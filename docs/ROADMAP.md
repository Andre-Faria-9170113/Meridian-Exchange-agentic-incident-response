# Implementation roadmap

The starter implements one runnable vertical slice. Use this checklist to turn it into your own final project, preserving a working version at each milestone.

## Milestone 1 — first-line incident agent

- [ ] Run the offline demo and read its checkpoint from input through recovery.
- [ ] Configure the real model, run the same incident and inspect all three agents' messages.
- [ ] Explain every exposed tool and each output contract; tighten remaining MCP output schemas.
- [ ] Add incident routing and follow-up evidence gathering rather than assuming every incident is gateway memory pressure.
- [ ] Correlate alerts, operations tickets and member complaints by observed time/component/link evidence. Add a similar-looking unrelated ticket to prove you do not overmerge.
- [ ] Add a second incident family, such as a dependency change requiring rollback, with its own runbook/evidence guard and authorized action.
- [ ] Cover invalid outputs, missing evidence and temporary/permanent service failure with controlled statuses.
- [ ] Save baseline cases/results/traces and a Git version, for example `milestone-1`.

## Milestone 2 — production on-call agent

- [ ] Run two incidents in successive simulated shifts sharing memory; show how relevant history helps without becoming unquestioned authority.
- [ ] Demonstrate stale, conflicting and corrected memory. Add an authorized deletion and handover entry point if useful for your flow.
- [ ] Add adversarial source text and sensitive-data examples; test the real LLM as well as deterministic controls.
- [ ] Add mismatched approval, denied approval, role confusion and cross-team cases.
- [ ] Decide approval validity/expiry and who may approve each enabled critical action.
- [ ] Reuse public check patterns or extend `scripts/evaluate.py`; compare a frozen baseline and revised version repeatedly under identical seeds, model and budgets.
- [ ] State regressions and limits, then preserve `milestone-2`.

## Milestone 3 — incident response center

- [ ] Review session 8's security material when its missing slides become available.
- [ ] Incorporate session 9 after it is taught and confirm the scope of technical corrections with the trainer.
- [ ] Exercise specialist failure/disagreement/invalid output, and make sure the orchestrator detects and handles it.
- [ ] Demonstrate constraints survive delegation and are enforced by the mutation path.
- [ ] Interrupt before action, after applied action/before response, and before final verification. Resume without duplicate effects.
- [ ] Resume with changed permissions/approval and prove authority is checked again.
- [ ] Expand recoverable state for any new workflow stages or tools; keep external writes outside simulator replay.
- [ ] Repeat the accumulated cases and reserved cases; document remaining failure modes.
- [ ] Preserve `milestone-3` and rehearse the final demo from a clean clone.

## Submission

- [ ] Prepare the verbal Meridian introduction: name the lecture features being emphasized and the demonstrations planned. See [FOCUS_TOPICS.md](FOCUS_TOPICS.md); the proposal diagram is optional under the trainer clarification.
- [ ] Keep dependencies/lock and `.env.example` current; inspect Git staging for secrets/runtime files.
- [ ] Include representative sanitized input/expected/obtained results, traces and comparisons in a tracked evidence folder.
- [ ] Record code version, model, repeated-run count, limits, decisions and known regressions.
- [ ] Update README commands, limitations and AI-assistance disclosure.
- [ ] Publish the project in a public GitHub repository, retain course-material attribution and verify evaluator access while signed out.
- [ ] Deliver by the PDF's deadline: 30 November, 23:59.
