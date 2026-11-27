"""End to end: brief -> specialists -> decision -> authorize -> act -> verify -> (one correction) -> record.

The model never holds a mutation tool. After the coordinator decides, code checks authority,
re-reads fresh evidence, asks for approval, acts once with an idempotency key, confirms the
effect with the executor, and verifies recovery against the runbook criterion. The incident
ticket is updated (or created) by code, idempotently, with the outcome.

Correction (session 7): when policy refuses the proposal or recovery is not verified, the coordinator gets the
reason and one attempt at a different mitigation, which is reviewed, authorized and verified again. Both attempts
are in the report. A person's denial is never corrected around.

Progress is checkpointed (checkpoint.json) and the simulated systems persist separately
(world.pkl), so a paused or crashed run can be resumed in another process. On resume the systems'
history decides (session 8): the executor's status for the idempotency key says whether the action
ran, and the approval service says whether an approval was given and whether it is still valid.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from pydantic import ValidationError
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.usage import RunUsage

from meridian.agent_runtime import IncidentDeps, identity_for
from meridian.memory import MemoryStore
from meridian.scenarios import load_scenario

from . import __version__
from .agents import Crew, LLMSpecialists, Orchestrator, Pipeline, SpecialistFailure
from .contracts import Plan, Report
from .gateway import Gateway, ToolFailure, redact, require
from .guards import evidence_refusal, verify
from .memory import recall, remember
from .monitors import watch
from .policy import (REMEDIATION_ROLES, PolicyRefusal, approval_refusal, approver_role, authority_refusal,
                     needs_on_call)
from .rules import RuleSpecialists
from .state import Checkpoint
from .world import create_world, load_world

PAUSE_POINTS = ("plan", "action")
CRASH_POINTS = ("approval", "action", "verify")
MAX_CORRECTIONS = 1


@dataclass
class Outcome:
    status: str
    summary: str
    actions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    correction: dict | None = None  # {"reason", "failed": [action, target]} when a correction may help


class Paused(Exception):
    def __init__(self, phase: str):
        super().__init__(phase)
        self.phase = phase


class Crash(BaseException):
    """The process dies (a test and demo hook, `run --crash-at`). Raised after the systems saved the step and before
    the checkpoint records it, so the checkpoint is behind. A BaseException: no `except Exception` in the run can
    swallow it, and nothing is written on the way out."""


def crash_if(point: str, crash_at: str | None) -> None:
    if point == crash_at:
        raise Crash(f"simulated crash at {point}: the systems recorded it, the checkpoint did not")


def note(state: Checkpoint, kind: str, **details: Any) -> None:
    """What resume found and decided, for the trace."""
    state.set(resume_log=state.data.get("resume_log", []) + [{"kind": kind, **details}])


def fallback_name() -> str | None:
    name = os.getenv("OPENAI_FALLBACK_MODEL")
    return f"openai:{name}" if name else None


def routed(model: Any) -> Any:
    """Session 9 routing. The fixture is the no-model route. In llm mode one model serves every agent; with
    OPENAI_FALLBACK_MODEL set, an API failure of the primary (outage, rate limit) moves that request to the
    fallback. Plan B is held to the same rules: its answers pass the same output validators, read budgets,
    gateway permissions and policy, so it cannot do what plan A may not. If both fail, the specialist fails and
    the run escalates to a person instead of guessing."""
    fallback = fallback_name()
    return FallbackModel(model, fallback) if fallback and isinstance(model, str) else model


def coordinator_for(crew: Crew, mode: str, coordination: str, model: Any):
    if mode == "fixture":
        return Pipeline(crew, RuleSpecialists(crew.gateway, crew.deps, crew.brief))
    model = routed(model)
    specialists = LLMSpecialists(crew, model)
    return Orchestrator(crew, specialists, model) if coordination == "orchestrator" else Pipeline(crew, specialists)


Approver = Callable[[dict], bool]  # a person deciding: gets the request, answers yes or no


def approval_request(gateway: Gateway, deps: IncidentDeps, plan: Plan, role: str) -> dict:
    """What a person needs to decide: the exact action, why, and the evidence behind it."""
    finding, review = plan.finding, plan.review
    refs = finding.evidence + (review.evidence if review else [])
    events = {event["ref"]: event for event in gateway.checkpoint.data["events"]}
    evidence = [f"{ref} ({events[ref]['caller']}) {events[ref]['tool']} {events[ref]['args']}"
                for ref in dict.fromkeys(refs) if ref in events]
    sim = deps.tools.sim
    return {"action": finding.proposal.action, "target": finding.proposal.target, "reason": finding.proposal.reason,
            "cause": finding.cause, "approver_role": role, "evidence": evidence,
            "reviewer": review.model_dump() if review else None, "time": sim.clock.label(sim.state.tick)}


async def ask_person(gateway: Gateway, deps: IncidentDeps, plan: Plan, role: str, approver: Approver) -> dict:
    """A person answers instead of the scenario's simulated approver. The request still goes through the systems'
    approval service, so the approval has a reference, is bound to this action and target, and is audited there."""
    proposal = plan.finding.proposal
    approved = approver(approval_request(gateway, deps, plan, role))
    sim, simulated = deps.tools.sim, deps.tools.sim.scenario.approver
    sim.scenario.approver = {"mode": "approve_all" if approved else "deny_all"}
    try:
        approval = require(await gateway.call("request_approval", action=proposal.action, target=proposal.target,
                                              reason=f"{proposal.reason} ({plan.finding.cause})"[:300],
                                              approver_role=role))
    finally:
        sim.scenario.approver = simulated
        deps.tools.persist()  # the saved world keeps the scenario's approver, not this one answer
    return {**approval, "answered_by": "person at the terminal"}


async def obtain_approval(gateway: Gateway, deps: IncidentDeps, state: Checkpoint, plan: Plan, role: str,
                          approver: Approver | None) -> dict:
    """Reuse the approval the approval service already holds for exactly this action and target while it is valid
    (after a crash the checkpoint may not know it was given); a denial stands; otherwise ask."""
    finding, proposal = plan.finding, plan.finding.proposal
    earlier = [record for record in deps.sim.approvals
               if record["action"] == proposal.action and record["target"] == proposal.target]
    if earlier:
        record = dict(earlier[-1])
        if record["status"] != "approved":
            note(state, "approval_denied_earlier", approval_ref=record["approval_ref"])
            return record
        stale = approval_refusal(deps, proposal, record["approval_ref"])
        if stale is None:
            note(state, "approval_reused", approval_ref=record["approval_ref"], given_at=record["time"],
                 now=deps.sim.clock.label(deps.sim.state.tick))
            return {**record, "reused": True}
        note(state, "approval_not_reused", approval_ref=record["approval_ref"], reason=stale)
    if approver is None:  # the scenario's simulated approver answers
        return require(await gateway.call("request_approval", action=proposal.action, target=proposal.target,
                                          reason=f"{proposal.reason} ({finding.cause})"[:300], approver_role=role))
    return await ask_person(gateway, deps, plan, role, approver)


async def act(gateway: Gateway, deps: IncidentDeps, state: Checkpoint, plan: Plan, pause_after: str | None,
              approver: Approver | None = None, crash_at: str | None = None) -> Outcome:
    """Authorize, act once, confirm the effect, verify recovery. Refusals end the attempt with zero effects."""
    finding, proposal = plan.finding, plan.finding.proposal
    denied = authority_refusal(deps, proposal)
    if denied:
        raise PolicyRefusal(denied, correctable=deps.identity["role"] in REMEDIATION_ROLES,
                            escalate=needs_on_call(deps, proposal))
    key = f"{state.data['run_id']}:{proposal.action}:{proposal.target}"
    known = require(await gateway.call("action_status", idempotency_key=key))
    if known.get("status") != "completed":
        denied = await evidence_refusal(gateway, deps, finding)
        if denied:
            raise PolicyRefusal(denied)
        approval = await obtain_approval(gateway, deps, state, plan, approver_role(deps, proposal), approver)
        crash_if("approval", crash_at)
        state.set(approval=approval)
        denied = approval_refusal(deps, proposal, approval["approval_ref"])
        if denied:
            raise PolicyRefusal(denied, correctable=approval.get("status") != "denied")
        state.set(intent={"key": key, "action": proposal.action, "target": proposal.target, "approval_ref": approval["approval_ref"]})
        argument = "instance_id" if proposal.action == "restart_instance" else "change_id"
        await gateway.call(proposal.action, **{argument: proposal.target}, idempotency_key=key,
                           confirmation_ref=approval["approval_ref"])  # the response may be lost: ask the executor below
        crash_if("action", crash_at)
        known = require(await gateway.call("action_status", idempotency_key=key))
    else:
        note(state, "action_already_done", idempotency_key=key, action_id=known.get("action_id"))
    if known.get("status") != "completed":
        raise ToolFailure(f"Executor outcome for {key} is {known.get('status')}; stopping without repeating the action")
    state.set(phase="acted", action=known)
    if pause_after == "action":
        raise Paused("acted")
    return await check_recovery(gateway, deps, plan, known, crash_at)


async def check_recovery(gateway: Gateway, deps: IncidentDeps, plan: Plan, known: dict, crash_at: str | None = None) -> Outcome:
    action = f"{known['action']} {known['target']} ({known['action_id']}, approval {known.get('confirmation_ref')})"
    recovered, refs, detail = await verify(gateway, deps, plan.finding.component, known["tick"], known["action"])
    crash_if("verify", crash_at)
    if recovered:
        return Outcome("recovered", f"Recovery verified: {detail}.", [action], refs)
    return Outcome("not_recovered", f"The action completed but recovery was not verified: {detail}.", [action], refs,
                   correction={"reason": f"{known['action']} {known['target']} completed but recovery was not verified: "
                                         f"{detail}", "failed": [known["action"], known["target"]]})


async def carry_out(gateway: Gateway, deps: IncidentDeps, state: Checkpoint, plan: Plan, pause_after: str | None,
                    approver: Approver | None, crash_at: str | None = None) -> Outcome:
    """One attempt at the plan's decision."""
    try:
        if state.data["phase"] == "acted":
            return await check_recovery(gateway, deps, plan, state.data["action"], crash_at)
        if plan.decision.decision == "act":
            return await act(gateway, deps, state, plan, pause_after, approver, crash_at)
        if plan.decision.decision == "no_action_needed":
            healthy, refs, detail = await verify(gateway, deps, plan.finding.component, None)
            return (Outcome("resolved", f"No action needed: {detail}.", [], refs) if healthy else
                    Outcome("escalated", f"The investigator found no fault, but {detail}; escalate to on-call.", [], refs))
        return Outcome("escalated", f"Escalated to on-call: {plan.decision.rationale}")
    except PolicyRefusal as refusal:
        proposal = plan.finding.proposal
        if refusal.escalate:
            return Outcome("escalated", f"Escalated to on-call, refused before any effect: {refusal}",
                           refusals=[str(refusal)])
        return Outcome("refused", f"Refused before any effect: {refusal}", refusals=[str(refusal)],
                       correction={"reason": f"Refused by policy: {refusal}", "failed": [proposal.action, proposal.target]}
                       if refusal.correctable else None)


