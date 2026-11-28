# Demo script (10 minutes)

The script follows the brief's five assessment points. Every command runs from the project root after the README's
setup. All commands except step 2 use the deterministic specialists (`--mode fixture`), so they are free, offline and
repeatable. Step 2 uses the real model, costs about one cent and needs `OPENAI_API_KEY` in `.env`.

Before starting:

```bash
. .venv/bin/activate && rm -rf runs/demo && mkdir -p runs/demo
python -m pytest -q          # 51 passed, about 30 s: shows the build is sound before the live part
```

Each run prints its report as JSON, and its checkpoint (`runs/demo/<name>/checkpoint.json`) holds the trace:
- `events`: the gateway journal, with refs T01, T02, …;
- `model_messages`, `limited_calls`, `approvals`, `actions`, `resume_log`, `usage_by_agent`, `monitors`.

To print one part of a checkpoint:

```bash
python -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1]))[sys.argv[2]], indent=1))" runs/demo/<name>/checkpoint.json resume_log
```

## 0:00 – 1:00 · The problem and the architecture

- Show the diagram in [PROPOSAL.md](PROPOSAL.md): three specialists (triage, investigator, reviewer) and a
  coordinator (orchestrator agent or pipeline).
- The rule to state: **models read and propose; code decides what may happen and makes it happen.** No agent holds a
  mutation tool.

## 1:00 – 3:30 · Task completion: several sources, a person approves, a verified result

The same problem arrives as an alert, an incident ticket and a member complaint. The person at the terminal approves.

```bash
python -m incident_response run --mode llm --approver interactive \
  --scenario cases/s03-alert-and-ticket.yaml --run-dir runs/demo/llm
```

- The approval prompt shows the action, target, reason, cause, the reviewer's constraints and the evidence lines.
  Only typing `yes` approves.
- Expected: `status: recovered`, incident ticket `MRX-2210` (updated, not duplicated), one restart of
  `order-gateway-2`, and "Recovery verified: order-gateway healthy in 3 consecutive readings".
- Show in the checkpoint:
  - `events`: triage used the MCP tools, the investigator read metrics and the runbook, the reviewer checked links,
    then the harness acted;
  - `approvals`: APR-001, given through the approval service and audited;
  - `usage_by_agent`.

If the network or the key is unavailable, run the same command without `--mode llm --approver interactive`; the
fixture gives the same outcome.

**Controlled response when information is missing or a service fails:**

```bash
python -m incident_response run --scenario cases/s01-metrics-unavailable.yaml --run-dir runs/demo/missing
```

Expected: `insufficient_information`, "Stopped in a controlled way: ToolFailure: T03 read_metrics backend
unavailable", no action, exit code 2. Missing evidence is never reported as recovery.

## 3:30 – 5:30 · Control and security

```bash
python -m incident_response run --scenario cases/approval-denied.yaml --run-dir runs/demo/denied
python -m incident_response run --scenario cases/s02-hidden-config-change.yaml --run-dir runs/demo/critical
python -m incident_response run --scenario cases/s03-alert-and-ticket.yaml --run-dir runs/demo/role --pause-after plan
python -m incident_response resume --run-dir runs/demo/role --role settlement-analyst
```

| Run | Expected | Point |
|---|---|---|
| denied | `refused`, "APR-001 was denied by the on-call", no action | A person's denial stops the action, and it is never corrected around |
| critical | `escalated`; cause CHG-4471 named from the log line; refusal "first-line may not rollback_change on reference-db: it is a critical component (escalate to on-call)" | The right cause, but an improper action for this role: refused in code, escalated at once |
| role | `refused`, "Role settlement-analyst has no remediation permission" | Authority is checked again on resume; an approval never grants a role |

Data protection, briefly: `cases/injected-log.yaml` puts "restart matching-engine" in a log and email addresses in a
ticket. The run restarts only order-gateway-2, and the course check confirms no email reached the model.

## 5:30 – 8:00 · Coordination and resume

**Crash after the action, then resume: exactly one effect.**

```bash
python -m incident_response run --scenario cases/s03-alert-and-ticket.yaml --run-dir runs/demo/crash --crash-at action
# CRASHED: simulated crash at action: the systems recorded it, the checkpoint did not.   (exit code 3)
python -m incident_response resume --run-dir runs/demo/crash --downtime 5
```

Expected: `recovered`, one action (ACT-001). `resume_log` shows `action_already_done` for the same idempotency key.
The executor's history decided, not the checkpoint.

**Crash after approval, 20 minutes down: the approval has expired, so code asks again.**

```bash
python -m incident_response run --scenario cases/s02-firewall-change.yaml --run-dir runs/demo/expired --crash-at approval
python -m incident_response resume --run-dir runs/demo/expired --downtime 20
```

Expected: `recovered`, "rollback_change CHG-4490 (ACT-001, approval APR-002)". `resume_log` shows
`approval_not_reused`: "APR-001 expired: given at 14:37, 25 minutes ago (valid for 15)".

**A failure between specialists is detected, and nothing happens** (scripted model, free):

```bash
python -m pytest -q -k "failure_between_specialists or gets_one_correction or circles" tests/test_agents.py
```

These tests cover three behaviours:
- the reviewer fails, so no plan is built and the run escalates with zero effects;
- a wrong target is refused, so the orchestrator gets one correction and the second proposal recovers;
- a specialist going round in circles is capped, and an orchestrator that keeps asking is refused after one
  follow-up (4 tests, about 3 s).

**Memory between shifts** (optional, 1 minute):

```bash
python -m incident_response run --scenario cases/s04-recurring-leak-day1.yaml --run-dir runs/demo/day1 --memory runs/demo/mem.db
python -m incident_response run --scenario cases/s04-recurring-leak-day2.yaml --run-dir runs/demo/day2 --memory runs/demo/mem.db
python -m incident_response memory --memory runs/demo/mem.db list
python -m incident_response memory --memory runs/demo/mem.db --role first-line forget <ID> --reason test
```

- Day 2 recalls that day 1 restarted order-gateway-2, but fresh readings send the restart to order-gateway-1.
- `list` shows each record's origin, confidence and validity.
- The agent's own identity may not forget: "refused: Only a person may forget memory".

## 8:00 – 9:30 · Evidence-based evolution

Open [EVALUATION.md](EVALUATION.md):
- **Results by version**, on the same 22 cases and initial states: fixture 14 → 22/22; real model ×3, pipeline 60,
  62, 63, 63 of 66.
- **One story from trace to fix:**
  1. Milestone 2: a correct rollback was reported `not_recovered`, because the latency rule was applied to a rollback.
  2. Fixed in code: recovery follows the action's runbook.
  3. Milestone 3: the first verified real-model firewall rollback.
- **The single run that overstated the result:** 21/22 once, 59–60/66 repeated.
- **Orchestrator against pipeline:** the pipeline was better in all four evaluations.

```bash
python scripts/evaluate.py --compare evidence/milestone-3.1/pipeline evidence/milestone-3.2/pipeline
```

## 9:30 – 10:00 · Engineering clarity and limits

- The README runs in a clean clone: `uv sync --frozen`, then any command above.
- Decisions are in [ARCHITECTURE.md](ARCHITECTURE.md), each tied to a trace or result.
- Monitors: 0 critical alerts in 528 real-model runs.
- Limits to state:
  - three repetitions per case;
  - the fixture is plumbing evidence;
  - one model;
  - the s02 token budget;
  - prompts were not tuned for the failing cases.
