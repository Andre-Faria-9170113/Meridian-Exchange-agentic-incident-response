"""Exercise the three-agent wiring using a scripted local model."""
import asyncio
import json
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from incident_response.agents import fixture_plan
from incident_response.workflow import run

ROOT = Path(__file__).resolve().parents[1]


async def scripted_model(messages, info):
    returns = {part.tool_name: part.content for message in messages for part in message.parts
               if isinstance(part, ToolReturnPart)}
    if info.function_tools:
        for tool in ["ask_investigator", "ask_safety_reviewer"]:
            if tool not in returns:
                return ModelResponse(parts=[ToolCallPart(tool, {})])
        def as_data(value):
            if isinstance(value, BaseModel):
                return value.model_dump()
            return json.loads(value) if isinstance(value, str) else value
        output = {"finding": as_data(returns["ask_investigator"]),
                  "review": as_data(returns["ask_safety_reviewer"])}
    else:
        prompt = next(part.content for message in messages for part in message.parts if isinstance(part, UserPromptPart))
        payload = json.loads(prompt)
        if "finding" in payload:
            output = fixture_plan(payload["evidence"]).review.model_dump()
        else:
            output = fixture_plan(payload).finding.model_dump()
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])


def test_orchestrator_delegates_to_both_specialists(tmp_path):
    async def bounded_run():
        return await asyncio.wait_for(run(ROOT / "cases/s03-alert-and-ticket.yaml", tmp_path / "run",
                                          mode="llm", model=FunctionModel(scripted_model)), timeout=15)
    report = asyncio.run(bounded_run())
    assert report["status"] == "recovered", report
    state = json.loads((tmp_path / "run/checkpoint.json").read_text())
    assert set(state["model_messages"]) == {"investigator", "reviewer", "orchestrator"}
    assert state["usage"]["requests"] == 5


def test_failure_between_specialists_stops_before_action(tmp_path):
    async def reviewer_unavailable(messages, info):
        if "You are the dependency and safety specialist" in (info.instructions or ""):
            raise RuntimeError("Safety specialist unavailable")
        return await scripted_model(messages, info)

    async def bounded_run():
        return await asyncio.wait_for(run(ROOT / "cases/s03-alert-and-ticket.yaml", tmp_path / "run",
            mode="llm", model=FunctionModel(reviewer_unavailable)), timeout=15)
    report = asyncio.run(bounded_run())
    assert report["status"] == "insufficient_information"
    state = json.loads((tmp_path / "run/checkpoint.json").read_text())
    assert state["actions"] == []
    assert "investigator" in state["model_messages"]
