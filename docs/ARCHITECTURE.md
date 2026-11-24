# Architecture and policies

## Ownership and data flow

`meridian/` is copied course infrastructure. Student code belongs in `incident_response/`. The simulator owns state, synthetic signals, actions, approvals and idempotency. The harness owns selected context, validated contracts, permissions, memory policy, coordination and recovery decisions.

The harness calls native tools for metrics, logs, links, changes and runbooks. Every call moves simulated time and is traced. Ticket search and monitoring alerts go through a real FastMCP client/server connection in the same process. All servers share one simulator. No HTTP server or external service is needed.

Context is deliberately bounded: five metric readings, two links, ten ERROR log entries, five ticket summaries, five changes, one current runbook and ten qualified memory candidates. It is a starting selection policy, not an autonomous investigation strategy.

## Contracts and agent responsibilities

- `Finding`: cause, source references and an exact action proposal.
- `Review`: dependency/safety judgment, constraints and source references.
- `Plan`: both results, preserved without orchestration edits.
- `Metrics`: typed observation fields used by code for evidence and recovery.
- `Report`: constrained status, observed actions, evidence and summary.

The gateway investigator diagnoses the gateway. The dependency/safety specialist reviews the proposal against independent link and database readings. The orchestrator decides delegation within this narrow workflow and integrates them. Both specialists must actually run; a plausible fabricated final plan is rejected. Shared request/token limits bound the planning call. Specialist exceptions or invalid outputs are handled as inconclusive runs before mutation.

MCP responses must be objects; ticket-summary keys and collection shape are checked. Extend typed schemas for additional MCP data before using those data in consequential decisions. Native metrics and every specialist output are already validated with Pydantic.

## Mutation authority

No specialist or orchestrator gets a raw restart tool. After planning, code checks the caller's current role, safety review, fresh instance pressure, live links and database metrics. Only a single gateway-instance restart is enabled by the evidence guard in this baseline. The proposal schema reserves rollback as an extension, but the current guard refuses it.

Whole-service restart is never exposed. First-line may restart only noncritical instances; settlement analysts cannot remediate. On-call and incident-manager roles have broader role permission, but still need implemented evidence guards and matching approval. Every mutation in this starter needs approval, a stricter policy than the simulator's minimum. The policy also requires incident-manager approval for critical trading-session actions if those actions are enabled later.

Approval is simulated by the scenario, not by an actual human UI. `approve_all` accepts scoped requests, `deny_all` refuses them. An approval never grants a role extra authority. Resume rechecks authority for further work.

## MCP governance and data handling

Only tickets/monitoring servers and explicitly allowlisted read tools are reachable through the gateway. The committed description hashes originate in the supplied session-3 reviewed catalog. New or changed descriptions are refused; do not regenerate approval locks automatically at startup. Review publisher, version, schemas and descriptions before accepting a change. Current enforcement pins descriptions, not the full server identity/schema.

An insufficient-scope response blocks that tool for the remaining run. No alternative write tool is exposed. No messaging/email actions are implemented.

Email-shaped strings in tool results are masked before model context and checkpoint tool-result storage. This is an illustrative pattern, not a comprehensive privacy filter. Synthetic input scenarios are copied to the run directory as original inputs; they may still contain synthetic identifiers. Inputs, local checkpoints, model output and memory remain trusted-local artifacts and need appropriate handling if you introduce real data.

Retrieved text is untrusted evidence. Prompts state this, while scoped mutation tools and evidence checks enforce the useful boundary. The injected-log fixture tests that boundary; it does not prove a real model resists every prompt injection.

## Memory

The supplied SQLite store persists separately from checkpoints. By default runs with the same parent directory share `memory.db`. The evaluator overrides this with a fresh database per case.

Write only summaries of verified recoveries, citing the run ID and observed evidence; confidence is 0.8 and validity is seven simulated days. Incident summaries describe mitigations, not approved reusable procedures. Recall requires same team, active status, confidence >=0.7, a nonfuture creation time and a future expiry. Seeded memories without explicit validity are deliberately excluded. Current evidence has priority over recalled hints.

`correct()` checks team ownership, writes a sourced replacement and supersedes the old record. The underlying store also supports deletion with an audit tombstone, but a protected deletion command/handover workflow remains an extension. Do not expose raw store methods directly to agents.

## Checkpoint and resume semantics

Before each tool call, atomically save its intent. Save its result after execution. On resume, load the pinned scenario, verify its checksum, reconstruct the deterministic simulator, and replay recorded tool intents in order using their original actors. Completed observations must match their recorded outputs; otherwise resume fails closed. A pending intent is completed during reconstruction.

This reconstruction runs actions against a fresh in-memory simulation. It represents one logical history, not a second action against a live external system. The same durable run/action/target key identifies the mitigation. Query action status before any new attempt; a completed action skips fresh execution and proceeds to verification after revalidating permissions/approval. Post-action readings must include three consecutive healthy ticks later than the action tick.

Atomic file replacement protects against partial checkpoint content. It does not implement multiple concurrent writers, a distributed lease, remote transactions, or production crash consistency. Keep code/catalog versions stable between interruption and resume. Never substitute a real restart API into this replay adapter: a real integration must restore task state without replaying external side effects, and reconcile with durable server-side status/idempotency.

## Remaining engineering decisions

Record decisions as the project grows: when one incident is the same as another, when to request more evidence, which role can approve each action, how approval expires, how specialist disagreements resolve, how confidence/validity change after correction, and how live failures affect resume. Support each with a case and trace.