def combined(attempts: list[dict], last: Outcome) -> Outcome:
    """The report covers every attempt: what was tried, refused or done before the correction, and what followed."""
    if not attempts:
        return last
    first = Outcome(**attempts[0]["outcome"])
    return Outcome(last.status, f"First attempt ({first.status}): {first.summary} After one correction: {last.summary}",
                   first.actions + last.actions, first.evidence + last.evidence, first.refusals + last.refusals)


async def update_tickets(gateway: Gateway, state: Checkpoint, plan: Plan, report: Report) -> list[str]:
    """Record the outcome on the incident ticket, or open one. Idempotent across resumes (marker in the text)."""
    notes, correlation = [], plan.correlation
    marker = f"[{state.data['run_id'][:8]}]"
    text = (f"{marker} Agent update for {report.incident_id}: status {report.status}. Cause: {report.root_cause} "
            f"Actions: {', '.join(report.actions_taken) or 'none'}. {report.summary}")[:1500]
    key = correlation.incident_ticket
    if key is None:
        found = await gateway.call("tickets.search_issues", text=marker.strip("[]"), max_results=5)
        existing = [issue["key"] for issue in found.get("issues", []) if issue.get("project") == "MRX"]
        if existing:
            key = existing[0]
        else:
            created = await gateway.call("tickets.create_issue", project="MRX", issue_type="Incident",
                                         summary=f"{report.incident_id}: {state.data['brief']['summary']}"[:80],
                                         description=text, component=correlation.component, priority="High")
            if created.get("error"):
                return [f"Could not open an incident ticket: {created['error']}"]
            key = created["key"]
    else:
        issue = await gateway.call("tickets.get_issue", key=key)
        if not any(marker in comment.get("body", "") for comment in issue.get("comments", [])):
            commented = await gateway.call("tickets.add_comment", key=key, body=text)
            if commented.get("error"):
                notes.append(f"Could not comment on {key}: {commented.get('message') or commented['error']}")
    issue = await gateway.call("tickets.get_issue", key=key)
    linked = {link.get("key") for link in issue.get("links", [])}
    for related in correlation.related:
        if related not in linked:
            result = await gateway.call("tickets.link_issues", key=key, other_key=related, link_type="relates to")
            if result.get("error"):
                notes.append(f"Could not link {related} to {key}: {result.get('message') or result['error']}")
    state.set(incident_ticket=key)
    return notes


