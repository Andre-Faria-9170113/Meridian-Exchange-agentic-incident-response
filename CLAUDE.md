# Working notes for Claude Code

This file is the plan and context for continuing this project in a new workspace. Read it first.

## The project

- Course 2 final project, *Agentic AI: Da Arquitetura à Implementação* (trainer: Luís Noronha). Common proposal:
  incident response for the fictional **Meridian Exchange**.
- **Deadline: 30 November 2026, 23:59.**
- Repository: https://github.com/Andre-Faria-9170113/Meridian-Exchange-agentic-incident-response. The evaluator
  confirmed a public repository is fine.
- The brief (`Projeto Agentic AI.pdf`) and the slides for sessions 1–9 stayed in the original course workspace. Their
  essentials are summarised below.

### What the brief requires

Minimum capabilities:
- **Main flow:** end to end from request to verified result, with selected context. A controlled response when
  information is missing, an output is invalid or a service fails.
- **Tools and MCP:** clear tool contracts and a working MCP integration that selects which capabilities are exposed.
  Structured outputs are validated in code before the next step uses them.
- **Memory:** state between runs, with origin, validity, correction and isolation defined.
- **Coordination:** an orchestrator and at least two specialists with distinct responsibilities and integrated results.
- **Verifiable effects:** run an action (simulated is fine) and confirm its consequence before concluding or repeating.
- **Permissions:** limits enforced in code, data protected, approval for the actions that need it.
- **Resume:** persist the work, resume after an interruption, and re-validate permissions and effects already produced.
- **Data and environment:** synthetic data accepted; local data for testing external-service failures; keys only in
  `.env`.

Assessment, shown in the demo and the cases:
1. **Task completion:** a case with several sources and a verified result; a controlled response when information is
   missing or a service fails.
2. **Control and security:** an authorised action with confirmed effect, an improper action refused, data and approvals
   respected.
3. **Coordination and resume:** integrated results, a failure between specialists detected, an interruption recovered
   without repeating effects.
4. **Evidence-based evolution:** baseline and later versions compared on the same cases and initial state; new cases,
   regressions and limits identified.
5. **Engineering clarity:** runs from the README in a clean clone; architecture decisions supported by traces and
   results.

Deliverables:
- **Proposal:** problem, user, flow and diagram.
- **Repository:** code, declared dependencies and a lock, a secret-free `.env.example`, and **milestone versions**.
- **README:** setup and execution, architecture, policies, decisions, limits and demo. AI assistance is allowed and
  must be declared.
- **Cases and results:** inputs, expected and obtained results, comparisons and traces, with version, model and limits
  recorded.

Unit tests and metrics built from scratch are **not** required.

Milestones, each evolving the same system:
- **1. First-Line Incident Agent (sessions 1–3):** investigate, use tools/MCP, act within limits.
- **2. Production On-Call Agent (sessions 4–6):** memory between runs, security, repeated evaluation.
- **3. 24/7 Incident Response Center (sessions 7–9):** technical corrections, multi-agent coordination, resume.

### Course content the remaining work relies on

- **Session 7 (orchestration):** pipeline versus orchestrator. The orchestrator sends goal, context and limits, and
  decides: integrate results, ask for corrections, or finish. A person approves before an action. A reviewer checks the
  state after the action: *if recovery is not confirmed, the mitigation receives the reason and gets one correction
  attempt, followed by a new review.* This is our reading of the brief's "correções técnicas".
- **Session 8 (agents in production):**
  - A2A between teams (optional for us).
  - Silent failures found in traces and monitors: going round in circles, losing a fact between steps, repeating work,
    declaring success without verifying.
  - Durable execution: checkpoint versus executor history. After a crash, the systems' history is the truth. The same
    operation keeps the same idempotency key.
  - On resume, re-check that a saved approval is still valid. In the course lab, approvals expire after 15 minutes and
    become invalid if given before the trading session opened and used after it.
- **Session 9 (LLM and MCP gateways):**
  - Admission (budget, rate limits).
  - A cache only for the same answer, for the same customer, while still true (TTL).
  - Routing: no model, a small model or a large model.
  - Fallback: if plan B breaks a rule, wait or hand over to a person.
  - Logging of cost, trace and personal data.
  - MCP gateway: authentication, allowed tools, credentials, audit.

## State at milestone 1 (24 November 2026)

