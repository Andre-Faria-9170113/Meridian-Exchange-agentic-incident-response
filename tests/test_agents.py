"""The LLM team's wiring and validation, with a scripted local model (no API key, no network).

The script plays each agent: it calls real tools through the gateway and answers from what they return.
This tests delegation, contracts and the code checks around the agents, not model quality.
"""
import asyncio
import json
from pathlib import Path

from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from incident_response.agents import READ_BUDGET
from incident_response.workflow import run

ROOT = Path(__file__).resolve().parents[1]


def returns(messages):
    return [(part.tool_name, part.content) for message in messages if isinstance(message, ModelRequest)
            for part in message.parts if isinstance(part, ToolReturnPart)]


def retried(messages):
    return any(isinstance(part, RetryPromptPart) for message in messages if isinstance(message, ModelRequest) for part in message.parts)


def call(name, args):
    return ModelResponse(parts=[ToolCallPart(name, args)])


def answer(info, data):
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, data)])


class Script:
    def __init__(self, fake_ref_once=False, reviewer_fails=False, act_without_review=False, reviewer_loops=False,
                 triage_repeats=False):
        self.fake_ref_once, self.reviewer_fails, self.act_without_review = fake_ref_once, reviewer_fails, act_without_review
        self.reviewer_loops, self.triage_repeats = reviewer_loops, triage_repeats

    async def __call__(self, messages, info):
        instructions, done = info.instructions or "", returns(messages)
        refs = [content["ref"] for _, content in done if isinstance(content, dict) and "ref" in content]
        if "You are the triage specialist" in instructions:
            if not done:
                return call("monitoring_list_alerts", {"device": "order-gateway", "size": 20})
            if len(done) == 1 or (self.triage_repeats and len(done) == 2):
                return call("tickets_search_issues", {"max_results": 10})
            issues = done[1][1]["issues"]
            incident = next(i["key"] for i in issues if i["project"] == "MRX" and i.get("component") == "order-gateway")
            related = [i["key"] for i in issues if i["key"] != incident and "acknowledg" in i["summary"].lower()]
            return answer(info, {"component": "order-gateway", "incident_ticket": incident, "related": related,
                                 "unrelated": [i["key"] for i in issues if i["key"] not in related + [incident]],
                                 "reasoning": "Same component and symptom", "evidence": refs})
        if "You are the investigator" in instructions:
            if not done:
                return call("read_metrics", {"component": "order-gateway", "per_instance": True})
            latest = done[0][1]["readings"][-1]["instances"]
            hot = next(name for name, values in latest.items() if values["memory_pct"] > 90)
            evidence = ["T99"] if self.fake_ref_once and not retried(messages) else refs
            return answer(info, {"component": "order-gateway", "cause_kind": "instance_memory", "cause": f"{hot} memory high",
                                 "evidence": evidence, "proposal": {"action": "restart_instance", "target": hot, "reason": "runbook"}})
        if "You are the dependency and safety reviewer" in instructions:
            if self.reviewer_fails:
                raise RuntimeError("reviewer model unavailable")
            if self.reviewer_loops and info.function_tools:  # what gpt-4.1-mini did: guess runbook names until stopped
                return call("read_runbook", {"name": f"memory pressure {len(done)}"})
            if not done:
                return call("check_link", {"source": "order-gateway", "target": "reference-db"})
            return answer(info, {"safe_to_attempt": True, "constraints": ["one instance"], "evidence": refs})
        asked = [name for name, _ in done]
        if "ask_triage" not in asked:
            return call("ask_triage", {"question": "Which component and tickets?"})
        if "ask_investigator" not in asked:
            return call("ask_investigator", {"question": "Cause and proposal?"})
        if self.act_without_review and not retried(messages):
            return answer(info, {"decision": "act", "rationale": "skipping review"})
        if "ask_reviewer" not in asked:
            return call("ask_reviewer", {"question": "Is this safe?"})
        review = dict(done)["ask_reviewer"]
        decision = "escalate" if "error" in review else "act"
        return answer(info, {"decision": decision, "rationale": "Based on the specialists"})


def execute(tmp_path, script, case="s03-alert-and-ticket", **kwargs):
    async def bounded():
        return await asyncio.wait_for(run(ROOT / "cases" / f"{case}.yaml", tmp_path / "run", mode="llm",
                                          model=FunctionModel(script), memory_path=tmp_path / "memory.db", **kwargs), 30)
    report = asyncio.run(bounded())
    state = json.loads((tmp_path / "run/checkpoint.json").read_text())
    return report, state, [a for a in state["actions"] if a["outcome"] == "completed"]


def test_orchestrator_delegates_and_code_executes(tmp_path):
    report, state, effects = execute(tmp_path, Script())
    assert report["status"] == "recovered" and report["incident_ticket"] == "MRX-2210"
    assert set(state["model_messages"]) == {"triage", "investigator", "reviewer", "orchestrator"}
    assert {e["caller"] for e in state["events"]} >= {"triage", "investigator", "reviewer", "harness"}
    assert state["usage"]["requests"] > 0 and len(effects) == 1


def test_invented_evidence_is_rejected_then_corrected(tmp_path):
    report, state, _ = execute(tmp_path, Script(fake_ref_once=True))
    assert report["status"] == "recovered"
    assert "Unknown evidence refs" in json.dumps(state["model_messages"]["investigator"])


def test_failure_between_specialists_is_detected_and_nothing_happens(tmp_path):
    report, state, effects = execute(tmp_path, Script(reviewer_fails=True))
    assert report["status"] == "escalated" and effects == []
    assert state["specialist_failures"] and "reviewer" in state["specialist_failures"][0]


def test_specialist_going_round_in_circles_is_capped_and_kept_in_the_trace(tmp_path):
    report, state, effects = execute(tmp_path, Script(reviewer_loops=True))
    assert report["status"] == "escalated" and effects == []  # its answer cites no evidence it read: rejected
    assert state["specialist_failures"] and "reviewer" in state["specialist_failures"][0]
    guesses = [e for e in state["events"] if e["caller"] == "reviewer" and e["tool"] == "read_runbook"]
    assert len(guesses) == READ_BUDGET["reviewer"]  # then the tools were withdrawn: no more reads, no more time
    seen = json.dumps(state["model_messages"]["reviewer"])  # the failed reviewer's conversation is in the trace
    assert "Do not guess runbook names" in seen and "That was your last read" in seen
    assert state["usage"]["requests"] < 40  # the team still had budget left


def test_repeated_read_is_refused_without_touching_the_systems(tmp_path):
    report, state, effects = execute(tmp_path, Script(triage_repeats=True))
    assert report["status"] == "recovered" and len(effects) == 1
    searches = [e for e in state["events"] if e["caller"] == "triage" and e["tool"] == "tickets.search_issues"]
    assert len(searches) == 1 and [c["reason"] for c in state["limited_calls"]] == ["repeated"]
    assert f"you already have this result as {searches[0]['ref']}" in json.dumps(state["model_messages"]["triage"])


def test_orchestrator_cannot_act_without_a_review(tmp_path):
    report, state, effects = execute(tmp_path, Script(act_without_review=True))
    assert "act needs the reviewer" in json.dumps(state["model_messages"]["orchestrator"])
    assert report["status"] == "recovered" and len(effects) == 1


def test_pipeline_with_llm_specialists(tmp_path):
    report, state, effects = execute(tmp_path, Script(), coordination="pipeline")
    assert report["status"] == "recovered" and "orchestrator" not in state["model_messages"]
