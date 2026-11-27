"""Policy, gateway and memory boundaries, tested directly."""
import asyncio
from pathlib import Path

import pytest

from incident_response.contracts import Proposal
from incident_response.gateway import Gateway, redact
from incident_response.memory import correct, forget, recall, remember, store_clock
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
    on_call, at = identity_for("on-call"), store_clock(deps.memory)
    with pytest.raises(PermissionError):  # the agent may not rewrite its own memory
        correct(deps.memory, record.memory_id, "x", "x", operator=identity_for("first-line"), at=at)
    fixed = correct(deps.memory, record.memory_id, "Restart mitigated it; the leak itself is still open.",
                    "ticket MRX-2210", operator=on_call, at=at)
    assert deps.memory.get(record.memory_id).status == "superseded" and fixed.author == "rita.alves"
    with pytest.raises(ValueError):  # a superseded record is not corrected twice
        correct(deps.memory, record.memory_id, "x", "x", operator=on_call, at=at)
    assert [hint["memory_id"] for hint in recall(deps, "order-gateway")["hints"]] == [fixed.memory_id]
    other_team = deps_for("settlement-analyst", tmp_path)
    assert recall(other_team, "order-gateway")["hints"] == []
    with pytest.raises(PermissionError):
        correct(deps.memory, fixed.memory_id, "wrong team", "x", operator=identity_for("settlement-analyst"), at=at)
    deps.memory.update(fixed.memory_id, valid_until="2020-01-01 00:00")
    assert recall(deps, "order-gateway")["hints"] == []  # expired records are not recalled
    assert forget(deps.memory, fixed.memory_id, "operator request", operator=on_call, at=store_clock(deps.memory))
    assert deps.memory.deletions()[0]["memory_id"] == fixed.memory_id


def test_memory_operator_cli(tmp_path):
    """The operator commands: list by team, correct and forget by a person, never by the agent's identity."""
    import subprocess
    import sys

    deps = deps_for("first-line", tmp_path)
    record = remember(deps, incident_id="INC-1", component="order-gateway", cause_kind="instance_memory",
                      action={"action": "restart_instance", "target": "order-gateway-2", "action_id": "ACT-001"},
                      verification="metrics/order-gateway/40", run_id="cli123")

    def cli(*args):
        return subprocess.run([sys.executable, "-m", "incident_response", "memory", "--memory", str(deps.memory.path), *args],
                              cwd=ROOT, capture_output=True, text=True)

    assert record.memory_id in cli("list").stdout
    assert "0 record(s)" in cli("--role", "settlement-analyst", "list").stdout
    refused = cli("--role", "first-line", "forget", record.memory_id, "--reason", "x")
    assert refused.returncode == 1 and "Only a person" in refused.stderr
    assert cli("correct", record.memory_id, "--text", "leak not fixed", "--source", "on-call review").returncode == 0
    fixed = next(r for r in deps.memory.all() if r.supersedes == record.memory_id)
    assert fixed.author == "rita.alves" and fixed.created_at > record.created_at  # on the store's clock, not wall time
    assert cli("forget", fixed.memory_id, "--reason", "vendor fixed it").returncode == 0
    assert "vendor fixed it" in cli("list", "--all").stdout


def test_recall_includes_what_the_component_depends_on(tmp_path):
    deps = deps_for("first-line", tmp_path)
    deps.sim.advance(5)
    note = deps.memory.add(kind="shift_note", subject="reference-db", content="CHG-9 still active", source_type="user",
                           source_ref="rita.alves", author="rita.alves", team="trading-ops", created_at="2026-11-04 08:00",
                           valid_until="2026-11-10 00:00", confidence=0.9)
    hints = recall(deps, "order-gateway")
    assert "reference-db" in hints["subjects"] and [h["memory_id"] for h in hints["hints"]] == [note.memory_id]
    assert recall(deps, "order-gateway-2")["subjects"] == ["order-gateway-2"]  # not a component: that subject only


def test_recovery_follows_the_runbook_of_the_action():
    """milestone-2 evidence: after a correct rollback the error rate was 0.1% while latency still drained (36 ms)."""
    from incident_response.contracts import Reading
    from incident_response.guards import healthy

    draining = Reading(tick=141, latency_ms=36.2, error_rate=0.001)
    assert healthy("order-gateway", draining, "rollback_change")  # reference-db-connections: errors below 1%
    assert not healthy("order-gateway", draining, "restart_instance")  # order-gateway-latency: also below 20 ms
    assert not healthy("order-gateway", draining)  # no action: the component's own health
    assert not healthy("order-gateway", Reading(tick=141, latency_ms=5, error_rate=0.4), "rollback_change")
