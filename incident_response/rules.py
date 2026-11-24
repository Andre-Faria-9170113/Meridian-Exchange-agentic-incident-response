"""Deterministic specialists: the 'no model' route.

They read the systems through the same gateway, with the same per-specialist permissions,
and return the same validated contracts as the LLM specialists. Used by `--mode fixture`
for offline runs, tests and as the reference baseline for evaluations.

The correlation vocabulary is adapted from the course's session 3 solution
(sessions/course-02-agentic-ai/03-mcp-integration/starter/incident_server.py).
"""
from __future__ import annotations

import re

from meridian.agent_runtime import IncidentDeps

from .contracts import Correlation, Decision, Finding, Metrics, Proposal, Review
from .gateway import Gateway, require
from .guards import MEMORY_LIMIT_PCT, dependencies, healthy

COMPONENTS = ["order-gateway", "matching-engine", "market-data", "settlement", "reference-db"]
# Words that point to a component, for events that do not name one (complaints, some tickets).
COMPONENT_WORDS = {
    "order-gateway": ["acknowledg", "order", "reject", "503", "gateway"],
    "market-data": ["quote", "market data", "feed", "price"],
    "settlement": ["settlement", "batch"],
}
# Symptom families. Memory pressure shows up as latency.
SYMPTOM_WORDS = {
    "slow": ["latency", "slow", "late", "delay", "acknowledg", "memory"],
    "errors": ["error", "reject", "503", "fail", "refused"],
}
WINDOW_MINUTES = 120
RECENT_CHANGE_TICKS = 720  # changes from the last 12 hours are candidate causes


def component_in(text: str) -> str | None:
    lowered = text.lower()
    named = [component for component in COMPONENTS if component in lowered]
    if named:
        return named[0]
    return next((component for component, words in COMPONENT_WORDS.items() if any(word in lowered for word in words)), None)


def symptoms_in(text: str) -> set[str]:
    lowered = text.lower()
    return {family for family, words in SYMPTOM_WORDS.items() if any(word in lowered for word in words)}


def minutes(text: str | None) -> int | None:
    match = re.search(r"(\d{2}):(\d{2})\s*$", text or "")
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


