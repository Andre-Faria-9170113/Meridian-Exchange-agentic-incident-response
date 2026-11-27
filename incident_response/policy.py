"""Authorization lives in code. Model output, ticket text and approvals never grant a role.

Policy (stricter than the simulator's minimum):
- Only restart_instance and rollback_change exist. Whole-service restarts are never exposed.
- settlement-analyst (another team) cannot remediate anything here.
- first-line may act only on non-critical components (a gateway instance, a change to the gateway).
- on-call and incident-manager may also act on critical components (matching-engine, reference-db).
- Every action needs a matching approval. On a critical component during the trading session the
  approver must be the incident manager; otherwise the on-call engineer approves.
- An approval is valid for 15 minutes, and not at all once the trading session has opened if it was given
  before (session 8 lab). After an interruption a saved approval is reused only while it is still valid.
"""
from __future__ import annotations

from meridian.agent_runtime import IncidentDeps
from meridian.security import ActionRequest, describe_action

from .contracts import Proposal

REMEDIATION_ROLES = {"first-line", "on-call", "incident-manager"}
APPROVAL_TTL_MINUTES = 15


class PolicyRefusal(Exception):
    """An action was refused by policy (role, target, evidence or approval).

    `correctable`: the proposal was the problem (a critical target, evidence that does not hold), so the coordinator
    may propose something else once. Not when a person denied the approval, and not when the identity may not
    remediate at all: a different proposal would not change either answer."""

    def __init__(self, reason: str, correctable: bool = True):
        super().__init__(reason)
        self.correctable = correctable


def facts(deps: IncidentDeps, proposal: Proposal, approval_ref: str | None = None) -> ActionRequest:
    return describe_action(deps, proposal.action, proposal.target, approval_ref)


def authority_refusal(deps: IncidentDeps, proposal: Proposal) -> str | None:
    """May this identity attempt this action on this target at all? Checked before asking for approval."""
    if proposal.action not in {"restart_instance", "rollback_change"}:
        return f"Unsupported action {proposal.action!r}; whole-service restarts are never exposed"
    request = facts(deps, proposal)
    if request.component is None:
        return f"Unknown target {proposal.target!r}"
    if request.role not in REMEDIATION_ROLES:
        return f"Role {request.role} has no remediation permission"
    if request.role == "first-line" and request.critical:
        return f"first-line may not {proposal.action} on {request.component}: it is a critical component (escalate to on-call)"
    return None


def approver_role(deps: IncidentDeps, proposal: Proposal) -> str:
    request = facts(deps, proposal)
    return "incident-manager" if request.critical and request.trading_session else "on-call"


def approval_refusal(deps: IncidentDeps, proposal: Proposal, approval_ref: str | None) -> str | None:
    """Is there a matching, approved, sufficient approval for exactly this action and target?"""
    request = facts(deps, proposal, approval_ref)
    if not approval_ref or request.approval_status is None:
        return "A matching approval is required for every action"
    if not request.approval_matches:
        return f"{approval_ref} does not approve {proposal.action} {proposal.target}"
    if request.approval_status != "approved":
        return f"{approval_ref} was {request.approval_status} by the {request.approver_role}"
    if request.critical and request.trading_session and request.approver_role != "incident-manager":
        return "Critical actions during the trading session need the incident manager's approval"
    return validity_refusal(deps, approval_ref)


def validity_refusal(deps: IncidentDeps, approval_ref: str) -> str | None:
    """Is this approval still valid now? It ages with the simulated clock: a crash and downtime age it too."""
    record = next((item for item in deps.sim.approvals if item["approval_ref"] == approval_ref), None)
    if record is None:
        return f"{approval_ref} is not known to the approval service"
    clock, now = deps.sim.clock, deps.sim.state.tick
    age = (now - record["tick"]) * clock.minutes_per_tick
    if age > APPROVAL_TTL_MINUTES:
        return f"{approval_ref} expired: given at {record['time']}, {age} minutes ago (valid for {APPROVAL_TTL_MINUTES})"
    if clock.is_trading_session(now) and not clock.is_trading_session(record["tick"]):
        return f"{approval_ref} was given at {record['time']}, before the trading session opened"
    return None
