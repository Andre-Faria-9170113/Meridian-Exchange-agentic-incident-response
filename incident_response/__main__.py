"""Command line.

    python -m incident_response run --scenario cases/s03-alert-and-ticket.yaml --run-dir runs/demo
    python -m incident_response run --mode llm --scenario ... --run-dir ...
    python -m incident_response resume --run-dir runs/demo [--role on-call]

Exit codes: 0 recovered, resolved or paused; 2 escalated, refused, not recovered or insufficient
information (often the correct outcome of a failure case).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .workflow import PAUSE_POINTS, run

ROLES = ["first-line", "on-call", "incident-manager", "settlement-analyst"]
ROOT = Path(__file__).resolve().parents[1]


def model_name() -> str:
    return f"openai:{os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}"


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

    again = commands.add_parser("resume", help="Continue a paused or interrupted run")
    again.add_argument("--run-dir", type=Path, required=True)
    again.add_argument("--role", choices=ROLES, help="Act as another identity from now on (authority is re-checked)")

    args = parser.parse_args()
    if args.command == "run":
        if args.mode == "llm" and not os.getenv("OPENAI_API_KEY"):
            parser.error("OPENAI_API_KEY is missing; copy .env.example to .env and set it")
        result = asyncio.run(run(args.scenario, args.run_dir, mode=args.mode, model=model_name(),
                                 coordination=args.coordination, role=args.role, pause_after=args.pause_after,
                                 memory_path=args.memory))
    else:
        saved = json.loads((args.run_dir / "checkpoint.json").read_text(encoding="utf-8"))
        if saved["mode"] == "llm" and not os.getenv("OPENAI_API_KEY"):
            parser.error("OPENAI_API_KEY is missing; this run uses a model")
        result = asyncio.run(run(None, args.run_dir, model=saved["model"], resume=True, role=args.role))
    print(json.dumps(result, indent=2))
    if result["status"] not in {"recovered", "resolved", "paused"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
