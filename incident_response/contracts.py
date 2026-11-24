"""Validated boundaries between specialists, executor and final report."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Proposal(Contract):
    action: Literal["restart_instance", "rollback_change", "none"] = "none"
    target: str = ""
    reason: str

    @model_validator(mode="after")
    def target_required(self):
        if self.action != "none" and not self.target:
            raise ValueError("An action requires an exact target")
        return self


class Finding(Contract):
    cause: str
    evidence: list[str] = Field(min_length=1)
    proposal: Proposal


class Review(Contract):
    safe_to_attempt: bool
    constraints: list[str]
    evidence: list[str] = Field(min_length=1)


class Plan(Contract):
    finding: Finding
    review: Review


class Reading(Contract):
    tick: int
    time: str
    latency_ms: float
    error_rate: float
    queue_depth: float
    cpu_pct: float
    memory_pct: float
    disk_pct: float
    version: str
    instances: dict[str, dict[str, Any]]


class Metrics(Contract):
    component: str
    window_ticks: int
    readings: list[Reading] = Field(min_length=1)
    source_ref: str


class Report(Contract):
    incident_id: str
    status: Literal["recovered", "not_recovered", "insufficient_information", "refused"]
    root_cause: str
    evidence: list[str]
    actions_taken: list[str]
    summary: str
