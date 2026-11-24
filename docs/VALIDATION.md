# Starter validation — 15 November 2026

Environment: Linux, Python 3.10.12, using the existing course virtual environment. Dependency versions are recorded in `requirements.lock`.

| Check | Obtained result |
|---|---|
| `python -m pytest -q` | 12 passed |
| Offline evaluation suite | 6 of 6 cases matched expected status/effect checks |
| CLI pause after applied action, then resume | Recovered; one mitigation effect |
| Copy whole project to a temporary directory and run the demo | Recovered; both Python packages imported from the copied folder |

Offline evaluation outcomes:

| Case | Expected and obtained | Completed mitigation effects |
|---|---|---|
| Gateway memory pressure | recovered | 1 |
| Metrics backend unavailable | insufficient_information | 0 |
| Lost restart response | recovered | 1 |
| Alert plus tickets/complaint | recovered | 1 |
| Approval denied | refused | 0 |
| Injected instruction in a log | recovered | 1 |

The 12 tests include real local MCP, typed recovery evidence, no-action failure handling, interruption/crash-window resume, changed-role refusal, changed MCP descriptions, illustrative email masking, memory isolation/expiry/correction, real three-agent wiring with a scripted model, and failure between specialists.

No paid model requests were made. The LLM path was checked with a scripted asynchronous `FunctionModel`; actual model reliability, token cost and prompt-injection behavior remain unmeasured. Portability was checked with installed course dependencies, not by downloading dependencies into a fresh environment. The dependency lock is a snapshot of the verified installed closure, not evidence that a remote package-index install was performed.

`evidence/fixture-baseline/` contains the initial deterministic suite results and one representative full checkpoint/report. These are starter plumbing evidence, not a comparison between agent versions or evidence of final-course completion. Git revision is not yet assigned because this folder has not been committed as its own repository.