class RuleSpecialists:
    def __init__(self, gateway: Gateway, deps: IncidentDeps, brief: dict):
        self.gateway, self.deps, self.brief = gateway, deps, brief

    async def triage(self, question: str = "") -> Correlation:
        component = component_in(self.brief["summary"])
        if component is None:
            raise ValueError("The incident does not name a component")
        symptoms = symptoms_in(self.brief["summary"])
        alerts = require(await self.gateway.call("monitoring.list_alerts", caller="triage", device=component, size=20))
        issues = require(await self.gateway.call("tickets.search_issues", caller="triage", max_results=10))
        now = minutes(self.brief["time"])
        related, unrelated = [], []
        for issue in issues["issues"]:
            if issue["status"] in ("Resolved", "Closed"):
                continue
            text = f"{issue['summary']} {issue.get('component') or ''}"
            same_component = (issue.get("component") or component_in(text)) == component
            compatible = bool(symptoms_in(text) & symptoms) if symptoms else True
            opened = minutes(issue.get("created"))
            recent = now is None or opened is None or abs(now - opened) <= WINDOW_MINUTES
            (related if same_component and compatible and recent else unrelated).append(issue)
        incidents = [issue for issue in related if issue["project"] == "MRX" and issue["issue_type"] == "Incident"]
        incident = incidents[-1]["key"] if incidents else None
        return Correlation(
            component=component, incident_ticket=incident,
            related=[issue["key"] for issue in related if issue["key"] != incident],
            unrelated=[issue["key"] for issue in unrelated],
            reasoning=(f"Alert on {component} ({', '.join(sorted(symptoms)) or 'no symptom words'}). Same component, compatible "
                       f"symptoms and opened within {WINDOW_MINUTES} minutes: related. Other component or symptom: unrelated."),
            evidence=[alerts["ref"], issues["ref"]])

    async def investigate(self, correlation: Correlation, excluded: set[tuple[str, str]] = frozenset(), note: str = "") -> Finding:
        component = correlation.component
        raw = require(await self.gateway.call("read_metrics", caller="investigator", component=component, window_ticks=5, per_instance=True))
        observed = Metrics.model_validate(raw)
        refs = [raw["ref"]]
        version = raw["readings"][-1].get("version", "")
        runbooks = require(await self.gateway.call("list_runbooks", caller="investigator"))
        refs.append(runbooks["ref"])
        names = [book["name"] for book in runbooks["runbooks"] if book["name"].startswith(component)
                 and version.rsplit(".", 1)[0] in book["applies_to"]]
        if not names:
            names = [book["name"] for book in runbooks["runbooks"] if book["name"].startswith(component)]
        if names:
            refs.append(require(await self.gateway.call("read_runbook", caller="investigator", name=names[-1]))["ref"])
        hints = require(await self.gateway.call("memory.recall", caller="investigator", subject=component))
        refs.append(hints["ref"])  # memory is a hint; the decision below uses current readings only

        latest = observed.readings[-1]
        hot = [name for name, values in latest.instances.items() if values.get("memory_pct", 0) > MEMORY_LIMIT_PCT]
        allowed = lambda action, target: (action, target) not in excluded  # noqa: E731
        if len(hot) == 1:
            action = "restart_instance" if allowed("restart_instance", hot[0]) else "none"
            return Finding(component=component, cause_kind="instance_memory",
                           cause=f"{hot[0]} memory at {latest.instances[hot[0]]['memory_pct']:.1f}% (above {MEMORY_LIMIT_PCT:.0f}%)",
                           evidence=refs, proposal=Proposal(action=action, target=hot[0] if action != "none" else "",
                                                            reason="Runbook: restart the single instance above 90% memory"))
        if len(hot) > 1:
            return Finding(component=component, cause_kind="instance_memory", cause=f"Several instances above {MEMORY_LIMIT_PCT:.0f}%: {hot}",
                           evidence=refs, proposal=Proposal(reason="The runbook covers a single instance only; escalate"))
        if all(healthy(component, row) for row in observed.readings[-3:]):
            return Finding(component=component, cause_kind="no_fault", cause=f"{component} is healthy in the latest readings; the alert is stale",
                           evidence=refs, proposal=Proposal(reason="Nothing to fix"))
        changes = require(await self.gateway.call("recent_changes", caller="investigator", limit=10))
        refs.append(changes["ref"])
        scope = {component, *dependencies(self.deps, component)}
        now = self.deps.sim.state.tick
        candidates = [change for change in changes["changes"] if change["active"] and change["component"] in scope
                      and now - RECENT_CHANGE_TICKS <= change["at_tick"] <= now]
        if candidates:
            change = candidates[0]  # the most recent active change on the component or a dependency
            if "reference-db" in scope and component != "reference-db":
                runbook = require(await self.gateway.call("read_runbook", caller="investigator", name="reference-db-connections"))
                refs.append(runbook["ref"])
            named = require(await self.gateway.call("read_logs", caller="investigator", contains=change["change_id"], limit=5))
            refs.append(named["ref"])
            if named["total_matching"] and allowed("rollback_change", change["change_id"]):
                return Finding(component=component, cause_kind="change", change_id=change["change_id"],
                               cause=f"{change['change_id']} ({change['component']}: {change['description']}) is named in the logs: "
                                     f"{named['lines'][0]['message'][:120]}",
                               evidence=refs, proposal=Proposal(action="rollback_change", target=change["change_id"],
                                                                reason="Runbook: if a recent change explains the errors, roll it back"))
            return Finding(component=component, cause_kind="change", change_id=change["change_id"],
                           cause=f"Suspected {change['change_id']} ({change['component']}: {change['description']}), active since "
                                 f"{change['at']}" + ("; already refused: " + note if note else "; no log line names it"),
                           evidence=refs, proposal=Proposal(reason="Not enough evidence or authority to roll back; escalate"))
        kind = "data_feed" if component == "market-data" else "unknown"
        return Finding(component=component, cause_kind=kind,
                       cause=f"{component} degraded (latency {latest.latency_ms} ms, errors {latest.error_rate:.1%}); no recent change explains it",
                       evidence=refs, proposal=Proposal(reason="No runbook action applies; escalate"))

    async def review(self, finding: Finding) -> Review:
        refs, constraints, safe = [], [], finding.proposal.action != "none"
        for target in dependencies(self.deps, finding.component):
            link = require(await self.gateway.call("check_link", caller="reviewer", source=finding.component, target=target))
            refs.append(link["ref"])
            if link["state"] != "up":
                constraints.append(f"Link {finding.component}->{target} is {link['state']}")
                safe = safe and finding.proposal.action == "rollback_change"  # a restart cannot fix a broken link
        if "reference-db" in dependencies(self.deps, finding.component):
            db = require(await self.gateway.call("read_metrics", caller="reviewer", component="reference-db", window_ticks=3))
            refs.append(db["ref"])
            if db["readings"][-1]["error_rate"] >= 0.01 and finding.proposal.action == "restart_instance":
                constraints.append("reference-db is unhealthy: restarting a client will not help")
                safe = False
        session = require(await self.gateway.call("exchange_status", caller="reviewer"))
        refs.append(session["ref"])
        if session["trading_session_open"]:
            constraints.append("Trading session open: critical targets need incident-manager approval")
        constraints.append("Exactly one action on the exact target; verify recovery before closing")
        if finding.proposal.action == "none":
            constraints.insert(0, "No action proposed")
        return Review(safe_to_attempt=safe, constraints=constraints, evidence=refs)


def decide(finding: Finding, review: Review | None) -> Decision:
    """The pipeline's fixed decision rule, used when no orchestrator agent decides."""
    if finding.cause_kind == "no_fault":
        return Decision(decision="no_action_needed", rationale="The investigator found no current fault")
    if finding.proposal.action != "none" and review is not None and review.safe_to_attempt:
        return Decision(decision="act", rationale="A runbook action is proposed and the reviewer found it safe")
    return Decision(decision="escalate", rationale="No safe action within the runbooks: " + finding.proposal.reason)
