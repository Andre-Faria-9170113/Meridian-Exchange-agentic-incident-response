# Lecture topics and a verbal project focus

Reviewed on 19 November 2026 against the seven PDFs supplied in the workspace's `slides/` folder and `Projeto Agentic AI.pdf`.

**Submission clarification supplied by the student:** for the Meridian proposal, the proposal diagram can be omitted and the intended lecture-feature focus can be presented verbally. The written proposal and diagrams already in this starter are optional planning aids. This clarification is separate from the PDF's original delivery instructions; it does not establish an exemption from the final system's minimum capabilities.

## Topics actually covered in the supplied slides

| Session and topic | Features you could emphasize in Meridian | Demonstration or comparison |
|---|---|---|
| **1 — Agent harnesses and PydanticAI** | Separate model decisions, harness responsibilities and runtime restrictions; typed tool/report contracts; output validators; bounded retries and evidence-based acceptance. | A structurally valid report claims recovery, but code rejects it because metrics do not support it. Compare the harness before and after that check. |
| **2 — Context engineering, tools and skills** | Always/on-demand/excluded context; log search and grouping; source-preserving summaries; task-specific tool selection; loading the applicable runbook by version; fresh action preconditions, dry-runs and idempotency. | Noisy logs conceal a rare configuration event; the revised context/tool interface exposes it. Separately, an executor response is lost and the same mitigation is not repeated. |
| **3 — MCP integration, correlation and governance** | A real MCP client/server integration; correlating events using time, symptoms and component/dependency evidence; approved tool catalogs; changed-description detection; least privilege; handling scope refusals. | Group an alert, ticket and complaint into one incident while keeping a similar-looking unrelated event separate. Reject an unreviewed/changed tool and respect a scope refusal. |
| **4 — Memory as a data system** | Write/recall policies; provenance, confidence, validity and team boundaries; duplicate handling, updates and replacement; current-state verification; memory poisoning defenses; shift handover and deletion; human review before promoting a lesson into a procedure. | Compare a second shift with and without memory. Show a stale or corrected note, cross-team exclusion, and a newly affected instance rather than repeating yesterday's restart target. |
| **5 — Security, authorization and personal data** | Hooks versus content guardrails; acting on behalf of the requesting user; role and target permissions; scoped approval; current evidence; prompt injection in logs; privacy checks at input, outbound messages and final output. | Refuse an unrelated critical restart suggested by a log while still permitting the useful gateway mitigation. Show that approval does not override the user's role and that technical evidence survives data masking. |
| **6 — Evaluation, reliability and improvement** | Repeated comparisons on identical initial states; outcome, trajectory and report checks; per-case regressions; model/token/time budgets; code, model and human evaluators; reserved cases. An additional topic is a critic/proposer improvement loop with acceptance rules and memory of rejected changes. | A candidate appears better after one run but regresses on an approval or rollback case after repeated runs. An optional improvement loop must retain gains on reserved cases, not just obtain a high critic score. |
| **7 — Multi-agent orchestration** | Fixed pipeline versus agent-chosen delegation; agents as tools versus handoffs; specialist-specific context and tools; parallelism only for independent tasks; transmitting constraints; shared task/evidence state; human approval and post-action review. | A network diagnosis alone suggests an unsuitable mitigation; a database specialist supplies the missing constraint. Compare pipeline/orchestrator calls, tokens and time, and refuse to finish when recovery review fails. |

The examples are possible project demonstrations, not claims that the starter already implements every feature listed.

## Slide references

Page numbers count from the PDF's first page. Filenames identify the supplied sources without requiring this portable project to depend on the parent course folder.

