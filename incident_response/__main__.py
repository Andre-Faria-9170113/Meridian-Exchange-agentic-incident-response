"""Command line.

    python -m incident_response run --scenario cases/s03-alert-and-ticket.yaml --run-dir runs/demo
    python -m incident_response run --mode llm --scenario ... --run-dir ...
    python -m incident_response resume --run-dir runs/demo [--role on-call]
    python -m incident_response memory --memory runs/memory.db list|correct|forget ...

Exit codes: 0 recovered, resolved or paused; 2 escalated, refused, not recovered or insufficient
information (often the correct outcome of a failure case).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from meridian.agent_runtime import identity_for
from meridian.memory import MemoryStore

from .memory import correct, forget, store_clock
from .workflow import PAUSE_POINTS, run

ROLES = ["first-line", "on-call", "incident-manager", "settlement-analyst"]
ROOT = Path(__file__).resolve().parents[1]
APPROVERS = ["scenario", "interactive"]
APPROVER_HELP = "Who answers approval requests: the scenario's simulated approver, or a person at this terminal"


def model_name() -> str:
    return f"openai:{os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}"


def terminal_approver(request: dict) -> bool:
    """A person decides at the terminal. Only an explicit yes approves; anything else, or no input, denies."""
    print("\n" + "=" * 72, file=sys.stderr)
    print(f"APPROVAL NEEDED ({request['time']}) from the {request['approver_role']}", file=sys.stderr)
    print(f"  action : {request['action']}\n  target : {request['target']}", file=sys.stderr)
    print(f"  reason : {request['reason']}\n  cause  : {request['cause']}", file=sys.stderr)
    if request["reviewer"]:
        review = request["reviewer"]
        print(f"  review : safe_to_attempt={review['safe_to_attempt']}; " + "; ".join(review["constraints"]), file=sys.stderr)
    print("  evidence:", file=sys.stderr)
    for line in request["evidence"]:
        print(f"    {line}", file=sys.stderr)
    print("Code already re-read fresh metrics and checked authority; it verifies recovery after acting.", file=sys.stderr)
    try:
        answer = input(f"Approve {request['action']} {request['target']}? Type 'yes' to approve: ")
    except EOFError:
        answer = ""
    print("=" * 72, file=sys.stderr)
    return answer.strip().lower() == "yes"


def memory_command(args: argparse.Namespace) -> None:
    if not args.memory.exists():
        raise ValueError(f"{args.memory} does not exist")
    store, operator = MemoryStore(args.memory), identity_for(args.role)
    if args.operation == "list":
        records = [r for r in store.all() if r.team == operator["team"] and (args.all or r.status == "active")]
        print(f"{len(records)} record(s) of team {operator['team']} in {args.memory}")
        for r in records:
            replaced = f" (superseded by {', '.join(x.memory_id for x in store.all() if x.supersedes == r.memory_id)})" \
                if r.status == "superseded" else ""
            print(f"\n{r.memory_id}  {r.status}{replaced}  subject={r.subject}  confidence={r.confidence}  "
                  f"valid_until={r.valid_until}")
            print(f"  origin: {r.source_type} {r.source_ref}, by {r.author} at {r.created_at}"
                  + (f", corrects {r.supersedes}" if r.supersedes else ""))
            print(f"  {r.content}")
        if args.all:
            for entry in store.deletions():
                print(f"\ndeleted {entry['memory_id']} by {entry['deleted_by']} at {entry['deleted_at']}: {entry['reason']}")
        return
    at = args.at or store_clock(store)
    if args.operation == "correct":
        record = correct(store, args.memory_id, args.text, args.source, operator=operator, at=at)
        print(f"{record.memory_id} replaces {args.memory_id} (by {operator['name']} at {record.created_at}, "
              f"valid until {record.valid_until})")
    else:
        forget(store, args.memory_id, args.reason, operator=operator, at=at)
        print(f"{args.memory_id} deleted by {operator['name']} at {at:%Y-%m-%d %H:%M}; the deletion log keeps why")


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(prog="python -m incident_response", description="Meridian incident response")
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("run", help="Handle a new incident")
    start.add_argument("--scenario", type=Path, required=True)
    start.add_argument("--run-dir", type=Path, required=True)
    start.add_argument("--mode", choices=["fixture", "llm"], default="fixture",
                       help="fixture: deterministic specialists, no model; llm: model-backed specialists")
    start.add_argument("--coordination", choices=["orchestrator", "pipeline"], default="orchestrator",
                       help="llm mode: an orchestrator agent decides, or a fixed pipeline in code")
    start.add_argument("--role", choices=ROLES, help="Identity to act as (default: the scenario's actor)")
    start.add_argument("--pause-after", choices=PAUSE_POINTS)
    start.add_argument("--memory", type=Path, help="Memory SQLite file (default: <run-dir parent>/memory.db)")
    start.add_argument("--approver", choices=APPROVERS, default="scenario", help=APPROVER_HELP)

    again = commands.add_parser("resume", help="Continue a paused or interrupted run")
    again.add_argument("--run-dir", type=Path, required=True)
    again.add_argument("--role", choices=ROLES, help="Act as another identity from now on (authority is re-checked)")
    again.add_argument("--approver", choices=APPROVERS, default="scenario", help=APPROVER_HELP)

    memory = commands.add_parser("memory", help="Operator commands on the memory store (between runs)")
    memory.add_argument("--memory", type=Path, required=True, help="Memory SQLite file, e.g. runs/memory.db")
    memory.add_argument("--role", choices=ROLES, default="on-call", help="Operator identity (default: on-call)")
    memory.add_argument("--at", type=datetime.fromisoformat,
                        help="Simulated time of the change (default: one minute after the store's latest entry)")
    operations = memory.add_subparsers(dest="operation", required=True)
    listing = operations.add_parser("list", help="Records of the operator's team")
    listing.add_argument("--all", action="store_true", help="Include superseded records and the deletion log")
    fix = operations.add_parser("correct", help="Replace a record with a sourced correction")
    fix.add_argument("memory_id")
    fix.add_argument("--text", required=True, help="The corrected content")
    fix.add_argument("--source", required=True, help="Where the correction comes from, e.g. 'ticket MRX-2210'")
    drop = operations.add_parser("forget", help="Delete a record's content, keeping who, when and why")
    drop.add_argument("memory_id")
    drop.add_argument("--reason", required=True)

    args = parser.parse_args()
    if args.command == "memory":
        try:
            memory_command(args)
        except (KeyError, PermissionError, ValueError) as error:
            raise SystemExit(f"refused: {error}") from None
        return
    approver = terminal_approver if args.approver == "interactive" else None
    if approver and not sys.stdin.isatty():
        parser.error("--approver interactive needs a terminal")
    if args.command == "run":
        if args.mode == "llm" and not os.getenv("OPENAI_API_KEY"):
            parser.error("OPENAI_API_KEY is missing; copy .env.example to .env and set it")
        result = asyncio.run(run(args.scenario, args.run_dir, mode=args.mode, model=model_name(),
                                 coordination=args.coordination, role=args.role, pause_after=args.pause_after,
                                 memory_path=args.memory, approver=approver))
    else:
        saved = json.loads((args.run_dir / "checkpoint.json").read_text(encoding="utf-8"))
        if saved["mode"] == "llm" and not os.getenv("OPENAI_API_KEY"):
            parser.error("OPENAI_API_KEY is missing; this run uses a model")
        result = asyncio.run(run(None, args.run_dir, model=saved["model"], resume=True, role=args.role, approver=approver))
    print(json.dumps(result, indent=2))
    if result["status"] not in {"recovered", "resolved", "paused"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
