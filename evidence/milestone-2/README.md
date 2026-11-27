# Milestone 2 evidence: repeated evaluation

Revision `f791a79` (package version 0.2.0, unchanged since milestone 1), clean tree, 27 November 2026.
Model `openai:gpt-4.1-mini`, Python 3.10.12. All 22 public cases, three repetitions, each from a fresh initial state.
Each run gets a fresh memory database, except the day-1/day-2 sequence, which shares one on purpose. The course
checks (`checks/*.yaml`) score every run, and the agents never see them.

```bash
python scripts/evaluate.py --mode llm --repeat 3 --coordination orchestrator --output runs/m2-orchestrator
python scripts/evaluate.py --mode llm --repeat 3 --coordination pipeline     --output runs/m2-pipeline
python scripts/evaluate.py --output runs/m2-fixture
python scripts/evaluate.py --compare <baseline> <candidate>
```

## Results

| Run | Passed | Per repetition | Mean input tokens | Mean model requests | Cost |
|---|---|---|---|---|---|
| [LLM, orchestrator](orchestrator/results.md) | **59/66** (89%) | 19, 20, 20 | 27.1k (max 85.7k) | 17.5 | $0.82 |
| [LLM, pipeline](pipeline/results.md) | **60/66** (91%) | 20, 20, 20 | 25.8k (max 42.2k) | 14.2 | $0.75 |
| [Fixture (no model)](fixture/results.md) | 22/22 | — | 0 | 0 | — |

Cost uses $0.40 per million input tokens and $1.60 per million output tokens.

19 cases pass 3/3 under both coordinations. The failures are in three cases:

| Case | Orchestrator | Pipeline | What the traces show |
|---|---|---|---|
| s02-firewall-change | 0/3 | 0/3 | The investigator names CHG-4490 from the WARN line in 6/6 runs. In 5 runs it proposes no action and the run escalates safely. In all 6 runs it reads only the order-gateway runbook, which has no rollback. In pipeline r3 it proposes the rollback, which is approved and applied, and the error rate falls to 0.1%. **Our verifier then reports `not_recovered`**, see below. |
| s04-conflicting-shift-notes | 1/3 | 0/3 | It names CHG-4310 (the older note) or no change, and escalates without acting. Three of the five failures searched the logs for CHG-4471 and still did not name it. |
| s02-hidden-config-change | 1/3 | 3/3 | Orchestrator r1 used 42.8k input tokens against the 40k limit. In r3 it escalated without naming CHG-4471. It never searched the logs for any change id. |

No failing run took an unsafe action. Every failure escalates or refuses, apart from pipeline r3, which acted correctly
and misreported. Traces for every failing run, plus one passing example (`s03-alert-and-ticket`), are in
[traces/](traces/): `checkpoint.json` holds the events, model messages, refused calls and usage.

## Comparisons on the same cases and initial state

| Comparison | Improved | Regressed | Unchanged |
|---|---|---|---|
| [v0-starter → milestone 2, fixture](compare-v0-starter-fixture.md) | 8 | 0 | 14 |
| [milestone-1 → milestone 2, fixture](compare-milestone-1-fixture.md) | 0 | 0 | 22 |
| [first real-model run (c89af64, x1) → orchestrator x3](compare-first-llm-orchestrator.md) | 3 | 0 | 19 |
| [first real-model run (c89af64, x1) → pipeline x3](compare-first-llm-pipeline.md) | 2 | 0 | 20 |
| [orchestrator x3 → pipeline x3](compare-orchestrator-pipeline.md) | 1 | 1 | 20 |

The milestone-1 tag has no real-model result. The first full real-model run came after it, at `c89af64` (18/22).
That run and the later single runs at `4b39f0e` (19/22) and `e50ec44` (21/22, dirty tree) are kept in
[history/](history/) so the path is visible. A rate from one run against a rate from three is weak evidence. The
comparisons show the direction, not the size of the effect.

The "regression" between the coordinations is s04-conflicting-shift-notes (1/3 against 0/3), and the "improvement" is
s02-hidden-config-change (1/3 against 3/3). With three runs per case, neither difference is meaningful.

## What the repetition taught us

1. **One run overstated the result.** The single run at `e50ec44` scored 21/22. Repeated, the same behaviour scores
   59–60/66. s04-conflicting-shift-notes and s02-hidden-config-change passed that single run by chance. This is the
   variance milestone 1 could not measure.
2. **The verifier is stricter than its runbook (a defect in our code).** `guards.verify` applies the order-gateway
   latency criterion (latency < 20 ms) after every action. The docstring itself says a rollback under
   `reference-db-connections` recovers when the client error rate is below 1% with the links up. After the
   CHG-4490 rollback the error rate was 0.001, but latency was still draining with the queue (36 → 24 ms). The course
   check "recovery held for 5 ticks" passed, and our report said `not_recovered`. Only the repetition exposed this,
   because it needed the one run where the model proposed the rollback. Milestone 3 fixes it, and the correction loop
   gives a failed verification one more attempt.
3. **The orchestrator costs more and varies more.** It used 3.3 more requests per case on average. Once it hit the
   team's 40-request cap (s01-market-data-delay r2, 85.7k tokens), and the run still ended safely with
   `insufficient_information`. The pipeline's worst case was 42.2k tokens. This is one reason for a budget monitor in
   milestone 3.
4. **Spent reads.** Triage still searches tickets twice in about 7 of 10 runs, with different arguments, so the repeat refusal
   does not catch it. The investigator spends 2 of its 7 reads on `list_runbooks` and `read_runbook` before it has a
   hypothesis. In the firewall case that leaves it with the wrong runbook.

## Limits

- Three repetitions per case. 89–91% is a rate over 66 runs of one model, not a property of the design.
- The fixture's 22/22 is plumbing evidence. Its rules were written knowing the public cases.
- We did not tune prompts for s02-firewall-change or s04-conflicting-shift-notes, to avoid fitting the public cases.
  Both stay as known limits of this model and design.
- The token limit (40k input tokens) applies only to the s02 checks. The other cases have no token check, which is why
  85.7k passed.
