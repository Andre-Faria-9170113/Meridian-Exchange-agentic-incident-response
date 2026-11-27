# Milestone 3 evidence: repeated evaluation after the corrections, resume and monitors

Revision `56b053b` (package version 0.3.0), clean tree, 27 November 2026. Model `openai:gpt-4.1-mini`, Python
3.10.12, no fallback model configured. All 22 public cases, three repetitions, each from a fresh initial state. The
cases, checks and initial states are the same as in [milestone 2](../milestone-2/README.md), which ran the same
commands at `f791a79`.

```bash
python scripts/evaluate.py --mode llm --repeat 3 --coordination orchestrator --output runs/m3-orchestrator
python scripts/evaluate.py --mode llm --repeat 3 --coordination pipeline     --output runs/m3-pipeline
python scripts/evaluate.py --output runs/m3-fixture
```

What changed since milestone 2 (all in code, no prompt changes):
- `cb89788`: the recovery criterion follows the action's runbook;
- `8cb7d6e`: one correction after a policy refusal or unverified recovery;
- `1b457c5`: crash points, downtime, approval validity on resume;
- `c6e21e5`: monitors over the journal;
- `9d624a6`: fallback model routing and usage per agent.

## Results

| Run | Milestone 2 | **Milestone 3** | Per repetition | Mean input tokens | Mean requests | Cost |
|---|---|---|---|---|---|---|
| [LLM, orchestrator](orchestrator/results.md) | 59/66 | **60/66** | 20, 19, 21 | 27.9k (max 67.7k) | 18.0 | $0.84 |
| [LLM, pipeline](pipeline/results.md) | 60/66 | **62/66** | 20, 21, 21 | 25.7k (max 56.4k) | 14.3 | $0.75 |
| [Fixture (no model)](fixture/results.md) | 22/22 | 22/22 | — | 0 | 0 | — |

Monitors: 0 critical alerts in 132 model runs. No action ran without a valid matching approval, nothing was
applied twice, and no recovery claim lacked a metrics read after the action. There were 29 warnings: 26 for
repeated work and 3 for budget.

## Comparisons on the same cases and initial state

| Comparison | Improved | Regressed | Unchanged |
|---|---|---|---|
| [milestone 2 → 3, orchestrator](compare-m2-m3-orchestrator.md) | 2 | 2 | 18 |
| [milestone 2 → 3, pipeline](compare-m2-m3-pipeline.md) | 1 | 1 | 20 |
| [orchestrator → pipeline, milestone 3](compare-orchestrator-pipeline.md) | 2 | 1 | 19 |
| [milestone 2 → 3, fixture](compare-m2-m3-fixture.md) | 0 | 0 | 22 |
| [v0-starter → milestone 3, fixture](compare-v0-starter-fixture.md) | 8 | 0 | 14 |

Case by case, with what the traces in [traces/](traces/) show:

| Case | Orch. m2 → m3 | Pipe. m2 → m3 | Reading |
|---|---|---|---|
| s02-firewall-change | 0/3 → **1/3** | 0/3 → 0/3 | **The recovery-criterion fix, confirmed on a real run.** In orchestrator r3 the model proposed the CHG-4490 rollback. Afterwards the error rate was 0.1% while latency was still 32–34 ms. The run was verified `recovered` in 3 readings, and the course check "recovery held for 5 ticks" passed. The milestone-2 criterion would have reported `not_recovered`, as it did for pipeline r3 then. In the other 5 runs the model again proposed no action and escalated safely. |
| s02-hidden-config-change | 1/3 → 0/3 | 3/3 → 2/3 | **The correction loop works, but costs too many tokens.** It triggered twice, both times here, after the model proposed rolling back the wrong change (CHG-4310). Code refused it because no log line names it. In orchestrator r2 the correction found the real cause, CHG-4471, and escalated correctly, but with 65.9k input tokens against the 40k limit. In pipeline r1 it escalated at 56.4k without naming CHG-4471. Without a correction: orchestrator r1 used 43.9k, and r3 did not name the change. |
| s04-conflicting-shift-notes | 1/3 → **3/3** | 0/3 → **3/3** | **Not claimed as an improvement.** No code on this path changed, and the prompts are the same. All 6 runs escalated without acting, as before. 5 of 6 searched the logs for CHG-4471 (3 of 5 failing runs did in milestone 2). Only 2 of 6 name it as the cause; the others mention it elsewhere in the report, which is what the check requires. We read this as model variance, which three repetitions cannot rule out, and a lenient check. |
| s04-recurring-leak-day2 | 3/3 → 2/3 | 3/3 → 3/3 | **Going round in circles at the orchestrator level.** In r2 the orchestrator asked the investigator 4 times and triage 3 times. The investigator tried 7 times to read metrics outside its component (reference-db, matching-engine), and each was refused. The team hit its 40-request limit and stopped in a controlled way, without acting. No correction was involved. |

## What this evidence shows

1. **The defect found in milestone 2 is fixed, and a real run shows it.** The fix came from the repetition: the
   failing case was found in milestone 2, a unit test pins the criterion, and here a real run passes because of it.
2. **The correction loop is correct but expensive.** In both corrections the refusal was right, no effect followed,
   and the second proposal was reviewed and escalated. A correction starts the investigator from scratch, so it
   re-reads what it had already read, which adds about 20k input tokens. That breaks the s02 token budget. The next
   step would be to give the corrected investigator the evidence it already cited instead of a fresh start. Not done
   in this milestone.
3. **The monitors show what the checks miss.** They found no rule broken in 132 runs. Scope refusals (s04 day2 r2)
   are not yet a monitor: they appear in `limited_calls` but raise no alert. That gap is noted for the docs.
4. **Orchestrator against pipeline.** The pipeline is cheaper (14.3 against 18.0 requests per case) and scored
   slightly higher in both milestones (60 against 59, then 62 against 60). Its fixed order cannot go round in
   circles at the coordination level, and the orchestrator did that once in each milestone. The orchestrator can
   ask follow-ups and decide on corrections itself, but with this model that flexibility has not yet paid off.

## Limits

- Three repetitions per case. Changes of one or two runs per case, in either direction, are within the variance this
  shows. s04-conflicting-shift-notes moved from 1/6 to 6/6 with no relevant code change.
- The crash and resume paths are tested in code (`tests/test_workflow.py`) and run with the fixture specialists. This
  evaluation does not interrupt runs.
- The fallback model was not configured, so every request was answered by gpt-4.1-mini (`models_used` in each
  checkpoint).
- The fixture's 22/22 is plumbing evidence. Its rules were written knowing the public cases.
