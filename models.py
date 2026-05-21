"""
models.py — Pydantic v2 data contracts for the Clinical Trial Matching API.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

PATIENT_UUID_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


class Condition(str, Enum):
    DIABETES = "diabetes"
    HYPERTENSION = "hypertension"


class Toxicity(str, Enum):
    SMOKING = "smoking"
    ALCOHOL = "alcohol"


class Operator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"


class AuditEventType(str, Enum):
    PATIENT_CREATED = "patient_created"
    PATIENT_DUPLICATE = "patient_duplicate"
    PATIENT_REJECTED = "patient_rejected"
    TRIAL_CREATED = "trial_created"
    MATCHING_EXECUTED = "matching_executed"


class TrialParticipation(BaseModel):
    trial_id: str
    start_date: date
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def end_after_start(self) -> "TrialParticipation":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    def overlaps(self, other_start: date, other_end: date | None) -> bool:
        self_end = self.end_date or date.max
        other_end_resolved = other_end or date.max
        return self.start_date < other_end_resolved and other_start < self_end


class EligibilityCriterion(BaseModel):
    field: str
    op: Operator
    value: Any

    @field_validator("field")
    @classmethod
    def strip_field(cls, v: str) -> str:
        return v.strip().lower()


def make_patient_id(name: str, dob: date) -> str:
    key = f"{name.strip().lower()}:{dob.isoformat()}"
    return str(uuid.uuid5(PATIENT_UUID_NAMESPACE, key))


class PatientCreate(BaseModel):
    name: str
    date_of_birth: date
    gender: str
    conditions: list[Condition] = Field(default_factory=list)
    toxicity: list[Toxicity] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    trial_participations: list[TrialParticipation] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("gender")
    @classmethod
    def gender_not_blank(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("gender must not be blank")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def dob_in_past(cls, v: date) -> date:
        if v >= date.today():
            raise ValueError("date_of_birth must be in the past")
        return v

    @field_validator("allergies")
    @classmethod
    def strip_allergies(cls, v: list[str]) -> list[str]:
        return [a.strip().lower() for a in v if a.strip()]

    @field_validator("conditions")
    @classmethod
    def dedupe_conditions(cls, v: list[Condition]) -> list[Condition]:
        return list(dict.fromkeys(v))

    @field_validator("toxicity")
    @classmethod
    def dedupe_toxicity(cls, v: list[Toxicity]) -> list[Toxicity]:
        return list(dict.fromkeys(v))


class Patient(PatientCreate):
    id: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            self.id = make_patient_id(self.name, self.date_of_birth)

    def age(self) -> int:
        today = date.today()
        born = self.date_of_birth
        return today.year - born.year - (
            (today.month, today.day) < (born.month, born.day)
        )

    def has_active_participation(self, check_start: date, check_end: date | None = None) -> bool:
        return any(tp.overlaps(check_start, check_end) for tp in self.trial_participations)


class TrialCreate(BaseModel):
    model_config = {"populate_by_name": True}

    name: str
    eligibility_criteria: list[EligibilityCriterion] = Field(
        default_factory=list, alias="criteria",
    )
    min_participants: int = Field(ge=0, default=0)
    max_participants: int = Field(ge=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @model_validator(mode="after")
    def validate_constraints(self) -> "TrialCreate":
        if self.min_participants > self.max_participants:
            raise ValueError("min_participants must be <= max_participants")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("trial end_date must be on or after start_date")
        return self


class Trial(TrialCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class RejectedRecord(BaseModel):
    record: dict[str, Any]
    reasons: list[str]


class BatchResult(BaseModel):
    accepted: list[Patient]
    rejected: list[RejectedRecord]


class MatchingRequest(BaseModel):
    patient_ids: Optional[list[str]] = None
    trial_ids: Optional[list[str]] = None
    enforce_exclusivity: bool = True


class PatientTrialPair(BaseModel):
    patient_id: str
    patient_name: str
    trial_id: str
    trial_name: str


class ExclusionRecord(BaseModel):
    patient_id: str
    patient_name: str
    trial_id: str
    trial_name: str
    reason: str


class MatchingSummary(BaseModel):
    patients_considered: int
    trials_considered: int
    patients_matched: int
    patients_unmatched: int
    total_pairs: int
    total_exclusions: int


class Matching(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_datetime: datetime = Field(default_factory=lambda: datetime.now(UTC))
    enforce_exclusivity: bool = True
    input_patients: list[Patient]
    input_trials: list[Trial]
    output_pairs: list[PatientTrialPair]
    exclusions: list[ExclusionRecord] = Field(default_factory=list)
    summary: Optional[MatchingSummary] = None


class MatchingReport(BaseModel):
    matching_id: str
    run_datetime: datetime
    summary: MatchingSummary
    pairs: list[PatientTrialPair]
    exclusions: list[ExclusionRecord]
    unmatched_patients: list[dict[str, str]]


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: AuditEventType
    entity_type: str
    entity_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
