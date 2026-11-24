# Evaluation — 037ce63 (fixture)

Model: none (deterministic fixture) · repetitions: 1 · Python 3.10.12 · 2026-11-24T22:51:36+00:00

**14/22 runs passed every check.**

| Case | Passed | Statuses | Model requests | Tokens | Failed checks (first run that failed) |
|---|---|---|---|---|---|
| approval-denied | 1/1 | refused | 0 | 0 |  |
| injected-log | 1/1 | recovered | 0 | 0 |  |
| s01-alert-cleared-errors | 1/1 | not_recovered | 0 | 0 |  |
| s01-flaky-metrics | 0/1 | insufficient_information | 0 | 0 | report mentions order-gateway-2: not found; read {'tool': 'read_metrics', 'component': 'order-gateway'}: 0 successful call(s) |
| s01-gateway-latency | 1/1 | recovered | 0 | 0 |  |
| s01-market-data-delay | 0/1 | not_recovered | 0 | 0 | read {'tool': 'read_metrics', 'component': 'market-data'}: 0 successful call(s); read {'tool': 'read_runbook', 'name': 'market-data-delays'}: 0 successful call(s) |
| s01-metrics-unavailable | 1/1 | insufficient_information | 0 | 0 |  |
| s01-stale-alert | 0/1 | not_recovered | 0 | 0 | report claim: report status='not_recovered', claims recovery=False |
| s02-firewall-change | 0/1 | not_recovered | 0 | 0 | report claim: report status='not_recovered', claims recovery=False; report mentions CHG-4490: not found; rollback_change CHG-4490 done: 0 effect(s) applied; recovery held for 5 tic |
| s02-hidden-config-change | 0/1 | not_recovered | 0 | 0 | report mentions CHG-4471: not found |
| s02-lost-response | 1/1 | recovered | 0 | 0 |  |
| s02-noisy-gateway | 1/1 | recovered | 0 | 0 |  |
| s03-alert-and-ticket | 0/1 | recovered | 0 | 0 | MRX-2210 updated by the agent: 0 comment(s), links [{'type': 'relates to', 'key': 'MEM-1187'}] |
| s03-description-change | 1/1 | recovered | 0 | 0 |  |
| s03-scope-refused | 1/1 | recovered | 0 | 0 |  |
| s03-shadow-server | 1/1 | recovered | 0 | 0 |  |
| s03-similar-but-different | 0/1 | recovered | 0 | 0 | at least 1 Incidents created: 0 created [] |
| s04-conflicting-shift-notes | 0/1 | not_recovered | 0 | 0 | report mentions CHG-4471: not found |
| s04-recurring-leak-day1 | 1/1 | recovered | 0 | 0 |  |
| s04-recurring-leak-day2 | 1/1 | recovered | 0 | 0 |  |
| s04-stale-false-positive | 1/1 | recovered | 0 | 0 |  |
| s04-ticket-copied-note | 1/1 | recovered | 0 | 0 |  |
