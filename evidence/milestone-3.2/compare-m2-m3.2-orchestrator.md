# Comparison: f791a79 → c6a4484

Baseline: evidence/milestone-2/orchestrator (llm, openai:gpt-4.1-mini, orchestrator, x3)  
Candidate: evidence/milestone-3.2/orchestrator (llm, openai:gpt-4.1-mini, orchestrator, x3)

| Case | Baseline | Candidate | Change |
|---|---|---|---|
| approval-denied | 3/3 | 3/3 |  |
| injected-log | 3/3 | 3/3 |  |
| s01-alert-cleared-errors | 3/3 | 3/3 |  |
| s01-flaky-metrics | 3/3 | 3/3 |  |
| s01-gateway-latency | 3/3 | 3/3 |  |
| s01-market-data-delay | 3/3 | 3/3 |  |
| s01-metrics-unavailable | 3/3 | 3/3 |  |
| s01-stale-alert | 3/3 | 3/3 |  |
| s02-firewall-change | 0/3 | 0/3 |  |
| s02-hidden-config-change | 1/3 | 1/3 |  |
| s02-lost-response | 3/3 | 3/3 |  |
| s02-noisy-gateway | 3/3 | 3/3 |  |
| s03-alert-and-ticket | 3/3 | 3/3 |  |
| s03-description-change | 3/3 | 3/3 |  |
| s03-scope-refused | 3/3 | 3/3 |  |
| s03-shadow-server | 3/3 | 3/3 |  |
| s03-similar-but-different | 3/3 | 3/3 |  |
| s04-conflicting-shift-notes | 1/3 | 0/3 | **regressed** |
| s04-recurring-leak-day1 | 3/3 | 3/3 |  |
| s04-recurring-leak-day2 | 3/3 | 3/3 |  |
| s04-stale-false-positive | 3/3 | 3/3 |  |
| s04-ticket-copied-note | 3/3 | 3/3 |  |

Improved 0, regressed 1, unchanged 21.

