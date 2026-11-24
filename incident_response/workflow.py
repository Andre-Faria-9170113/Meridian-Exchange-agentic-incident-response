"""End to end: brief -> specialists -> decision -> authorize -> act -> verify -> record.

The model never holds a mutation tool. After the coordinator decides, code checks authority,
re-reads fresh evidence, asks for approval, acts once with an idempotency key, confirms the
effect with the executor, and verifies recovery against the runbook criterion. The incident
ticket is updated (or created) by code, idempotently, with the outcome.

Progress is checkpointed (checkpoint.json) and the simulated systems persist separately
(world.pkl), so a paused run can be resumed in another process.
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from pydantic import ValidationError
from pydantic_ai.exceptions import AgentRunError

from meridian.agent_runtime import IncidentDeps, identity_for
from meridian.memory import MemoryStore
from meridian.scenarios import load_scenario

from . import __version__
from .agents import Crew, LLMSpecialists, Orchestrator, Pipeline, SpecialistFailure
from .contracts import Plan, Report
from .gateway import Gateway, ToolFailure, redact, require
from .guards import evidence_refusal, verify
from .memory import recall, remember
from .policy import PolicyRefusal, approval_refusal, approver_role, authority_refusal
from .rules import RuleSpecialists
from .state import Checkpoint
from .world import create_world, load_world

PAUSE_POINTS = ("plan", "action")


@dataclass
class Outcome:
    status: str
    summary: str
    actions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)


class Paused(Exception):
    def __init__(self, phase: str):
        super().__init__(phase)
        self.phase = phase


def coordinator_for(crew: Crew, mode: str, coordination: str, model: Any):
    if mode == "fixture":
        return Pipeline(crew, RuleSpecialists(crew.gateway, crew.deps, crew.brief))
    specialists = LLMSpecialists(crew, model)
    return Orchestrator(crew, specialists, model) if coordination == "orchestrator" else Pipeline(crew, specialists)


async def act(gateway: Gateway, deps: IncidentDeps, state: Checkpoint, plan: Plan, pause_after: str | None) -> Outcome:
    """Authorize, act once, confirm the effect, verify recovery. Refusals end the attempt with zero effects."""
    finding, proposal = plan.finding, plan.finding.proposal
    denied = authority_refusal(deps, proposal)
    if denied:
        raise PolicyRefusal(denied)
    key = f"{state.data['run_id']}:{proposal.action}:{proposal.target}"
    known = require(await gateway.call("action_status", idempotency_key=key))
    if known.get("status") != "completed":
        denied = await evidence_refusal(gateway, deps, finding)
        if denied:
            raise PolicyRefusal(denied)
        approval = require(await gateway.call("request_approval", action=proposal.action, target=proposal.target,
                                              reason=f"{proposal.reason} ({finding.cause})"[:300],
                                              approver_role=approver_role(deps, proposal)))
        state.set(approval=approval)
        denied = approval_refusal(deps, proposal, approval["approval_ref"])
        if denied:
            raise PolicyRefusal(denied)
        state.set(intent={"key": key, "action": proposal.action, "target": proposal.target, "approval_ref": approval["approval_ref"]})
        argument = "instance_id" if proposal.action == "restart_instance" else "change_id"
        await gateway.call(proposal.action, **{argument: proposal.target}, idempotency_key=key,
                           confirmation_ref=approval["approval_ref"])  # the response may be lost: ask the executor below
        known = require(await gateway.call("action_status", idempotency_key=key))
    if known.get("status") != "completed":
        raise ToolFailure(f"Executor outcome for {key} is {known.get('status')}; stopping without repeating the action")
    state.set(phase="acted", action=known)
    if pause_after == "action":
        raise Paused("acted")
    return await check_recovery(gateway, deps, plan, known)


async def check_recovery(gateway: Gateway, deps: IncidentDeps, plan: Plan, known: dict) -> Outcome:
    action = f"{known['action']} {known['target']} ({known['action_id']}, approval {known.get('confirmation_ref')})"
    recovered, refs, detail = await verify(gateway, deps, plan.finding.component, known["tick"])
    if recovered:
        return Outcome("recovered", f"Recovery verified: {detail}.", [action], refs)
    return Outcome("not_recovered", f"The action completed but recovery was not verified: {detail}.", [action], refs)


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
              observe: Callable[[Any], None] | None = None) -> dict:
    """Run (or resume) one incident. `observe(tools)` lets the evaluator see the simulated systems."""
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
                  scenario_sha256=hashlib.sha256((directory / "scenario.yaml").read_bytes()).hexdigest(),
                  memory_path=str((memory_path or directory.parent / "memory.db").resolve()), events=[])

    identity = identity_for(role or state.data.get("role")
                            or load_scenario(directory / "scenario.yaml").actor.get("role", "first-line"))
    tools = load_world(world_path, identity["name"]) if resume else create_world(directory / "scenario.yaml", world_path, identity["name"])
    state.set(role=identity["role"])
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
            coordinator = coordinator_for(crew, mode, coordination, model)
            try:
                if state.data["phase"] == "start":
                    plan = await coordinator.plan()
                    state.set(plan=plan.model_dump(), phase="planned")
                    if pause_after == "plan":
                        raise Paused("planned")
                plan = Plan.model_validate(state.data["plan"])
                if state.data["phase"] == "acted":
                    outcome = await check_recovery(gateway, deps, plan, state.data["action"])
                elif plan.decision.decision == "act":
                    outcome = await act(gateway, deps, state, plan, pause_after)
                elif plan.decision.decision == "no_action_needed":
                    healthy, refs, detail = await verify(gateway, deps, plan.finding.component, None)
                    outcome = (Outcome("resolved", f"No action needed: {detail}.", [], refs) if healthy else
                               Outcome("escalated", f"The investigator found no fault, but {detail}; escalate to on-call.", [], refs))
                else:
                    outcome = Outcome("escalated", f"Escalated to on-call: {plan.decision.rationale}")
            except PolicyRefusal as refusal:
                outcome = Outcome("refused", f"Refused before any effect: {refusal}", refusals=[str(refusal)])
            except (ToolFailure, ValidationError, AgentRunError, SpecialistFailure) as error:
                outcome = Outcome("insufficient_information", f"Stopped in a controlled way: {type(error).__name__}: {error}")
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


def record_usage(state: Checkpoint, crew: Crew | None) -> None:
    if crew is None:
        return
    usage = crew.usage
    state.set(usage={"requests": usage.requests, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                     "tool_calls": usage.tool_calls},
              model_messages=crew.messages, specialist_failures=crew.failures)
