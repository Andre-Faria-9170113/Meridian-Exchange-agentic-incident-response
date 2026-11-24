import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .state import Checkpoint
from .workflow import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Meridian incident-response starter")
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--run-dir", type=Path, default=Path("runs/demo"))
    parser.add_argument("--mode", choices=["fixture", "llm"], default="fixture")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--role", choices=["first-line", "on-call", "incident-manager", "settlement-analyst"])
    parser.add_argument("--pause-after", choices=["plan", "action"])
    parser.add_argument("--memory", type=Path, help="Shared SQLite file; defaults to <run-dir parent>/memory.db")
    args = parser.parse_args()
    if not args.resume and args.scenario is None:
        parser.error("give --scenario for a new run")
    load_dotenv(Path.cwd() / ".env")
    mode = args.mode
    saved_model = None
    if args.resume:
        checkpoint = Checkpoint(args.run_dir)
        checkpoint.load()
        mode = checkpoint.data["mode"]
        saved_model = checkpoint.data["model"]
    if mode == "llm" and not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is missing; copy .env.example to .env and set it")
    model = saved_model or f"openai:{os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}"
    result = asyncio.run(run(args.scenario, args.run_dir, mode=mode, model=model, resume=args.resume,
                             role=args.role, pause_after=args.pause_after, memory_path=args.memory))
    print(json.dumps(result, indent=2))
    if result["status"] in {"insufficient_information", "refused", "not_recovered"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
