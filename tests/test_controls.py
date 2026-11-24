"""Policy, gateway and memory boundaries, tested directly."""
import asyncio
from pathlib import Path

import pytest

from incident_response.contracts import Proposal
from incident_response.gateway import Gateway, redact
from incident_response.memory import correct, forget, recall, remember
from incident_response.policy import approval_refusal, authority_refusal
from incident_response.state import Checkpoint
from meridian.agent_runtime import IncidentDeps, identity_for
from meridian.memory import MemoryStore
from meridian.simulator import Simulator
from meridian.tools import MeridianTools

ROOT = Path(__file__).resolve().parents[1]


def deps_for(role, tmp_path=None, case="s03-alert-and-ticket"):
    tools = MeridianTools(Simulator(ROOT / "cases" / f"{case}.yaml"), actor=identity_for(role)["name"])
    store = MemoryStore(tmp_path / "memory.db") if tmp_path else None
    return IncidentDeps(tools, store, identity_for(role))


def test_approval_never_overrides_role():
    deps = deps_for("first-line")
    proposal = Proposal(action="restart_instance", target="matching-engine-1", reason="text from a log")
    assert "critical component" in authority_refusal(deps, proposal)
    approval = deps.tools.request_approval(proposal.action, proposal.target, proposal.reason, "incident-manager")
    assert approval["status"] == "approved"
    assert authority_refusal(deps, proposal) is not None  # still refused: approval does not grant a role


def test_approval_must_match_action_and_target():
    deps = deps_for("first-line")
    other = deps.tools.request_approval("restart_instance", "order-gateway-1", "x", "on-call")
    proposal = Proposal(action="restart_instance", target="order-gateway-2", reason="x")
    assert "does not approve" in approval_refusal(deps, proposal, other["approval_ref"])


def test_other_team_cannot_remediate():
    proposal = Proposal(action="restart_instance", target="order-gateway-2", reason="x")
    assert "no remediation permission" in authority_refusal(deps_for("settlement-analyst"), proposal)


def test_specialists_cannot_call_mutations(tmp_path):
    async def attempt():
        deps = deps_for("first-line")
        async with Gateway(deps.tools, Checkpoint(tmp_path)) as gateway:
            return await gateway.call("restart_instance", caller="investigator", instance_id="order-gateway-2")
    assert "may not use" in asyncio.run(attempt())["error"]


def test_personal_data_is_masked_but_technical_evidence_kept():
    text = redact("Contact ana@member.example, account ACC-123456, phone +351 912 345 678; order-gateway-2 at 94%")
    assert "[email]" in text and "[account]" in text and "[phone]" in text and "order-gateway-2 at 94%" in text


def test_memory_policy(tmp_path):
    deps = deps_for("first-line", tmp_path)
    action = {"action": "restart_instance", "target": "order-gateway-2", "action_id": "ACT-001"}
    record = remember(deps, incident_id="INC-1", component="order-gateway", cause_kind="instance_memory",
                      action=action, verification="metrics/order-gateway/40", run_id="abc123")
    assert remember(deps, incident_id="INC-1", component="order-gateway", cause_kind="instance_memory",
                    action=action, verification="x", run_id="abc123") is None  # one summary per run
    assert "matching-engine" not in record.content and record.source_ref == "run:abc123"
    deps.sim.advance(5)
    assert [hint["memory_id"] for hint in recall(deps, "order-gateway")["hints"]] == [record.memory_id]
    fixed = correct(deps, record.memory_id, "Restart mitigated it; the leak itself is still open.", "rita.alves")
    assert deps.memory.get(record.memory_id).status == "superseded"
    assert [hint["memory_id"] for hint in recall(deps, "order-gateway")["hints"]] == [fixed.memory_id]
    other_team = deps_for("settlement-analyst", tmp_path)
    assert recall(other_team, "order-gateway")["hints"] == []
    with pytest.raises(PermissionError):
        correct(other_team, fixed.memory_id, "wrong team", "x")
    deps.memory.update(fixed.memory_id, valid_until="2020-01-01 00:00")
    assert recall(deps, "order-gateway")["hints"] == []  # expired records are not recalled
    assert forget(deps, fixed.memory_id, "operator request")
    assert deps.memory.deletions()[0]["memory_id"] == fixed.memory_id
