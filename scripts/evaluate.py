"""Run every case from a clean initial state and score it with the course's own checks.

    python scripts/evaluate.py --output runs/eval-fixture
    python scripts/evaluate.py --mode llm --repeat 3 --output runs/eval-llm
    python scripts/evaluate.py --compare runs/eval-a runs/eval-b

Each case in cases/ that has a checks/<id>.yaml is run in a fresh directory with a fresh
memory database (except the ordered day-1/day-2 sequence, which shares one on purpose).
The check files use the course format and are applied with the supplied meridian.evaluate:
the report claim, required reads, forbidden and maximum effects, ticket updates, memory
contents, personal data in model input, token budget and recovery held for several ticks.
Expectations never reach the agents.
"""
from __future__ import annotations

import argparse
import asyncio
import fnmatch
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from incident_response import __version__  # noqa: E402
from incident_response.workflow import run  # noqa: E402
from meridian.evaluate import evaluate  # noqa: E402
from meridian.memory import MemoryStore  # noqa: E402
from meridian.scenarios import load_solution  # noqa: E402

# Cases that must run in order and share one memory database (cross-run memory).
SEQUENCES = [["s04-recurring-leak-day1", "s04-recurring-leak-day2"]]


def git_revision() -> str:
    try:
        revision = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return revision + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def discover(patterns: list[str] | None) -> list[list[str]]:
    """Groups of case ids: a group is one case, or an ordered sequence sharing memory."""
    ids = sorted(path.stem for path in (ROOT / "cases").glob("*.yaml") if (ROOT / "checks" / path.name).is_file())
    if patterns:
        ids = [case for case in ids if any(fnmatch.fnmatch(case, pattern) for pattern in patterns)]
    groups, grouped = [], set()
    for sequence in SEQUENCES:
        present = [case for case in sequence if case in ids]
        if present:
            groups.append(present)
            grouped.update(present)
    groups += [[case] for case in ids if case not in grouped]
    return sorted(groups, key=lambda group: group[0])


def model_input_text(state: dict) -> str:
    messages = state.get("model_messages") or {}
    return "\n".join(value if isinstance(value, str) else json.dumps(value) for value in messages.values())


async def run_case(case: str, directory: Path, memory_path: Path, args) -> dict:
    observed = {}
    started = time.perf_counter()
    error = None
    try:
        report = await run(ROOT / "cases" / f"{case}.yaml", directory, mode=args.mode, model=args.model,
                           coordination=args.coordination, memory_path=memory_path, observe=lambda tools: observed.setdefault("tools", tools))
    except Exception as exc:  # noqa: BLE001 - a crash is a result to record, not a reason to stop the suite
        report, error = {"status": "crashed", "summary": f"{type(exc).__name__}: {exc}"}, f"{type(exc).__name__}: {exc}"
    seconds = round(time.perf_counter() - started, 2)
    checkpoint = directory / "checkpoint.json"
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.is_file() else {}
    usage = state.get("usage") or {}
    tools = observed.get("tools")
    checks = []
    if tools is not None:
        result = evaluate(tools.sim, tools.trace, report, load_solution(ROOT / "checks" / f"{case}.yaml"),
                          memory=MemoryStore(memory_path), model_input=model_input_text(state),
                          input_tokens=usage.get("input_tokens"))
        checks = [{"name": check.name, "passed": check.passed, "detail": check.detail} for check in result.checks]
        effects = [f"{record.action} {record.target}" for record in tools.sim.executor.effects()]
        tool_calls = len(tools.trace)
    else:
        effects, tool_calls = [], 0
    passed = error is None and bool(checks) and all(check["passed"] for check in checks)
    monitors = state.get("monitors") or {}
    return {"monitors": monitors.get("counts", {}), "monitor_alerts": monitors.get("alerts", []),
            "corrections": len(state.get("attempts", [])), "case": case, "passed": passed, "status": report.get("status"), "effects": effects,
            "failed_checks": [f"{c['name']}: {c['detail']}" for c in checks if not c["passed"]], "checks": checks,
            "error": error, "tool_calls": tool_calls, "model_requests": usage.get("requests", 0),
            "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0),
            "usage_by_agent": state.get("usage_by_agent", {}), "models_used": state.get("models_used", {}),
            "seconds": seconds, "run_dir": str(directory)}