async def run(scenario: Path | None, directory: Path, *, mode: str = "fixture", model: Any = None,
              coordination: str = "orchestrator", resume: bool = False, role: str | None = None,
              pause_after: str | None = None, memory_path: Path | None = None,
              observe: Callable[[Any], None] | None = None, approver: Approver | None = None,
              crash_at: str | None = None, downtime: int = 0) -> dict:
    """Run (or resume) one incident. `observe(tools)` lets the evaluator see the simulated systems.
    `approver`: a person who answers approval requests; by default the scenario's simulated approver does.
    `crash_at`: die at that step (see Crash). `downtime`: on resume, simulated minutes that passed while nobody
    worked; the systems kept running and approvals aged."""
    state = Checkpoint(directory)
    world_path = directory / "world.pkl"
    if resume:
        state.load()
        if state.data["version"] != __version__:
            raise ValueError("Resume with the code version that created this checkpoint")
        pinned = directory / "scenario.yaml"
        if hashlib.sha256(pinned.read_bytes()).hexdigest() != state.data["scenario_sha256"]:
            raise ValueError("The pinned scenario changed; resume refused")
        if state.data["phase"] == "done":
            return state.data["report"]
        mode, coordination = state.data["mode"], state.data["coordination"]
    else:
        if state.path.exists():
            raise ValueError("Run directory already used; resume it or choose a new --run-dir")
        if scenario is None:
            raise ValueError("A scenario is required")
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(scenario, directory / "scenario.yaml")
        state.set(version=__version__, run_id=uuid4().hex, phase="start", mode=mode,
                  coordination=coordination if mode == "llm" else "pipeline (deterministic rules)",
                  model=str(model) if mode == "llm" else "none (deterministic fixture)",
                  fallback_model=fallback_name() if mode == "llm" else None,
                  scenario_sha256=hashlib.sha256((directory / "scenario.yaml").read_bytes()).hexdigest(),
                  memory_path=str((memory_path or directory.parent / "memory.db").resolve()), events=[])

    identity = identity_for(role or state.data.get("role")
                            or load_scenario(directory / "scenario.yaml").actor.get("role", "first-line"))
    tools = load_world(world_path, identity["name"]) if resume else create_world(directory / "scenario.yaml", world_path, identity["name"])
    if resume:
        tools.pass_time(downtime)
        note(state, "resumed", phase=state.data["phase"], downtime_minutes=downtime,
             at=tools.sim.clock.label(tools.sim.state.tick), role=identity["role"])
    state.set(role=identity["role"], approver="person at the terminal" if approver else "scenario (simulated)")
    if observe:
        observe(tools)
    deps = IncidentDeps(tools, MemoryStore(state.data["memory_path"]), identity)
    deps.memory.seed(tools.sim.scenario.memory_seed)
    if "brief" not in state.data:
        state.set(brief=redact(tools.sim.incident_brief()))
    brief = state.data["brief"]

    outcome, plan, crew = None, None, None
    try:
        async with Gateway(tools, state, {"memory.recall": lambda subject: recall(deps, subject)}) as gateway:
            state.set(catalog=gateway.catalog)
            crew = Crew(gateway, deps, brief)
            if state.data.get("usage"):  # resumed: keep counting from what the earlier process used
                crew.usage = RunUsage(**state.data["usage"])
                crew.usage_by_agent = {agent: RunUsage(**used) for agent, used in state.data.get("usage_by_agent", {}).items()}
                crew.messages = state.data.get("model_messages", {})
            coordinator = coordinator_for(crew, mode, coordination, model)
            attempts: list[dict] = state.data.get("attempts", [])
            if "plan" in state.data:  # resumed: the coordinator continues from what was already established
                crew.correlation = Plan.model_validate(state.data["plan"]).correlation
                crew.excluded = {tuple(attempt["outcome"]["correction"]["failed"]) for attempt in attempts}
                if attempts:
                    crew.previous = Plan.model_validate(attempts[-1]["plan"]).finding
            try:
                if state.data["phase"] == "start":
                    plan = await coordinator.plan()
                    record_usage(state, crew)
                    state.set(plan=plan.model_dump(), phase="planned")
                    if pause_after == "plan":
                        raise Paused("planned")
                if state.data["phase"] != "correcting":
                    plan = Plan.model_validate(state.data["plan"])
                    outcome = await carry_out(gateway, deps, state, plan, pause_after, approver, crash_at)
                    if outcome.correction and len(attempts) < MAX_CORRECTIONS:
                        attempts.append({"plan": plan.model_dump(), "outcome": asdict(outcome),
                                         "events_before_correction": len(state.data["events"])})
                        state.set(attempts=attempts, phase="correcting")
                if state.data["phase"] == "correcting":
                    correction = attempts[-1]["outcome"]["correction"]
                    plan = await coordinator.correct(correction["reason"], tuple(correction["failed"]))
                    record_usage(state, crew)
                    state.set(plan=plan.model_dump(), phase="planned")
                    outcome = await carry_out(gateway, deps, state, plan, pause_after, approver, crash_at)
                outcome = combined(attempts, outcome)
            except (ToolFailure, ValidationError, AgentRunError, SpecialistFailure) as error:
                outcome = Outcome("insufficient_information", f"Stopped in a controlled way: {type(error).__name__}: {error}")
                outcome = combined(attempts, outcome)
            report = build_report(brief, plan, outcome, crew)
            if plan is not None:
                notes = await update_tickets(gateway, state, plan, report)
                report = report.model_copy(update={"refusals": report.refusals + notes,
                                                   "incident_ticket": state.data.get("incident_ticket")})
    except Paused as pause:
        record_usage(state, crew)
        state.set(phase=pause.phase)
        return {"status": "paused", "phase": pause.phase, "run_dir": str(directory)}
    if outcome.status == "recovered" and plan is not None:
        remember(deps, incident_id=brief["incident_id"], component=plan.finding.component, cause_kind=plan.finding.cause_kind,
                 action=state.data["action"], verification=outcome.evidence[-1], run_id=state.data["run_id"])
    record_usage(state, crew)
    state.set(phase="done", report=report.model_dump(), trace=redact([asdict(call) for call in tools.trace]),
              actions=[record.public() for record in tools.sim.executor.audit], approvals=tools.sim.approvals)
    state.set(monitors=watch(state.data, tools.sim.clock.is_trading_session))
    (directory / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report.model_dump()


def build_report(brief: dict, plan: Plan | None, outcome: Outcome, crew: Crew | None) -> Report:
    finding = plan.finding if plan else None
    evidence = list(finding.evidence) if finding else []
    if plan and plan.review:
        evidence += plan.review.evidence
    root_cause = finding.cause if finding else "Undetermined"
    if finding and finding.change_id and finding.change_id not in root_cause:
        root_cause += f" (change {finding.change_id})"
    summary = outcome.summary
    if crew and crew.failures:
        summary += " Specialist failures: " + "; ".join(crew.failures)
    return Report(incident_id=brief["incident_id"], status=outcome.status, root_cause=root_cause,
                  incident_ticket=plan.correlation.incident_ticket if plan else None,
                  related_tickets=plan.correlation.related if plan else [],
                  evidence=sorted(set(evidence + outcome.evidence)), actions_taken=outcome.actions,
                  refusals=outcome.refusals, summary=summary)


def usage_dict(usage: RunUsage) -> dict:
    return {"requests": usage.requests, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "tool_calls": usage.tool_calls}


def models_used(messages: dict[str, list]) -> dict[str, list[str]]:
    """Which model actually answered each agent (the primary, or the fallback after a failure)."""
    def names(value: Any) -> set[str]:
        if isinstance(value, dict):
            found = {value["model_name"]} if value.get("kind") == "response" and value.get("model_name") else set()
            return found.union(*(names(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(names(item) for item in value))
        return set()
    return {agent: sorted(names(conversation)) for agent, conversation in messages.items()}


def record_usage(state: Checkpoint, crew: Crew | None) -> None:
    """Usage for the whole team and per agent. The orchestrator's own share is the total minus its specialists'."""
    if crew is None:
        return
    by_agent = {agent: usage_dict(used) for agent, used in crew.usage_by_agent.items()}
    if "orchestrator" in crew.messages:
        total = usage_dict(crew.usage)
        by_agent["orchestrator"] = {key: total[key] - sum(used[key] for used in by_agent.values()) for key in total}
    state.set(usage=usage_dict(crew.usage), usage_by_agent=by_agent, models_used=models_used(crew.messages),
              model_messages=crew.messages, specialist_failures=crew.failures)
