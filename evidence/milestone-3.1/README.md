# Milestone 3.1 evidence: corrections from the earlier finding, and no circling

Revision `f156975` (package version 0.3.1), clean tree, 27 November 2026. Model `openai:gpt-4.1-mini`, Python 3.10.12,
no fallback model configured. All 22 public cases, three repetitions, each from a fresh initial state. The cases,
checks and initial states are the same as in [milestone 3](../milestone-3/README.md) and
[milestone 2](../milestone-2/README.md).

```bash
python scripts/evaluate.py --mode llm --repeat 3 --coordination orchestrator --output runs/m3b-orchestrator
python scripts/evaluate.py --mode llm --repeat 3 --coordination pipeline     --output runs/m3b-pipeline
python scripts/evaluate.py --output runs/m3b-fixture
```

What changed since milestone 3 (`8e83486`, code only, no change to the specialists' instructions). Each change answers
something the milestone-3 traces showed:
- **A correction starts from the earlier finding.** The corrected investigator receives the finding it gave before and
  a digest of the evidence it cited, which it may cite again. It re-reads the component's metrics and then reads only
  what the correction needs, within `CORRECTION_BUDGET = 4` reads. In milestone 3 a correction started from scratch
  and cost about 20k input tokens.
- **The orchestrator cannot go round in circles.** Each specialist gives at most one answer and one follow-up per round
  (`MAX_ANSWERS = 2`). Further questions are refused and logged as `asked_again`. A triage follow-up that names
  another component keeps the established one. In milestone 3, s04-recurring-leak-day2 r2 hit the 40-request cap.
- **A circling monitor.** It counts scope refusals, `asked_again` refusals, and specialists answering more than twice
  per round. In milestone 3, scope refusals raised no alert.

## Results

| Run | Milestone 2 | Milestone 3 | **Milestone 3.1** | Per repetition | Mean input tokens | Mean requests | Cost |
|---|---|---|---|---|---|---|---|
| [LLM, orchestrator](orchestrator/results.md) | 59/66 | 60/66 | **59/66** | 21, 19, 19 | 26.6k (max 49.5k) | 17.4 | $0.80 |
| [LLM, pipeline](pipeline/results.md) | 60/66 | 62/66 | **63/66** | 20, 22, 21 | 25.7k (max 46.2k) | 14.3 | $0.75 |
| [Fixture (no model)](fixture/results.md) | 22/22 | 22/22 | 22/22 | — | 0 | 0 | — |

Monitors: 0 critical alerts in 132 model runs. Warnings: orchestrator 62 (49 circling, 11 repeated work, 2 budget),
pipeline 57 (50 circling, 6 repeated work, 1 budget). Most circling alerts are a single refused read, see below.

No run hit the 40-request cap. The highest was 33 requests (orchestrator s01-metrics-unavailable r1). Milestones 2
and 3 each had one run at the cap.

## Comparisons on the same cases and initial state

| Comparison | Improved | Regressed | Unchanged |
|---|---|---|---|
| [milestone 3 → 3.1, orchestrator](compare-m3-m3.1-orchestrator.md) | 2 | 4 | 16 |
| [milestone 3 → 3.1, pipeline](compare-m3-m3.1-pipeline.md) | 1 | 1 | 20 |
| [milestone 2 → 3.1, orchestrator](compare-m2-m3.1-orchestrator.md) | 1 | 2 | 19 |
| [milestone 2 → 3.1, pipeline](compare-m2-m3.1-pipeline.md) | 2 | 1 | 19 |
| [orchestrator → pipeline, milestone 3.1](compare-orchestrator-pipeline.md) | 4 | 1 | 17 |
| [milestone 3 → 3.1, fixture](compare-m3-m3.1-fixture.md) | 0 | 0 | 22 |

Case by case, with what the traces in [traces/](traces/) show:

| Case | Orch. m3 → 3.1 | Pipe. m3 → 3.1 | Reading |
|---|---|---|---|
| s02-hidden-config-change | 0/3 → 3/3 | 2/3 → 1/3 | **The correction is cheaper, but it was spent on a refusal it cannot fix.** In pipeline r1 and r3 the investigator found the real cause, CHG-4471, and proposed rolling it back. The policy refused, because first-line may not act on reference-db, a critical component, and the refusal itself says to escalate. The refusal was marked correctable, so a correction ran. It escalated, at 46.2k and 43.7k input tokens, against 56.4k and 65.9k for the milestone-3 corrections. The cut is about 15k tokens, but the run is still over the 40k limit. A refusal whose remedy is escalation should not be corrected (fixed after this evaluation, see below). The three orchestrator runs needed no correction (23–25k tokens). |
| s02-firewall-change | 1/3 → 0/3 | 0/3 → 2/3 | Rollback proposed in 3 of 6 runs (milestone 3: 1 of 6). Pipeline r2 and r3 rolled back CHG-4490 and were verified `recovered`. Orchestrator r2 did the same, but used 40,979 input tokens against the 40k limit. The other runs escalated safely. Orchestrator r1 named firewall rule FW-221 but not the change id. Pipeline r1 and orchestrator r3 named CHG-4490 and still proposed nothing. The pipeline's first attempt did not change, so this is model variance, not an improvement. |
| s03-scope-refused | 3/3 → 2/3 | 3/3 → 3/3 | **A defect in our code, found in the trace.** In orchestrator r3, triage named the instance `order-gateway-1` as the component, and no validator rejected it. The investigator's metrics scope became that instance name. Reading `order-gateway-1` failed (unknown component), and every read of `order-gateway` was refused as outside the scope: 20 refusals in a row. The investigator then hit its 12-request cap. The orchestrator asked again until `MAX_ANSWERS` refused, and the run stopped with `insufficient_information` and no action. It was safe, but it is our defect, not model judgment (fixed after this evaluation). |
| s03-alert-and-ticket | 3/3 → 2/3 | 3/3 → 3/3 | In orchestrator r2, triage listed the open Incident MRX-2210 as related instead of as the incident ticket ("no open MRX Incident ticket perfectly matches"). The harness therefore created MRX-2401, and the check allows none. The action and recovery were correct. This is triage's judgment, and the first failure of this case in 18 real runs. |
| s04-conflicting-shift-notes | 3/3 → 1/3 | 3/3 → 3/3 | Back towards milestone 2 (1/3 and 0/3). This supports the milestone-3 reading: the 6/6 there was variance, not an improvement. All runs escalated without acting. |
| s04-recurring-leak-day2 | 2/3 → 3/3 | 3/3 → 3/3 | No circling: at most 16 requests and 24.2k input tokens. In milestone 3, r2 used 40 requests and 67.7k tokens. |

## What this evidence shows

1. **Starting the correction from the earlier finding works, but it uncovered a policy gap.** The corrections cost
   about 15k fewer tokens than in milestone 3. Both, however, followed a refusal that no other proposal could fix: the
   policy itself says a critical component goes to on-call. After this evaluation, such a refusal is no longer
   correctable, so the run escalates at once (see "After this evaluation").
2. **The circling guard holds.** No run reached the request cap, against one per milestone before. `MAX_ANSWERS`
   refused a question twice (orchestrator s01-market-data-delay r3 and s03-scope-refused r3). Both runs still ended in
   a controlled way.
3. **The new monitor is too noisy as written.** One refused read outside the investigator's scope raises a warning,
   and that happens in most runs. Real circling (s03-scope-refused r3: 20 refusals) is lost among them. After this
   evaluation, a scope refusal counts as circling only from the third one in a run.
4. **The traces found a defect the checks would have hidden.** s03-scope-refused r3 failed a recovery check, but the
   cause was a triage answer that our validators let through. The fix is in code, not in the prompt.
5. **Orchestrator against pipeline, third time.** The pipeline again scored higher (63 against 59) and used fewer
   requests (14.3 against 17.4). Over the three milestones the pipeline scored 60, 62 and 63, and the orchestrator 59,
   60 and 59.

## After this evaluation

The following were fixed in code after this evidence was recorded, and are not measured here:
- triage must name a component, not an instance. `order-gateway-1` is refused with "use its component,
  order-gateway";
- a first-line refusal on a critical component is not correctable, so the run escalates at once;
- the circling monitor ignores one or two scope refusals. Recomputed over these same 132 traces, circling alerts
  drop from 49 to 13 (orchestrator) and from 50 to 12 (pipeline), with s03-scope-refused r3 still among them. The
  other monitors are unchanged, still with 0 critical alerts.

## Limits

- Three repetitions per case. Over three milestones the totals moved between 59 and 63 of 66 with no change on the
  failing paths. Changes of one or two runs per case are within this variance.
- The fixture's 22/22 is plumbing evidence. Its rules were written knowing the public cases.
- The crash and resume paths are tested in code (`tests/test_workflow.py`) and run with the fixture specialists. This
  evaluation does not interrupt runs.
- No fallback model was configured, so every request was answered by gpt-4.1-mini (`models_used` in each checkpoint).
