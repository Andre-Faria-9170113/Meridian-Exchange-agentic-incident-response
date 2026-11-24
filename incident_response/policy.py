"""Authorization lives in code. Model output and approval do not grant roles."""
from meridian.agent_runtime import IncidentDeps
from meridian.security import describe_action

from .contracts import Proposal


def refusal(deps: IncidentDeps, proposal: Proposal, approval: str | None = None,
            *, require_approval: bool = True) -> str | None:
    facts = describe_action(deps, proposal.action, proposal.target, approval)
    if proposal.action not in {"restart_instance", "rollback_change"}:
        return "Unsupported action; whole-service restarts are never exposed"
    if facts.component is None:
        return "Unknown target"
    if facts.role not in {"first-line", "on-call", "incident-manager"}:
        return "Role has no remediation permission"
    if facts.role == "first-line" and (facts.critical or proposal.action != "restart_instance"):
        return "First-line can restart only a noncritical instance"
    if require_approval:
        if not (facts.approval_matches and facts.approval_status == "approved"):
            return "A matching approval is required for every action"
        if facts.critical and facts.trading_session and facts.approver_role != "incident-manager":
            return "Critical trading-session actions require incident-manager approval"
    return None
