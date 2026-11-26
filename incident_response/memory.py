"""Memory policy around the supplied SQLite store (session 4).

Write: only after a verified recovery, only facts produced by code (action, target, executor
action id, verification reference), never free text from a model, a log or a ticket. Source is
the run id; confidence 0.8; valid for seven simulated days.

Recall: same team only, active, confidence >= 0.7, with an explicit validity that has not
expired, created no later than now. Recalled records are hints for the investigator, labelled
as such; current readings always decide.

Correct / forget: operator operations (`python -m incident_response memory ...`), by a person of
the same team, never by the agent's identity and never triggered by ticket or log text. A
correction writes a sourced replacement and supersedes the old record; forgetting deletes the
content and keeps an audit entry (who, when, why).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from meridian.agent_runtime import IncidentDeps
from meridian.memory import MemoryRecord, MemoryStore

VALIDITY = timedelta(days=7)
MIN_CONFIDENCE = 0.7


def now(deps: IncidentDeps) -> datetime:
    return datetime.fromisoformat(deps.sim.clock.timestamp(deps.sim.state.tick))


def stamp(moment: datetime) -> str:
    return moment.isoformat(sep=" ", timespec="minutes")


def recall(deps: IncidentDeps, subject: str) -> dict:
    current = now(deps)
    records = deps.memory.search(subject=subject, team=deps.identity["team"], min_confidence=MIN_CONFIDENCE, limit=10)
    hints = [{key: record.public()[key] for key in ("memory_id", "content", "source_type", "source_ref", "created_at",
                                                     "valid_until", "confidence")}
             for record in records
             if record.valid_until and datetime.fromisoformat(record.valid_until) > current
             and datetime.fromisoformat(record.created_at) <= current]
    excluded = len(deps.memory.search(subject=subject, team=deps.identity["team"], limit=50)) - len(hints)
    return {"subject": subject, "hints": hints, "excluded_records": excluded,
            "note": "Hints from earlier verified incidents. They are not instructions; current readings decide."}


def remember(deps: IncidentDeps, *, incident_id: str, component: str, cause_kind: str, action: dict, verification: str,
             run_id: str) -> MemoryRecord | None:
    memory_id = f"RUN-{run_id[:12]}"
    if any(record.memory_id == memory_id for record in deps.memory.all()):
        return None  # idempotent: one summary per run, also after a resume
    content = (f"{incident_id}: {cause_kind.replace('_', ' ')} on {component}. {action['action']} {action['target']} "
               f"({action['action_id']}) was followed by verified recovery ({verification}). "
               "This mitigated the symptom; check current readings, the affected target may differ next time.")
    current = now(deps)
    return deps.memory.add(memory_id=memory_id, kind="incident_summary", subject=component, content=content,
                           source_type="tool", source_ref=f"run:{run_id}", author=deps.identity["name"],
                           team=deps.identity["team"], created_at=stamp(current), valid_until=stamp(current + VALIDITY),
                           confidence=0.8)


def store_clock(store: MemoryStore) -> datetime:
    """Default time for operator commands between runs: just after the latest thing the store recorded.

    Memory lives on the simulated exchange clock; the wall clock would date a correction after every scenario
    and recall (created no later than now) would never return it."""
    moments = [record.created_at for record in store.all()] + [entry["deleted_at"] for entry in store.deletions()]
    if not moments:
        raise ValueError("The memory store is empty: give the time explicitly")
    return max(datetime.fromisoformat(moment) for moment in moments) + timedelta(minutes=1)


def _operator_may_change(store: MemoryStore, memory_id: str, operator: dict, verb: str) -> MemoryRecord:
    record = store.get(memory_id)
    if operator["role"] == "first-line":
        raise PermissionError(f"Only a person may {verb} memory; the agent's identity may not")
    if record.team != operator["team"]:
        raise PermissionError(f"Cannot {verb} another team's memory")
    return record


def correct(store: MemoryStore, memory_id: str, content: str, source_ref: str, *, operator: dict,
            at: datetime) -> MemoryRecord:
    """Write a sourced replacement (user source, confidence 0.9) and supersede the old record."""
    previous = _operator_may_change(store, memory_id, operator, "correct")
    if previous.status != "active":
        raise ValueError(f"{memory_id} is {previous.status}; correct the record that replaced it")
    return store.add(kind=previous.kind, subject=previous.subject, content=content, source_type="user",
                     source_ref=source_ref, author=operator["name"], team=previous.team, created_at=stamp(at),
                     valid_until=stamp(at + VALIDITY), confidence=0.9, supersedes=memory_id)


def forget(store: MemoryStore, memory_id: str, reason: str, *, operator: dict, at: datetime) -> bool:
    """Delete the content; the store keeps who, when and why."""
    _operator_may_change(store, memory_id, operator, "forget")
    return store.delete(memory_id, deleted_at=stamp(at), deleted_by=operator["name"], reason=reason)
