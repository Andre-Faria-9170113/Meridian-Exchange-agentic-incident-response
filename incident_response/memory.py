"""A deliberately small policy around the supplied SQLite store."""
from datetime import datetime, timedelta

from meridian.agent_runtime import IncidentDeps

from .contracts import Report


def recall(deps: IncidentDeps) -> list[dict]:
    now = datetime.fromisoformat(deps.sim.clock.timestamp(deps.sim.state.tick))
    records = deps.memory.search(subject="order-gateway", team=deps.identity["team"],
                                 min_confidence=0.7, limit=10)
    return [record.public() for record in records
            if record.valid_until and datetime.fromisoformat(record.valid_until) > now
            and datetime.fromisoformat(record.created_at) <= now]


def remember(deps: IncidentDeps, report: Report, run_id: str) -> None:
    if report.status != "recovered":
        return
    memory_id = f"RUN-{run_id}"
    if any(record.memory_id == memory_id for record in deps.memory.all()):
        return
    now = datetime.fromisoformat(deps.sim.clock.timestamp(deps.sim.state.tick))
    deps.memory.add(memory_id=memory_id, kind="incident_summary", subject="order-gateway",
        content=f"{report.root_cause}. {report.summary} Evidence: {', '.join(report.evidence)}",
        source_type="tool", source_ref=f"run:{run_id}", author=deps.identity["name"],
        team=deps.identity["team"], created_at=now.isoformat(sep=" ", timespec="minutes"),
        valid_until=(now + timedelta(days=7)).isoformat(sep=" ", timespec="minutes"), confidence=0.8)


def correct(deps: IncidentDeps, memory_id: str, content: str, source_ref: str):
    """Correction is an operator operation, never an instruction from a ticket."""
    previous = deps.memory.get(memory_id)
    if previous.team != deps.identity["team"]:
        raise PermissionError("Cannot correct another team's memory")
    now = datetime.fromisoformat(deps.sim.clock.timestamp(deps.sim.state.tick))
    return deps.memory.add(kind=previous.kind, subject=previous.subject, content=content,
        source_type="user", source_ref=source_ref, author=deps.identity["name"],
        team=previous.team, created_at=now.isoformat(sep=" ", timespec="minutes"),
        valid_until=(now + timedelta(days=7)).isoformat(sep=" ", timespec="minutes"),
        confidence=0.8, supersedes=memory_id)