async def evaluate_suite(args) -> dict:
    rows = []
    for repetition in range(1, args.repeat + 1):
        for group in discover(args.cases):
            memory_path = args.output / f"{group[0]}-r{repetition}" / "memory.db" if len(group) > 1 else None
            for case in group:
                directory = args.output / f"{case}-r{repetition}"
                row = await run_case(case, directory, memory_path or directory / "memory.db", args)
                row["repetition"] = repetition
                rows.append(row)
                mark = "PASS" if row["passed"] else "FAIL"
                print(f"[{mark}] {case} r{repetition}: status={row['status']} effects={row['effects']}"
                      + (f" | {'; '.join(row['failed_checks'])[:200]}" if row["failed_checks"] else "")
                      + (f" | {row['error']}" if row["error"] else "")
                      + "".join(f" | monitor {a['severity']}: {a['detail']}" for a in row["monitor_alerts"]), flush=True)
    return {"meta": {"git_revision": git_revision(), "version": __version__, "mode": args.mode,
                     "model": args.model if args.mode == "llm" else "none (deterministic fixture)",
                     "coordination": args.coordination if args.mode == "llm" else "pipeline (deterministic rules)",
                     "repeat": args.repeat, "python": platform.python_version(),
                     "date": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            "rows": rows}


def summarize(results: dict) -> dict[str, dict]:
    by_case: dict[str, dict] = {}
    for row in results["rows"]:
        entry = by_case.setdefault(row["case"], {"runs": 0, "passed": 0, "statuses": [], "tokens": 0, "requests": 0,
                                                  "critical": 0, "warning": 0, "corrections": 0})
        entry["runs"] += 1
        entry["passed"] += row["passed"]
        entry["statuses"].append(row["status"])
        entry["tokens"] += row["input_tokens"] + row["output_tokens"]
        entry["requests"] += row["model_requests"]
        for key in ("critical", "warning"):
            entry[key] += (row.get("monitors") or {}).get(key, 0)
        entry["corrections"] += row.get("corrections", 0)
    return by_case


def markdown(results: dict) -> str:
    meta, by_case = results["meta"], summarize(results)
    total_runs = sum(entry["runs"] for entry in by_case.values())
    total_passed = sum(entry["passed"] for entry in by_case.values())
    lines = [f"# Evaluation — {meta['git_revision']} ({meta['mode']})", "",
             f"Model: {meta['model']} · coordination: {coordination_of(meta)} · "
             f"repetitions: {meta['repeat']} · Python {meta['python']} · {meta['date']}", "",
             f"**{total_passed}/{total_runs} runs passed every check.** Monitors: "
             f"{sum(e['critical'] for e in by_case.values())} critical, {sum(e['warning'] for e in by_case.values())} "
             "warning alerts (see `monitor_alerts` in results.json).", "",
             "| Case | Passed | Statuses | Model requests | Tokens | Corrections | Monitor alerts (critical/warning) "
             "| Failed checks (first run that failed) |",
             "|---|---|---|---|---|---|---|---|"]
    for case, entry in sorted(by_case.items()):
        failed = next((row["failed_checks"] or [row["error"]] for row in results["rows"] if row["case"] == case and not row["passed"]), [])
        failed_text = "; ".join(str(item) for item in failed).replace("|", "\\|")[:180]
        lines.append(f"| {case} | {entry['passed']}/{entry['runs']} | {', '.join(sorted(set(map(str, entry['statuses']))))} "
                     f"| {entry['requests']} | {entry['tokens']} | {entry['corrections']} "
                     f"| {entry['critical']}/{entry['warning']} | {failed_text} |")
    return "\n".join(lines) + "\n"


def coordination_of(meta: dict) -> str:
    """Results recorded before the option existed: fixture runs used the rule pipeline, LLM runs the orchestrator."""
    return meta.get("coordination") or ("pipeline (deterministic rules)" if meta["mode"] == "fixture" else "orchestrator")


def described(meta: dict) -> str:
    return f"{meta['mode']}, {meta['model']}, {coordination_of(meta)}, x{meta['repeat']}"


def compare(baseline_dir: Path, candidate_dir: Path) -> str:
    baseline = json.loads((baseline_dir / "results.json").read_text(encoding="utf-8"))
    candidate = json.loads((candidate_dir / "results.json").read_text(encoding="utf-8"))
    before, after = summarize(baseline), summarize(candidate)
    lines = [f"# Comparison: {baseline['meta']['git_revision']} → {candidate['meta']['git_revision']}", "",
             f"Baseline: {baseline_dir} ({described(baseline['meta'])})  ",
             f"Candidate: {candidate_dir} ({described(candidate['meta'])})", "",
             "| Case | Baseline | Candidate | Change |", "|---|---|---|---|"]
    counts = {"improved": 0, "regressed": 0, "unchanged": 0}
    for case in sorted(set(before) | set(after)):
        old, new = before.get(case), after.get(case)
        old_rate = old["passed"] / old["runs"] if old else None
        new_rate = new["passed"] / new["runs"] if new else None
        if old_rate is None or new_rate is None:
            change = "new case" if old_rate is None else "removed"
        elif new_rate > old_rate:
            change, counts["improved"] = "improved", counts["improved"] + 1
        elif new_rate < old_rate:
            change, counts["regressed"] = "**regressed**", counts["regressed"] + 1
        else:
            change, counts["unchanged"] = "", counts["unchanged"] + 1
        fmt = lambda entry: f"{entry['passed']}/{entry['runs']}" if entry else "—"  # noqa: E731
        lines.append(f"| {case} | {fmt(old)} | {fmt(new)} | {change} |")
    lines += ["", f"Improved {counts['improved']}, regressed {counts['regressed']}, unchanged {counts['unchanged']}."]
    return "\n".join(lines) + "\n"


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, help="Fresh directory for this experiment")
    parser.add_argument("--mode", choices=["fixture", "llm"], default="fixture")
    parser.add_argument("--model", default=f"openai:{os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--coordination", choices=["orchestrator", "pipeline"], default="orchestrator",
                        help="llm mode: an orchestrator agent decides, or a fixed pipeline in code")
    parser.add_argument("--cases", nargs="*", help="Glob patterns of case ids, e.g. 's03-*'")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BASELINE", "CANDIDATE"))
    args = parser.parse_args()
    if args.compare:
        text = compare(*args.compare)
        print(text)
        return 0
    if args.output is None:
        parser.error("--output is required (or use --compare)")
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    if args.output.exists():
        parser.error("Use a new --output directory for an independent experiment")
    if args.mode == "llm" and not os.getenv("OPENAI_API_KEY"):
        parser.error("Set OPENAI_API_KEY in .env for LLM evaluation")
    results = asyncio.run(evaluate_suite(args))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (args.output / "results.md").write_text(markdown(results), encoding="utf-8")
    print("\n" + markdown(results))
    return 0 if all(row["passed"] for row in results["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
