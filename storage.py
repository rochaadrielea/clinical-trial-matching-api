"""storage.py — In-memory repositories with audit logging."""

from __future__ import annotations
from typing import Any
from audit import AuditLog
from models import (AuditEventType, BatchResult, Matching, Patient,
                    PatientCreate, RejectedRecord, Trial, TrialCreate)


class PatientRepo:
    def __init__(self, audit_log: AuditLog) -> None:
        self._store: dict[str, Patient] = {}
        self._audit = audit_log

    def add(self, data: PatientCreate) -> tuple[Patient, bool]:
        patient = Patient(**data.model_dump())
        if patient.id in self._store:
            self._audit.append(AuditEventType.PATIENT_DUPLICATE, "patient",
                               patient.id, {"name": data.name, "date_of_birth": str(data.date_of_birth)})
            return self._store[patient.id], False
        self._store[patient.id] = patient
        self._audit.append(AuditEventType.PATIENT_CREATED, "patient",
                           patient.id, patient.model_dump(mode="json"))
        return patient, True

    def add_batch(self, records: list[dict[str, Any]]) -> BatchResult:
        accepted, rejected = [], []
        for raw in records:
            try:
                data = PatientCreate(**raw)
                patient, _ = self.add(data)
                accepted.append(patient)
            except Exception as exc:
                reasons = _extract_errors(exc)
                rejected.append(RejectedRecord(record=raw, reasons=reasons))
                self._audit.append(AuditEventType.PATIENT_REJECTED, "patient",
                                   None, {"record": raw, "reasons": reasons})
        return BatchResult(accepted=accepted, rejected=rejected)

    def get(self, pid: str) -> Patient | None:
        return self._store.get(pid)

    def list_all(self) -> list[Patient]:
        return list(self._store.values())


class TrialRepo:
    def __init__(self, audit_log: AuditLog) -> None:
        self._store: dict[str, Trial] = {}
        self._audit = audit_log

    def add(self, data: TrialCreate) -> Trial:
        trial = Trial(**data.model_dump())
        self._store[trial.id] = trial
        self._audit.append(AuditEventType.TRIAL_CREATED, "trial",
                           trial.id, trial.model_dump(mode="json"))
        return trial

    def get(self, tid: str) -> Trial | None:
        return self._store.get(tid)

    def list_all(self) -> list[Trial]:
        return list(self._store.values())


class MatchingRepo:
    def __init__(self, audit_log: AuditLog) -> None:
        self._store: dict[str, Matching] = {}
        self._audit = audit_log

    def add(self, matching: Matching) -> Matching:
        self._store[matching.id] = matching
        self._audit.append(AuditEventType.MATCHING_EXECUTED, "matching", matching.id,
                           {"summary": matching.summary.model_dump() if matching.summary else {},
                            "pair_count": len(matching.output_pairs)})
        return matching

    def get(self, mid: str) -> Matching | None:
        return self._store.get(mid)

    def list_all(self) -> list[Matching]:
        return list(self._store.values())


def _extract_errors(exc: Exception) -> list[str]:
    if hasattr(exc, "errors"):
        return [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()]
    return [str(exc)]
