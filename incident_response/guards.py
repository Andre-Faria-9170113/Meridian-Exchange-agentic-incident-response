"""Checks in code around every action: fresh evidence before acting, and recovery after.

Runbook criteria are encoded here, not left to a model:
- order-gateway-latency v2: restart one instance only when its memory is above 90% and the
  dependency links are up and reference-db is healthy; recovery = latency < 20 ms and
  error rate < 1% in 3 consecutive readings taken after the action.
- reference-db-connections: roll back a change only when evidence ties it to the errors;
  recovery = client error rate < 1% in 3 consecutive readings (and the links up).
- market-data-delays: recovery = market-data latency < 10 ms in 3 consecutive readings.
"""
from __future__ import annotations

from meridian.agent_runtime import IncidentDeps

from .contracts import Finding, Metrics, Proposal, Reading
from .gateway import Gateway, require

HEALTH = {"order-gateway": {"latency_ms": 20.0, "error_rate": 0.01},
          "market-data": {"latency_ms": 10.0, "error_rate": 0.01}}
DEFAULT_HEALTH = {"error_rate": 0.01}
MEMORY_LIMIT_PCT = 90.0
VERIFY_ATTEMPTS = 10


def healthy(component: str, reading: Reading) -> bool:
    limits = HEALTH.get(component, DEFAULT_HEALTH)
    return all(getattr(reading, metric) < limit for metric, limit in limits.items())


def dependencies(deps: IncidentDeps, component: str) -> list[str]:
    """Static topology (what a CMDB would tell us), not live state."""
    return list(deps.sim.state.component(component).depends_on)


def component_of_target(deps: IncidentDeps, proposal: Proposal) -> str | None:
    from .policy import facts
    return facts(deps, proposal).component


async def metrics(gateway: Gateway, component: str, window: int = 5) -> Metrics:
    return Metrics.model_validate(require(await gateway.call("read_metrics", component=component,
                                                             window_ticks=window, per_instance=True)))


async def links_down(gateway: Gateway, deps: IncidentDeps, component: str) -> list[str]:
    down = []
    for target in dependencies(deps, component):
        link = require(await gateway.call("check_link", source=component, target=target))
        if link.get("state") != "up":
            down.append(f"{component}->{target} is {link.get('state')} ({link['ref']})")
    return down


async def evidence_refusal(gateway: Gateway, deps: IncidentDeps, finding: Finding) -> str | None:
    """Re-read the systems now. None when current evidence justifies the exact proposal."""
    proposal = finding.proposal
    component = component_of_target(deps, proposal)
    if component is None:
        return f"Unknown target {proposal.target}"
    if proposal.action == "restart_instance":
        latest = (await metrics(gateway, component)).readings[-1]
        instance = latest.instances.get(proposal.target)
        if not instance or instance.get("memory_pct", 0) <= MEMORY_LIMIT_PCT:
            return f"Fresh metrics do not show {proposal.target} above {MEMORY_LIMIT_PCT:.0f}% memory"
        down = await links_down(gateway, deps, component)
        if down:
            return "Runbook: do not restart while a dependency link is unhealthy (" + "; ".join(down) + ")"
        for dependency in dependencies(deps, component):
            if dependency == "reference-db" and not healthy(dependency, (await metrics(gateway, dependency)).readings[-1]):
                return "reference-db is unhealthy; a restart would not help"
        return None
    if proposal.action == "rollback_change":
        changes = require(await gateway.call("recent_changes", limit=10))["changes"]
        change = next((item for item in changes if item["change_id"] == proposal.target), None)
        if change is None or not change["active"]:
            return f"{proposal.target} is not an active recent change"
        named = require(await gateway.call("read_logs", contains=proposal.target, limit=5))
        if not named["total_matching"]:
            return f"No log line names {proposal.target}; timing alone does not justify a rollback"
        symptom = finding.component
        if healthy(symptom, (await metrics(gateway, symptom)).readings[-1]):
            return f"{symptom} is already healthy; nothing to roll back for"
        return None
    return f"Unsupported action {proposal.action}"


async def verify(gateway: Gateway, deps: IncidentDeps, component: str, after_tick: int | None) -> tuple[bool, list[str], str]:
    """Three consecutive healthy readings (after the action, if any) and healthy dependency links."""
    refs: list[str] = []
    for _ in range(VERIFY_ATTEMPTS):
        observation = await metrics(gateway, component)
        refs.append(observation.source_ref)
        recent = observation.readings[-3:]
        fresh = after_tick is None or recent[0].tick > after_tick
        consecutive = len(recent) == 3 and all(b.tick == a.tick + 1 for a, b in zip(recent, recent[1:]))
        if fresh and consecutive and all(healthy(component, row) for row in recent):
            down = await links_down(gateway, deps, component)
            if not down:
                return True, refs, f"{component} healthy in 3 consecutive readings ({observation.source_ref})"
            return False, refs, "; ".join(down)
        if after_tick is None:
            return False, refs, f"{component} is not healthy now ({observation.source_ref})"
    return False, refs, f"{component} did not meet the recovery criterion within {VERIFY_ATTEMPTS} observations"
