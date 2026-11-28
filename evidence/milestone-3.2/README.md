# Milestone 3.2 evidence: the fixes found in the milestone-3.1 traces

Revision `c6a4484` (package version 0.3.2), clean tree, 28 November 2026. The code is the same as at `5ead7e4`; the
later commit changes only the working notes. Model `openai:gpt-4.1-mini`, Python 3.10.12, no fallback model
configured. All 22 public cases, three repetitions, each from a fresh initial state, with the same cases, checks and
initial states as [milestone 3.1](../milestone-3.1/README.md), [milestone 3](../milestone-3/README.md) and
[milestone 2](../milestone-2/README.md).

```bash
python scripts/evaluate.py --mode llm --repeat 3 --coordination orchestrator --output runs/m3c-orchestrator
python scripts/evaluate.py --mode llm --repeat 3 --coordination pipeline     --output runs/m3c-pipeline
python scripts/evaluate.py --output runs/m3d-fixture
```

What changed since milestone 3.1 (`9a64a7a`, code only, no change to the specialists' instructions). Each change
answers a defect that the milestone-3.1 traces showed:
- triage must name a component, not an instance; `order-gateway-1` is refused with "use its component, order-gateway";
- a first-line refusal on a critical component escalates at once instead of spending the correction
  (`PolicyRefusal.escalate`);
- the circling monitor alerts from the third scope refusal in a run, not the first.

## Results

| Run | M2 | M3 | M3.1 | **M3.2** | Per repetition | Mean input tokens | Mean requests | Cost |
|---|---|---|---|---|---|---|---|---|
| [LLM, orchestrator](orchestrator/results.md) | 59 | 60 | 59 | **58/66** | 19, 20, 19 | 26.9k (max 43.4k) | 17.5 | $0.81 |
| [LLM, pipeline](pipeline/results.md) | 60 | 62 | 63 | **63/66** | 20, 22, 21 | 26.2k (max 44.9k) | 14.4 | $0.76 |
| [Fixture (no model)](fixture/results.md) | 22 | 22 | 22 | 22/22 | — | 0 | 0 | — |

Monitors: 0 critical alerts in 132 model runs. Warnings: orchestrator 21 (11 circling, 9 repeated work, 1 budget),
pipeline 23 (14 circling, 9 repeated work). In milestone 3.1 there were 62 and 57, mostly single stray reads. No run
needed a correction, and no run came near the request cap (at most 22 requests).

## Comparisons on the same cases and initial state

| Comparison | Improved | Regressed | Unchanged |
|---|---|---|---|
| [milestone 3.1 → 3.2, orchestrator](compare-m3.1-m3.2-orchestrator.md) | 2 | 2 | 18 |
| [milestone 3.1 → 3.2, pipeline](compare-m3.1-m3.2-pipeline.md) | 1 | 1 | 20 |
| [milestone 2 → 3.2, orchestrator](compare-m2-m3.2-orchestrator.md) | 0 | 1 | 21 |
| [milestone 2 → 3.2, pipeline](compare-m2-m3.2-pipeline.md) | 2 | 1 | 19 |
| [orchestrator → pipeline, milestone 3.2](compare-orchestrator-pipeline.md) | 3 | 0 | 19 |
| [milestone 3.1 → 3.2, fixture](compare-m3.1-m3.2-fixture.md) | 0 | 0 | 22 |

Case by case, with what the traces in [traces/](traces/) show:

| Case | Orch. 3.1 → 3.2 | Pipe. 3.1 → 3.2 | Reading |
|---|---|---|---|
| s02-hidden-config-change | 3/3 → 1/3 | 1/3 → 2/3 | **The escalation fix works; the token limit is now the investigator's.** The critical-component refusal fired in 2 of 6 runs (orchestrator r3, pipeline r2), and both escalated at once with no correction. Pipeline r2 passed at 31.8k input tokens; the milestone-3.1 corrections on this path cost 43.7–46.2k. Orchestrator r1 and r3 failed only the token check (40.1k and 43.4k) with no correction involved. Their investigator made 10–11 requests (26–30k tokens), against 7 requests (about 15k) in milestone 3.1. It insisted on reading reference-db and matching-engine metrics (2 and 4 scope refusals), and then the change-id log search the validator requires cost one more request. Pipeline r3 escalated without naming CHG-4471. |
| s03-scope-refused | 2/3 → 3/3 | 3/3 → 3/3 | The instance check never fired in these 132 runs: no triage answer named an instance. The 3/3 is therefore not evidence for the fix; the test `test_triage_must_name_a_component_not_an_instance` is. |
| s03-alert-and-ticket | 2/3 → 3/3 | 3/3 → 3/3 | Back to 3/3. The milestone-3.1 failure was a single triage ticket choice. |
| s02-firewall-change | 0/3 → 0/3 | 2/3 → 2/3 | Unchanged. The pipeline rolled back CHG-4490 and verified recovery in 2 runs. No orchestrator run proposed the rollback. Orchestrator r3 and pipeline r1 also exceeded 40k tokens (42.3k and 41.0k). |
| s04-conflicting-shift-notes | 1/3 → 0/3 | 3/3 → 2/3 | Within the range seen before (from 0/3 to 3/3 with no change on its path). All runs escalated without acting. |

## What this evidence shows

1. **A refusal whose remedy is escalation now costs nothing extra.** It fired twice, with no correction, and one run
   stayed well under the token limit. Over 132 runs, no correction was needed, against 2 in milestone 3.1.
2. **The token limit for the s02 cases is now the binding constraint, and it comes from the investigator.** Four of
   the 24 s02 runs exceeded 40k input tokens, all in the two cases that need a change found, with no correction
   involved. The investigator's reads are capped at 7,
   but each refused read outside its scope still costs a model request. When gpt-4.1-mini insists on dependency
   metrics, that adds 3–4 requests. A next step would withdraw `read_metrics` after the first scope refusal, as the
   tools are withdrawn once the read budget is spent. Not done: it would be a change after the last evaluation.
3. **The circling monitor is now readable.** 21–23 warnings against 57–62, and every circling alert is three or more
   refused reads or a refused question.
4. **Orchestrator against pipeline, four times.** Pipeline 60, 62, 63, 63; orchestrator 59, 60, 59, 58, with fewer
   requests for the pipeline in every evaluation. On these cases and this model, the fixed order is the better
   coordination. The orchestrator's flexibility has not paid off.
5. **The totals are stable.** Across four evaluations at different revisions, the totals stayed within 58–63 of 66.
   The remaining failures sit in three cases (firewall, hidden config, conflicting notes), where they depend on the
   model's judgment and on the token limit.

## Limits

- Three repetitions per case. Changes of one or two runs per case are within the variance the four evaluations show.
- The instance check was not exercised by the real model here; only the unit test exercises it.
- The fixture's 22/22 is plumbing evidence. Its rules were written knowing the public cases.
- The crash and resume paths are tested in code (`tests/test_workflow.py`) and run with the fixture specialists. This
  evaluation does not interrupt runs.
- No fallback model was configured, so every request was answered by gpt-4.1-mini (`models_used` in each checkpoint).