| Tag | What |
|---|---|
| `v0-starter` | Codex-generated starter, unchanged |
| `baseline` | Starter plus the evaluator with the course checks: 14/22 (fixture) |
| `milestone-1` | Agent layer rewrite: 22/22 (fixture), 26 tests |

Architecture: see the README.
- Specialists are triage, investigator and reviewer, each with its own read-only tools through `gateway.py`.
- Coordination is an orchestrator agent, or a pipeline (`--coordination`).
- `rules.py` holds the deterministic specialists (`--mode fixture`).
- Code handles authority (`policy.py`), evidence and verification (`guards.py`), and the action, the ticket update and
  memory (`workflow.py`, `memory.py`).
- The world is persisted after every call (`world.py`, `world.pkl`), apart from `checkpoint.json`.

Caveats to keep stating honestly:
- The fixture rules were written knowing the public cases. A 22/22 fixture score is plumbing evidence, not an LLM
  result.
- Real-model results so far are single runs (`--repeat 1`) on the s03 cases only. No s01, s02, s04 LLM runs yet.

## First real-model check (26 November 2026, gpt-4.1-mini)

Done. The results are in ignored `runs/` folders; the milestone 2 evidence will rerun them at a tagged revision.
- s03 suite: 2/5 at `07b7c86`, then 5/5 at `520e3be`, with 17–20 requests and 27–31k tokens per case.
- **Lesson: every tool call costs one simulated minute.** In s03, `order-gateway-2` crashes out of memory around tick
  42, so the team has about 22 reads. The model made 24–43 reads, repeating work and guessing runbook names, and
  prompts did not fix it.
- What fixed it, in code (`agents.py`):
  - a read budget per specialist answer (`READ_BUDGET`: triage 3, investigator 6, reviewer 5);
  - identical repeated calls refused;
  - tools withdrawn once the budget is spent, so the model must answer;
  - the reviewer receives the runbook the investigator cited;
  - a request cap per specialist (12);
  - failed runs kept in `model_messages`.
- Every case now uses exactly 14 reads before acting, so the budget is the binding constraint. Keep it in mind when
  the correction loop adds reads.
- Full suite: 18/22 at `c89af64`, then 19/22 at `4b39f0e`, with 0 regressions.
  - Fixed at `4b39f0e`: the investigator may read metrics only for the component triage named; a `no_fault` that its
    latest reading contradicts is rejected; changes are listed for all components; the MCP list clamp is applied
    when the size is omitted (it was letting 50 alerts through).
  - Still failing:
    - s02-firewall-change: logs searched by level, not by change id; the proof is a WARN line naming CHG-4490.
    - s04-conflicting-shift-notes: names CHG-4310, not CHG-4471, which is still active.
    - s02-hidden-config-change: finds CHG-4471, but uses 41.2k tokens against a 40k limit.
  - All three escalate safely without acting.
- Gap: triage leaves `related` empty. MEM-1187 is linked from MRX-2210, but it is no longer reported. The checks pass
  without it.

## Plan (in order)

0. **The user pushes** `main` and the tags to GitHub. Claude cannot push from here: no credentials.
1. **(Done, see above.) First real-model check.** It needs the user's OK, because it spends API credit. Run `--mode llm` on
   `s03-alert-and-ticket`, then `scripts/evaluate.py --mode llm --cases 's03-*'`. Read the traces in `checkpoint.json`
   (`model_messages`, `events`). Fix prompt and validator problems before the full suite. Watch the token budget:
   s02 checks allow at most 40,000 input tokens.
2. **Milestone 2 (sessions 4–6):**
   - Memory operator CLI: `python -m incident_response memory list|correct|forget`. `correct()` and `forget()`
     already exist in `memory.py`.
   - `--approver interactive`: a terminal prompt showing action, target, reason and evidence, so a person approves in
     the demo.
   - Show cross-shift memory: on day 2 the investigator recalls day 1, but fresh readings send the restart to
     `order-gateway-1`, not `order-gateway-2`. The evaluator already shares memory for the day-1/day-2 sequence.
   - Folded in from the first real-model check (user decision, 26 November):
     - Validator rule: an errors finding must cite a log search by change id, for the change it names or else the
       most recent active one. This mirrors `guards.evidence_refusal`.
     - Free a read by exempting `memory.recall` from the budget, only if it does not advance simulated time. Raise
       the investigator budget to 7 only if measured safe for the memory-crash deadline.
     - s04-conflicting-shift-notes: memory policy for disagreeing notes (later, user-sourced notes weigh more, and
       current state decides).
     - Trim tokens: s02-hidden-config-change uses 41.2k against a 40k limit.
     - Triage `related` gap.
   - Repeated LLM evaluation (`--repeat 3`), orchestrator versus pipeline on the same cases. Save to
     `evidence/milestone-2/` with `--compare` against the baseline and milestone 1. Record model, version, tokens and
     regressions.
   - Tag `milestone-2`.
