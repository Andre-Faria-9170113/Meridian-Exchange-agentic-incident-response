"""Validated boundaries between specialists, coordinator, executor and final report.

Every specialist output is a Pydantic model. Code validates it (schema here, cited
evidence in agents.py) before the next step uses it.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Action = Literal["restart_instance", "rollback_change", "none"]
CauseKind = Literal["instance_memory", "change", "dependency", "data_feed", "no_fault", "unknown"]
Status = Literal["recovered", "resolved", "escalated", "not_recovered", "insufficient_information", "refused"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Correlation(Contract):
    """Triage specialist: which component is affected and which tickets describe the same problem."""

    component: str = Field(description="Affected exchange component, e.g. order-gateway")
    incident_ticket: str | None = Field(None, description="Open MRX Incident ticket for this problem, if one exists")
    related: list[str] = Field(default_factory=list, description="Other tickets/complaints about the same problem")
    unrelated: list[str] = Field(default_factory=list, description="Tickets that were seen but describe a different problem")
    reasoning: str
    evidence: list[str] = Field(min_length=1, description="Tool result refs (e.g. T03) that support this grouping")

    @model_validator(mode="after")
    def disjoint(self):
        grouped = set(self.related) | ({self.incident_ticket} if self.incident_ticket else set())
        if grouped & set(self.unrelated):
            raise ValueError("A ticket cannot be both related and unrelated")
        return self


class Proposal(Contract):
    action: Action = "none"
    target: str = Field("", description="Exact instance id (restart_instance) or change id (rollback_change)")
    reason: str

    @model_validator(mode="after")
    def target_required(self):
        if self.action != "none" and not self.target:
            raise ValueError("An action requires an exact target")
        return self


class Finding(Contract):
    """Investigator: cause, cited evidence and at most one proposed mitigation."""

    component: str
    cause_kind: CauseKind
    cause: str
    change_id: str | None = Field(None, description="Change suspected or confirmed as the cause, if any")
    evidence: list[str] = Field(min_length=1)
    proposal: Proposal


class Review(Contract):
    """Dependency and safety reviewer: independent checks on the exact proposal."""

    safe_to_attempt: bool
    constraints: list[str]
    evidence: list[str] = Field(min_length=1)


class Decision(Contract):
    """Coordinator: what happens next. Code assembles the plan from the specialists' validated results."""

    decision: Literal["act", "no_action_needed", "escalate"]
    rationale: str


class Plan(Contract):
    correlation: Correlation
    finding: Finding
    review: Review | None
    decision: Decision


class Reading(BaseModel):
    """One metrics reading, validated before code bases a decision on it (extra fields tolerated)."""

    tick: int
    latency_ms: float
    error_rate: float
    instances: dict[str, dict] = Field(default_factory=dict)


class Metrics(BaseModel):
    ref: str
    component: str
    readings: list[Reading] = Field(min_length=1)
    source_ref: str


class Report(Contract):
    incident_id: str
    status: Status
    root_cause: str
    incident_ticket: str | None = None
    related_tickets: list[str] = Field(default_factory=list)
    evidence: list[str]
    actions_taken: list[str]
    refusals: list[str] = Field(default_factory=list)
    summary: str
