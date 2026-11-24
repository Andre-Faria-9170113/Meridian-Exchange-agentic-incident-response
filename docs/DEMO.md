# Demo and evidence guide

Run commands from the project root after setup. Use a new output directory for each experiment.

## Short demonstration

1. Run `python -m incident_response --scenario cases/s03-alert-and-ticket.yaml --run-dir runs/demo-1`. Show selected source context, the plan, approval, exact action target and fresh metric evidence in `checkpoint.json`. This offline demo tests the plumbing. Repeat with `--mode llm` to demonstrate the actual agents.
2. Run `python -m incident_response --scenario cases/approval-denied.yaml --run-dir runs/refusal-1`. Expected: `refused`, no action effects, exit code 2. Show the denied approval rather than relying on the report text.
3. Run `python -m incident_response --scenario cases/s01-metrics-unavailable.yaml --run-dir runs/missing-1`. Expected: `insufficient_information`, no mitigation. Missing evidence is not recovery.
4. Run `python -m incident_response --scenario cases/s02-lost-response.yaml --run-dir runs/resume-1 --pause-after action`, then `python -m incident_response --run-dir runs/resume-1 --resume`. Show action status reconciliation and exactly one effect.
5. Run `python -m incident_response --scenario cases/s03-alert-and-ticket.yaml --run-dir runs/role-change-1 --pause-after plan`, then `python -m incident_response --run-dir runs/role-change-1 --resume --role settlement-analyst`. Expected: refusal with no action.
6. Explain a memory correction, expiry/isolation checks, and the distinction between a temporary restart mitigation and a fix for the underlying leak.

For the final assessment, add a concrete specialist-failure case, substantive source correlation and the technical-correction behavior required by later sessions. A multi-source input alone does not demonstrate correct correlation.

## Compare versions fairly

Freeze a version with Git, then run `python scripts/evaluate.py --mode llm --repeat 3 --output runs/baseline-v1`. Preserve its code revision and artifacts. Change one harness/policy element, then run the same command with a new output directory such as `runs/candidate-v2`. Hold scenarios, seeds, model, budgets and memory initialization constant.

The bundled evaluator starts every case with a new simulator and memory database. This avoids order-dependent memory contaminating a comparison. For cross-run-memory evaluation, create a separate explicitly ordered day-1/day-2 experiment. Do not call the deterministic fixture's perfect plumbing score an LLM benchmark.

Use the supplied `meridian.evaluate` and `checks/` where useful. `scripts/evaluate.py` currently checks expected final status, the permitted action target and effect count. It is a deliberately modest baseline; add checks for source correlation, specialist failure and final-world conditions as the scope grows. Keep expected outcomes outside model prompts.

## Evidence to preserve

Each run directory holds:

- `scenario.yaml`: exact input copy; checksum recorded in the checkpoint.
- `checkpoint.json`: selected context, plan, original-actor tool journal, action status/approvals/audit, masked trace, code version and mode/model. LLM runs add messages and token/request usage.
- `report.json`: validated final status, actions, evidence and explanation.
- `memory.db` where explicitly selected: persistent local memory; default shared memory is in the parent directory.

Suite output additionally includes `results.json`, with expected and obtained statuses, repetition, model/version, effect count and artifact locations.

Runtime directories are ignored. Before submission, inspect and copy representative sanitized artifacts into a tracked `evidence/` folder. Record the Git revision, environment, model, limits, actual results, comparisons, regressions and interpretation. Version `0.1.0` alone is not enough to identify a modified uncommitted harness; preserve the Git revision too.

## Initial validation scope

The generated baseline has been exercised with the local course environment and no model API calls. Automated checks cover real local MCP, expected effects, approval refusal, evidence failure, resume and memory. A scripted FunctionModel tests the orchestration protocol. These checks do not replace repeated runs against the actual selected LLM or a clean dependency-install test on another platform.
