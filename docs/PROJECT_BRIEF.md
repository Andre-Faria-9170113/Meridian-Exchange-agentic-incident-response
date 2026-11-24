# What the final project expects

Source: **Projeto Agentic AI.pdf**, 10 pages, supplied at the course workspace root. This document paraphrases the Meridian option; the PDF remains authoritative.

## The product

Build an **incident-response agent system for a fictional stock exchange**. Its user is an operations/on-call engineer. Given an alert, ticket or complaint, the system investigates the simulated exchange, proposes a justified mitigation, executes it within code-enforced permissions, and checks whether the exchange recovered.

For example: an alert says order acknowledgements are slow. Monitoring shows one gateway instance has high memory; links and the database are healthy. The system consults the applicable runbook, obtains any required approval, restarts that instance, and reads fresh metrics. It may report recovery only once the recovery condition holds. If a response is lost, it checks action status before retrying. If evidence is missing or permission is refused, it stops or escalates with an honest explanation.

The five simulated components are order gateway, matching engine, market data, settlement and reference database. The matching engine and reference database are critical. Several sources can refer to one incident, so collecting multiple texts is not enough: your finished system should correlate them using evidence and avoid treating every source as a separate incident.

You are building the **agent layer around the supplied simulator**. You do not need to build a real exchange, implement trading infrastructure, connect to real Jira, or design a polished website. The brief says a simple interface is sufficient. A CLI can satisfy this.

## Minimum capabilities translated into implementation

| PDF requirement | What you must show | This starter |
|---|---|---|
| End-to-end flow and selected context | Input -> investigation -> decision -> action -> verified result; controlled missing/invalid data and service failures | Working bounded gateway flow; one unavailable-metrics case |
| Tools and MCP | Clear contracts; a working MCP connection; controlled exposed capabilities; outputs validated before downstream use | Real in-process FastMCP reads, allowlist/hash checks, Pydantic boundaries; broaden result schemas as tools grow |
| Memory | Cross-run state with origin, validity, correction and isolation policies | SQLite summaries, confidence, expiry, team isolation and correction function |
| Coordination | An orchestrator plus **at least two distinct specialists**, with integrated results | LLM orchestrator, gateway investigator, dependency/safety reviewer; strict result integration |
| Verifiable effects | An action and independent evidence of its consequence before concluding or repeating | One instance restart, status reconciliation, three healthy post-action readings |
| Permissions/data/approval | Limits enforced by code; protected data; approval when required | Role checks, all-action simulated approval, fresh evidence guard, illustrative email masking |
| Resume | Persist work, interrupt it, resume and recheck permissions and previous effects | Atomic checkpoint and local simulator replay; pause/resume commands and crash-window test |
| Local failure data | Synthetic data is acceptable; service failures testable locally; secrets stay out of Git | Copied synthetic simulator/cases, extra refusal/injection cases, `.env.example`, ignored `.env` |
| Evaluation and engineering evidence | Repeated cases, comparisons, regressions, traces, clear clean-clone setup | Fixture evaluator and tests; actual LLM measurements and version comparisons remain yours |

An LLM saying “approved,” “I restarted it,” or “recovered” is not proof. Approval records, executor effects and fresh observations must support those claims.

## The three milestones evolve one system

1. **First-Line Incident Agent — sessions 1–3.** A working harness, selected context, useful tools/MCP, limited actions, and evidence showing what was read, decided and verified.
2. **Production On-Call Agent — sessions 4–6.** Cross-run memory with corrections, security/approval policies and repeated evaluations showing regressions and improvement.
3. **24/7 Incident Response Center — sessions 7–9.** Integrated specialist work, technical corrections, orchestration and safe resume without repeating effects.

The supplied slide decks cover Course 2 sessions **1–7**. As clarified by the student on 19 November 2026, **session 8 focused on security, but its slides are missing**, while **session 9 has not yet been taught**. Review session 8's security material when supplied and incorporate session 9 after it is taught; confirm the trainer's intended scope of “technical corrections” rather than inferring it from the session-7 lab. The “24/7” milestone name does not itself require production hosting or a real continuous on-call service.

## How the demonstration is assessed

- **Task completion:** a multi-source incident with a verified outcome, plus controlled behavior when information or a service is missing.
- **Control and security:** an authorized action with confirmed effect, an inappropriate action refused, and respected approvals/data policies.
- **Coordination and resume:** integrated specialist results, a detected failure between specialists, and interrupted work resumed without unintended repeated effects.
- **Evidence-based evolution:** compare a baseline and later versions on the **same cases and initial state**; add cases, measure regressions and state limitations.
- **Engineering clarity:** a clean clone runs from the README; traces and results justify architectural choices.

The offline fixture is a useful engineering baseline. It does not establish LLM task reliability, prompt-injection robustness, or improvement over earlier agent versions. Demonstrate those with the real agents and recorded model/version/budget information.

## What to hand in

1. **Project introduction:** the PDF originally asks for a proposal with problem, user, main flow and diagram. Per the later trainer clarification reported by the student, Meridian students may omit the proposal diagram and verbally explain the lecture features they will emphasize. See [FOCUS_TOPICS.md](FOCUS_TOPICS.md). [PROPOSAL.md](PROPOSAL.md) remains optional planning material.
2. **Repository:** code, declared dependencies and a lock, a secret-free `.env.example`, and versions of the milestones. Git tags/releases are a reasonable way to preserve them; agree naming with your trainer.
3. **README:** setup and execution, architecture, policies, decisions, limitations and a demo. AI assistance is allowed **with disclosure**.
4. **Cases and results:** input, expected and obtained results, comparisons and traces, recording version, model and limits.

The PDF gives the final deadline as **30 November at 23:59**. It explicitly says unit tests and metrics built from scratch are **not required**. Reusing the course simulator, evaluation patterns and code is expected; distinguish reused infrastructure from your own agent design and improvements.

## What to build next

Keep the gateway case as the first vertical slice. Run the live agents, inspect their traces and explain each component. Then add correlation, a second mitigation family such as approved rollback, specialist failure cases, stronger memory/security scenarios, and measured version comparisons. [ROADMAP.md](ROADMAP.md) gives a concrete sequence. Use the final brief and later course material to determine when the project is complete.
