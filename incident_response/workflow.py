"""End-to-end starter: observe -> delegate -> authorize -> act -> verify."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from meridian.agent_runtime import IncidentDeps, identity_for
from meridian.memory import MemoryStore
from meridian.simulator import Simulator
from meridian.tools import MeridianTools

from . import __version__
from .agents import fixture_plan, llm_plan
from .contracts import Metrics, Plan, Report
from .gateway import Gateway, ToolFailure, redact, require
from .memory import recall, remember
from .policy import refusal
from .state import Checkpoint


async def metrics(gateway: Gateway, component: str) -> Metrics:
    return Metrics.model_validate(require(await gateway.call("read_metrics", component=component,
                                                              window_ticks=5, per_instance=True)))


async def collect(gateway: Gateway, deps: IncidentDeps) -> dict:
    gateway_metrics = await metrics(gateway, "order-gateway")
    database_metrics = await metrics(gateway, "reference-db")
    links = [require(await gateway.call("check_link", source="order-gateway", target=target))
             for target in ("reference-db", "matching-engine")]
    tickets = require(await gateway.call("search_issues", server="tickets", text="order acknowledgements", max_results=5))
    if not isinstance(tickets.get("issues"), list):
        raise ToolFailure("Invalid MCP search_issues output")
    for issue in tickets["issues"]:
        if not isinstance(issue, dict) or not isinstance(issue.get("key"), str):
            raise ToolFailure("Invalid MCP issue summary")
    return {"brief": deps.sim.incident_brief(), "gateway_metrics": gateway_metrics.model_dump(),
        "database_metrics": database_metrics.model_dump(), "links": links, "tickets": tickets,
        "alerts": require(await gateway.call("list_alerts", server="monitoring", device="order-gateway", size=10)),
        "logs": require(await gateway.call("read_logs", component="order-gateway", level="ERROR", limit=10)),
        "changes": require(await gateway.call("recent_changes", limit=5)),
        "runbook": require(await gateway.call("read_runbook", name="order-gateway-latency")),
        "memory_hints": recall(deps)}


async def evidence_refusal(gateway: Gateway, plan: Plan) -> str | None:
    proposal = plan.finding.proposal
    if not plan.review.safe_to_attempt:
        return "Safety specialist did not endorse the proposal"
    if proposal.action != "restart_instance":
        return "Starter action evidence guard supports instance restarts only; implement rollback evidence before enabling it"
    latest = (await metrics(gateway, "order-gateway")).readings[-1]
    instance = latest.instances.get(proposal.target)
    if not instance or instance.get("memory_pct", 0) <= 90:
        return "Fresh metrics do not justify restarting this gateway instance"
    for target in ("reference-db", "matching-engine"):
        link = require(await gateway.call("check_link", source="order-gateway", target=target))
        if link.get("state") != "up":
            return "Dependency link is not healthy; investigate it before any restart"
    db = (await metrics(gateway, "reference-db")).readings[-1]
    if db.latency_ms >= 20 or db.error_rate >= 0.01:
        return "Database dependency is not healthy"
    return None


async def verify(gateway: Gateway, action_tick: int) -> tuple[bool, list[str]]:
    refs = []
    for _ in range(10):
        observation = await metrics(gateway, "order-gateway")
        refs.append(observation.source_ref)
        recent = observation.readings[-3:]
        if (len(recent) == 3 and recent[0].tick > action_tick
                and len({row.tick for row in recent}) == 3
                and all(right.tick == left.tick + 1 for left, right in zip(recent, recent[1:]))
                and all(row.latency_ms < 20 and row.error_rate < 0.01 for row in recent)):
            return True, refs
    return False, refs


async def run(scenario: Path | None, directory: Path, *, mode: str = "fixture", model: Any = None,
              resume: bool = False, role: str | None = None, pause_after: str | None = None,
              memory_path: Path | None = None) -> dict:
    state = Checkpoint(directory)
    if resume:
        state.load()
        if state.data["version"] != __version__:
            raise ValueError("Resume with the version that created this checkpoint")
        scenario = directory / "scenario.yaml"
        if hashlib.sha256(scenario.read_bytes()).hexdigest() != state.data["scenario_sha256"]:
            raise ValueError("Pinned scenario changed; resume refused")
        mode = state.data["mode"]
        if state.data["phase"] == "done":
            return state.data["report"]
    else:
        if state.path.exists():
            raise ValueError("Run directory already exists; use --resume or a new --run-dir")
        if scenario is None:
            raise ValueError("A scenario is required")
        raw = scenario.read_bytes()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "scenario.yaml").write_bytes(raw)
        scenario = directory / "scenario.yaml"
        state.set(version=__version__, run_id=uuid4().hex, phase="investigate", mode=mode,
                  model=str(model) if mode == "llm" else "none (deterministic fixture)",
                  scenario_sha256=hashlib.sha256(raw).hexdigest(), events=[],
                  memory_path=str((memory_path or directory.parent / "memory.db").resolve()))

    sim = Simulator(scenario)
    identity = identity_for(role or state.data.get("role") or sim.scenario.actor.get("role", "first-line"))
    state.set(role=identity["role"])
    tools = MeridianTools(sim, actor=identity["name"])
    deps = IncidentDeps(tools, MemoryStore(state.data["memory_path"]), identity)
    # Fixtures intentionally start with a clean memory DB in the evaluation runner.
    deps.memory.seed(sim.scenario.memory_seed)
    report = None
    try:
        async with Gateway(tools, state) as gateway:
            if resume:
                # Replay records original actors; subsequent authorization uses current identity.
                await gateway.replay()
            if state.data["phase"] == "investigate":
                context = await collect(gateway, deps)
                state.set(context=context)
                audit: dict = {}
                try:
                    plan = fixture_plan(context) if mode == "fixture" else await llm_plan(context, model, audit)
                finally:
                    state.set(**audit)
                state.set(plan=plan.model_dump(), phase="planned")
                if pause_after == "plan":
                    return {"status": "paused", "phase": "planned", "run_dir": str(directory)}
            plan = Plan.model_validate(state.data["plan"])
            proposal = plan.finding.proposal
            evidence = list(plan.finding.evidence) + list(plan.review.evidence)
            actions: list[str] = []
            status, summary = "not_recovered", "No supported mitigation proposed; escalate for further investigation"
            if proposal.action != "none":
                denied = refusal(deps, proposal, require_approval=False)
                if denied:
                    raise PermissionError(denied)
                key = f"{state.data['run_id']}:{proposal.action}:{proposal.target}"
                known = require(await gateway.call("action_status", idempotency_key=key))
                if known.get("status") != "completed":
                    denied = await evidence_refusal(gateway, plan)
                    if denied:
                        raise PermissionError(denied)
                    approval = require(await gateway.call("request_approval", action=proposal.action,
                        target=proposal.target, reason=proposal.reason, approver_role="on-call"))
                    denied = refusal(deps, proposal, approval.get("approval_ref"))
                    if denied:
                        raise PermissionError(denied)
                    args = {"instance_id" if proposal.action == "restart_instance" else "change_id": proposal.target,
                            "idempotency_key": key, "confirmation_ref": approval["approval_ref"]}
                    await gateway.call(proposal.action, **args)
                    known = require(await gateway.call("action_status", idempotency_key=key))
                else:
                    denied = refusal(deps, proposal, known.get("confirmation_ref"))
                    if denied:
                        raise PermissionError(denied)
                if known.get("status") != "completed":
                    raise ToolFailure("Executor outcome remains unknown; stop without repeating the action")
                state.set(phase="acted", action=known)
                if pause_after == "action":
                    return {"status": "paused", "phase": "acted", "run_dir": str(directory)}
                actions.append(f"{proposal.action} {proposal.target} ({known['action_id']})")
                healthy, refs = await verify(gateway, known["tick"])
                evidence += refs
                status = "recovered" if healthy else "not_recovered"
                summary = ("Recovery verified against the gateway runbook. Restart mitigates pressure; the memory leak remains."
                           if healthy else "Action completed but recovery was not verified within the observation budget")
            report = Report(incident_id=sim.scenario.incident["id"], status=status,
                root_cause=plan.finding.cause, evidence=sorted(set(evidence)), actions_taken=actions, summary=summary)
    except Exception as error:
        # Keep trace/checkpoint even after model, tool, contract or policy failures.
        report = Report(incident_id=sim.scenario.incident["id"],
            status="refused" if isinstance(error, PermissionError) else "insufficient_information",
            root_cause=state.data.get("plan", {}).get("finding", {}).get("cause", "Undetermined"),
            evidence=[], actions_taken=[f"{r.action} {r.target}" for r in sim.executor.effects()],
            summary=f"{type(error).__name__}: {error}")
    remember(deps, report, state.data["run_id"])
    state.set(phase="done", report=report.model_dump(),
              trace=redact([asdict(call) for call in tools.trace]),
              actions=[record.public() for record in sim.executor.audit], approvals=sim.approvals)
    (directory / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report.model_dump()