- `Sessão 1 - Agent Harness e Frameworks de Agentes.pdf`: pp. 3–7 (responsibilities), 15–19 (tools, validation, effects and comparison).
- `Sessão 2 - Context Engineering & Tools.pdf`: pp. 7–12 (context/tools/skills), 15–18 (effects, preconditions, dry-run and safe repetition).
- `Sessão 3 - MCP.pdf`: pp. 3–8 (integration), 9–12 (correlation and grouping checks), 13–18 (governance/scopes).
- `Sessão 4 - Memória como sistema.pdf`: pp. 7–10 (writing and corrections), 13–18 (recall and poisoning), 19–22 (handover, procedures, deletion and comparison).
- `Sessão 5 - Segurança, autorização e dados pessoais.pdf`: pp. 6–10 (controls/identity), 18–23 (role confusion, evidence, privacy and audit).
- `Sessão 6 - Avaliação e melhoria.pdf`: pp. 5–17 (reliability and evaluation), 18–21 (improvement loop, reserved cases and regressions).
- `Sessão 7 - Orquestração de agentes.pdf`: pp. 2–8 (coordination patterns), 12–17 (state, specialists and comparison), 18–21 (approval and recovery review).

## Cross-session topic: durable execution and resume

The project brief explicitly requires work to survive interruption, with permissions and prior effects revalidated. Session 2 supplies action-status/precondition/idempotency concepts; session 4 covers continuity and handover; session 7 covers shared tasks, plans, approvals and evidence. Together these support a focus on recoverable execution.

Persistent memory and a resumable workflow are different: remembering a previous incident does not establish whether an action in an interrupted current incident already happened. Evaluate both if you emphasize continuity.

The supplied slides cover sessions 1–7. Per the student's clarification on 19 November 2026, **session 8 focused on security, but its slides are currently missing**, and **session 9 has not yet been taught**. Session 8's detailed security topics cannot be mapped until its material is available; session 9's content is not yet known. Revisit the emphasis when those materials become available. The briefing's precise meaning of **technical corrections** remains unconfirmed; do not infer it from session 8's security focus or treat session 6's improvement loop/session 7's corrective mitigation attempt as confirmed substitutes.

## Suggested emphasis for the existing starter

**Safe multi-agent incident response, supported by repeated evaluation.**

This combines session 7's coordination, session 5's authorization/evidence controls, and session 6's evaluation. Context, MCP, memory and resume remain supporting capabilities. This is a suggested focus, not a selection made on the student's behalf.

The starter already has an orchestrator and two specialists, typed result integration, code-enforced action checks, simulated approval and recovery verification. Useful project contributions would be more selective investigation, a dependency-constrained mitigation case, specialist failure/disagreement handling, and repeated real-model comparisons with a frozen baseline.

Do not claim that the current implementation has independent parallel investigators, a separate post-action LLM reviewer, human approval UI, substantive event correlation or a critic/proposer improvement loop. Its current specialists are a gateway investigator and a sequential dependency/safety reviewer; the harness performs verification after acting. Those other lecture features are choices to implement if they serve the selected focus.

### Example verbal introduction

> I'll use the Meridian Exchange simulator to focus on multi-agent coordination and safe mitigation. The orchestrator will combine specialist evidence and operational constraints, while code checks permissions and approvals before an action. I'll verify recovery using fresh metrics and compare versions on repeated cases, including missing evidence, refused approval, specialist failure and interrupted execution.

### A bounded set of demonstrations

1. **Useful mitigation:** identify one unhealthy instance, act on the correct target with approval, and show fresh recovery evidence.
2. **Missing constraint:** show why specialist integration changes a decision when a dependency or destination is unavailable.
3. **Unsafe request:** show an unauthorized or injected action blocked while the legitimate mitigation can still proceed.
4. **Continuity:** interrupt after an applied action/unknown response, then resume without a second effect.
5. **Measured improvement:** compare a frozen baseline and revised harness on identical seeded cases, repeated with the actual selected model. Report per-case regressions and resources, including failures.

This emphasis does not require implementing every optional technique in the slides. In particular, a self-improvement loop, remote MCP hosting, cloud storage, handoffs and a polished UI are not separately stated minimum requirements in the project PDF.