3. **Milestone 3 (sessions 7–9):**
   - **Correction loop** in `workflow.act`. After a policy or evidence refusal (not after a person denies approval) or
     a failed verification, call `coordinator.correct(reason, (action, target))` once. `Pipeline.correct` and
     `Orchestrator.correct` already exist in `agents.py`. Then act again. At most one correction, and both attempts go
     in the report. Expected: `s02-hidden-config-change` ends `escalated` instead of `refused`.
   - **Crash and resume, as in session 8:**
     - `run --crash-at approval|action|verify` stops the process after the world was saved but before the checkpoint
       records the step. Use a `BaseException` subclass so `except Exception` does not swallow it.
     - `resume --downtime MIN` calls `tools.pass_time(MIN)` (in `world.py`) before continuing.
     - Approval validity in `policy.py`: TTL of 15 minutes, and invalid if given before the trading session opened and
       used after it. Reuse the checkpoint's approval only while it is valid; otherwise ask again.
     - Action status by idempotency key stays the source of truth.
     - Tests: a crash after the action and resume gives exactly one effect; a crash after approval plus 20 minutes of
       downtime gives a new approval.
   - **Monitors** over the journal: repeated identical calls, a mutation without approval, a recovery claim without a
     read after the action, budget use. Store them in the checkpoint and show them in the evaluator output.
   - **Session 9:**
     - Use `FallbackModel` when `OPENAI_FALLBACK_MODEL` is set.
     - Record usage per agent.
     - Document routing: the fixture is the no-model route.
     - Document `gateway.py` as the project's MCP gateway (allowlist, pins, audit, masking).
   - Tag `milestone-3`.
4. **Docs**, written in the project's voice for the evaluator:
   - The final README.
   - `docs/ARCHITECTURE.md`: decisions, policies and trace excerpts.
   - `docs/EVALUATION.md`: cases, expected versus obtained, comparisons, model and version, limits.
   - `docs/DEMO.md`: a 10-minute demo script.
   - `docs/PROPOSAL.md`: problem, user, flow and diagram.
   - **Delete** the starter's docs (`PROJECT_BRIEF.md`, `FOCUS_TOPICS.md`, `ROADMAP.md`, `VALIDATION.md`,
     `ARCHITECTURE.md`, `DEMO.md`) and `evidence/fixture-baseline/`. They are written to "the student" and contain
     errors: session 8 was *Agentes em Produção*, not security, and session 9 *was* taught (LLM and MCP gateways).
5. **Final:**
   - Test a clean clone by following the README.
   - Update the AI-assistance section.
   - Tag `final`.
   - The user pushes and checks the repository is reachable while signed out.

## Working agreements

- Ask before pushing, before real-model runs (API cost) and before deleting files the user wrote.
- Keep `meridian/`, `cases/s0*` and `checks/s0*` unchanged: they are course material.
- Commit per logical step. A milestone tag marks a runnable, tested state with evidence in `evidence/<tag>/`.
- Produce evidence at a clean revision: commit the code first, then run the evaluator, then commit the results.
- Never commit `.env` or `runs/`. Check `git status` before each commit.

## Commands

```bash
uv sync --frozen --python 3.10 && . .venv/bin/activate   # uv.lock is the source of truth
uv lock && uv export --frozen --format requirements-txt -o requirements.lock   # after changing pyproject.toml
python -m pytest -q
python scripts/evaluate.py --output runs/eval-x [--mode llm --repeat 3] [--cases 's03-*']
python scripts/evaluate.py --compare evidence/v0-starter runs/eval-x
python scripts/review_catalog.py          # MCP tools versus the reviewed lock; --write only after a human review
python -m incident_response run --scenario cases/<id>.yaml --run-dir runs/<new> [--mode llm] [--pause-after plan|action]
python -m incident_response resume --run-dir runs/<dir> [--role <role>]
```
