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
                 triage_repeats=False, strays=False, follow_up=False):
        self.fake_ref_once, self.reviewer_fails, self.act_without_review = fake_ref_once, reviewer_fails, act_without_review
        self.reviewer_loops, self.triage_repeats, self.strays = reviewer_loops, triage_repeats, strays
        self.follow_up = follow_up

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
            if self.strays and not done:  # reads a dependency first, then calls an unhealthy gateway no_fault
                return call("read_metrics", {"component": "reference-db", "per_instance": True})
            done = [(name, content) for name, content in done if "error" not in content]
            if not done:
                return call("read_metrics", {"component": "order-gateway", "per_instance": True})
            if self.strays and not retried(messages):
                return answer(info, {"component": "order-gateway", "cause_kind": "no_fault", "cause": "looks fine",
                                     "evidence": refs, "proposal": {"action": "none", "reason": "no fault"}})
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
        if self.follow_up and asked.count("ask_investigator") == 1:
            return call("ask_investigator", {"question": "Are you sure about the instance?"})
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


def test_investigator_stays_on_its_component_and_cannot_call_a_fault_no_fault(tmp_path):
    report, state, effects = execute(tmp_path, Script(strays=True))
    assert report["status"] == "recovered" and len(effects) == 1
    assert [(c["caller"], c["reason"]) for c in state["limited_calls"]] == [("investigator", "scope")]
    assert not any(e["caller"] == "investigator" and e["args"].get("component") == "reference-db" for e in state["events"])
    assert "no_fault contradicts" in json.dumps(state["model_messages"]["investigator"])


def test_orchestrator_cannot_act_without_a_review(tmp_path):
    report, state, effects = execute(tmp_path, Script(act_without_review=True))
    assert "act needs the reviewer" in json.dumps(state["model_messages"]["orchestrator"])
    assert report["status"] == "recovered" and len(effects) == 1


def test_pipeline_with_llm_specialists(tmp_path):
    report, state, effects = execute(tmp_path, Script(), coordination="pipeline")
    assert report["status"] == "recovered" and "orchestrator" not in state["model_messages"]


def test_follow_up_answers_from_what_was_read_without_reading_again(tmp_path):
    report, state, effects = execute(tmp_path, Script(follow_up=True))
    assert report["status"] == "recovered" and len(effects) == 1
    assert len(state["model_messages"]["investigator"]) == 2  # two answers ...
    assert [e["tool"] for e in state["events"] if e["caller"] == "investigator"] == ["read_metrics"]  # ... one read


def test_errors_finding_must_have_searched_the_logs_for_the_change():
    from types import SimpleNamespace

    from incident_response.agents import unsearched_change
    from incident_response.contracts import Finding

    reading = {"tick": 1, "latency_ms": 5.0, "error_rate": 0.4, "instances": {}}
    events = [{"ref": "T01", "caller": "investigator", "tool": "read_metrics", "args": {},
               "result": {"component": "order-gateway", "readings": [reading]}}]
    seat = SimpleNamespace(gateway=SimpleNamespace(checkpoint=SimpleNamespace(data={"events": events})), caller="investigator")
    finding = Finding(component="order-gateway", cause_kind="dependency", cause="reference-db unavailable",
                      evidence=["T01"], proposal={"action": "none", "reason": "dependency"})
    assert "list recent changes" in unsearched_change(seat, finding)
    events.append({"ref": "T02", "caller": "investigator", "tool": "recent_changes", "args": {},
                   "result": {"changes": [{"change_id": "CHG-1", "active": True}, {"change_id": "CHG-0", "active": True}]}})
    events.append({"ref": "T03", "caller": "investigator", "tool": "read_logs", "args": {"level": "ERROR"}, "result": {}})
    assert "contains='CHG-1'" in unsearched_change(seat, finding)  # searching by level is not searching for the change
    events.append({"ref": "T04", "caller": "investigator", "tool": "read_logs", "args": {"contains": "CHG-1"}, "result": {}})
    assert unsearched_change(seat, finding) is None
    named = finding.model_copy(update={"cause_kind": "change", "change_id": "CHG-0"})
    assert "CHG-0" in unsearched_change(seat, named)  # the change it names must be the one searched
    memory = finding.model_copy(update={"cause_kind": "instance_memory"})
    assert unsearched_change(seat, memory) is None
