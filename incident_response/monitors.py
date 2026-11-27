"""Monitors over a finished run's journal (session 8: silent failures show up in traces, not in exceptions).

They read only what was recorded: the gateway's journal (`events`), the calls the specialists' gate refused
(`limited_calls`), the executor's audit and the approval service's records, the report and the usage. They
change nothing and decide nothing. They check, independently of the code that acted, that:

- repeated_work: no specialist ran the same read twice within one attempt (a correction re-reads on purpose:
  the world has moved on), and how often a repeat had to be refused (going round in circles);
- circling: reads refused as outside the specialist's scope (from the third in a run), a specialist asked more often than one answer and one
  follow-up per round, and orchestrator questions refused for that reason;
- approval: every applied action has an approved approval for exactly that action and target, still valid
  when the action ran (15 minutes, not across the session opening);
- repeated_effect: no action was applied twice to the same target;
- unverified_claim: a recovered or resolved report has a metrics read after the last action;
- budget: model requests and tokens against the run's limits, and reads refused for budget.

Each alert has a severity: "critical" means a rule the code enforces was broken (a defect); "warning" means
waste or a run close to a limit.
"""
from __future__ import annotations

import json
from collections import Counter

from .agents import LIMITS
from .policy import APPROVAL_TTL_MINUTES

MUTATIONS = {"restart_instance", "rollback_change"}
# One stray read outside the scope happened in most milestone-3.1 runs; alerting on it hid the run with 20
SCOPE_REFUSALS = 3


def watch(data: dict, trading_session=None) -> dict:
    """`trading_session(tick) -> bool`, from the simulated clock, for the session-opening rule (optional)."""
    alerts: list[dict] = []

    def alert(monitor: str, severity: str, detail: str) -> None:
        alerts.append({"monitor": monitor, "severity": severity, "detail": detail})

    events = data.get("events", [])
    boundaries = [attempt.get("events_before_correction", 0) for attempt in data.get("attempts", [])]
    reads = [(sum(i >= b for b in boundaries), event) for i, event in enumerate(events)
             if event["caller"] != "harness" and event.get("attempt", 1) == 1]
    repeats = Counter((attempt, event["caller"], event["tool"], json.dumps(event["args"], sort_keys=True))
                      for attempt, event in reads)
    for (_, caller, tool, args), count in repeats.items():
        if count > 1:
            alert("repeated_work", "warning", f"{caller} ran {tool} {args} {count} times")
    limited = Counter((call["caller"], call["reason"]) for call in data.get("limited_calls", []))
    for (caller, reason), count in sorted(limited.items()):
        if reason == "repeated":
            alert("repeated_work", "warning", f"{caller} tried {count} repeated call(s); refused without touching the systems")

    for (caller, reason), count in sorted(limited.items()):
        if reason == "scope" and count >= SCOPE_REFUSALS:
            alert("circling", "warning", f"{caller} tried {count} read(s) outside its scope; refused")
        if reason == "asked_again":
            alert("circling", "warning", f"{caller} asked a specialist again {count} time(s) past the limit; refused")
    rounds = 1 + len(data.get("attempts", []))
    for agent, answers in (data.get("model_messages") or {}).items():
        if agent != "orchestrator" and isinstance(answers, list) and len(answers) > 2 * rounds:
            alert("circling", "warning", f"{agent} answered {len(answers)} times in {rounds} round(s)")

    approvals = {record["approval_ref"]: record for record in data.get("approvals", [])}
    applied = [record for record in data.get("actions", []) if record.get("outcome") == "completed"]
    for record in applied:
        what = f"{record['action']} {record['target']} ({record['action_id']})"
        approval = approvals.get(record.get("confirmation_ref"))
        if approval is None or approval["status"] != "approved":
            alert("approval", "critical", f"{what} ran without an approved approval")
            continue
        if (approval["action"], approval["target"]) != (record["action"], record["target"]):
            alert("approval", "critical", f"{what} ran on {approval['approval_ref']}, which approves something else")
        age = record["tick"] - approval["tick"]
        if age > APPROVAL_TTL_MINUTES:
            alert("approval", "critical", f"{what} ran on {approval['approval_ref']} given {age} minutes earlier")
        if trading_session and trading_session(record["tick"]) and not trading_session(approval["tick"]):
            alert("approval", "critical", f"{what} ran in the session on an approval given before it opened")
    for (action, target), count in Counter((r["action"], r["target"]) for r in applied).items():
        if count > 1:
            alert("repeated_effect", "critical", f"{action} {target} was applied {count} times")

    status = (data.get("report") or {}).get("status")
    last_mutation = max((i for i, event in enumerate(events) if event["tool"] in MUTATIONS), default=None)
    if status in {"recovered", "resolved"}:
        after = events[last_mutation + 1:] if last_mutation is not None else events
        if not any(event["tool"] == "read_metrics" and event["caller"] == "harness" and "error" not in event.get("result", {})
                   for event in after):
            alert("unverified_claim", "critical", f"report says {status} with no metrics read after the last action")

    usage = data.get("usage") or {}
    requests, tokens = usage.get("requests", 0), usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    if requests >= 0.8 * LIMITS.request_limit:
        alert("budget", "warning", f"{requests} model requests of {LIMITS.request_limit}")
    if tokens >= 0.8 * LIMITS.total_tokens_limit:
        alert("budget", "warning", f"{tokens} tokens of {LIMITS.total_tokens_limit}")
    for (caller, reason), count in sorted(limited.items()):
        if reason == "budget":
            alert("budget", "warning", f"{caller} asked for {count} read(s) beyond its budget")

    reads_by = Counter(event["caller"] for _, event in reads)
    return {"alerts": alerts,
            "counts": {"critical": sum(a["severity"] == "critical" for a in alerts),
                       "warning": sum(a["severity"] == "warning" for a in alerts)},
            "stats": {"reads": dict(reads_by), "refused_calls": dict(Counter(c["reason"] for c in data.get("limited_calls", []))),
                      "model_requests": requests, "tokens": tokens, "effects": len(applied),
                      "corrections": len(data.get("attempts", []))}}
