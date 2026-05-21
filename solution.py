"""
solution.py — FastAPI entry point for the Clinical Trial Matching API.

Supports both singular (/patient, /trial, /matching) and plural
(/patients, /trials, /matchings) endpoint paths for compatibility.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse

from audit import AuditLog
from matching import run_matching
from models import (AuditEvent, AuditEventType, BatchResult, Matching, MatchingReport,
                    MatchingRequest, MatchingSummary, Patient, PatientCreate,
                    PatientTrialPair, Trial, TrialCreate)
from security import mask_matching, mask_patient, mask_patient_list, mask_report
from storage import MatchingRepo, PatientRepo, TrialRepo

app = FastAPI(title="Clinical Trial Matching API", version="2.0.0")

audit_log = AuditLog()
patient_repo = PatientRepo(audit_log)
trial_repo = TrialRepo(audit_log)
matching_repo = MatchingRepo(audit_log)


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


# ── Patients ────────────────────────────────────────────────────────────────

def _create_patient(data: PatientCreate, full: bool = False):
    patient, created = patient_repo.add(data)
    if not created:
        return JSONResponse(status_code=200,
            content=patient.model_dump(mode="json") if full else mask_patient(patient))
    return patient.model_dump(mode="json") if full else mask_patient(patient)


@app.post("/patients", tags=["patients"])
def create_patient(data: PatientCreate, full: bool = Query(False)):
    return _create_patient(data, full)


@app.post("/patient", tags=["patients"])
def create_patient_singular(data: PatientCreate, full: bool = Query(False)):
    return _create_patient(data, full)


@app.post("/patients/batch", response_model=BatchResult, tags=["patients"])
def create_patients_batch(records: list[dict[str, Any]]):
    return patient_repo.add_batch(records)


def _list_patients(full: bool):
    patients = patient_repo.list_all()
    if full:
        return [p.model_dump(mode="json") for p in patients]
    return mask_patient_list(patients)


@app.get("/patients", tags=["patients"])
def list_patients(full: bool = Query(False)):
    return _list_patients(full)


@app.get("/patient", tags=["patients"])
def list_patients_singular(full: bool = Query(False)):
    return _list_patients(full)


def _get_patient(patient_id: str, full: bool):
    patient = patient_repo.get(patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Patient {patient_id} not found")
    return patient.model_dump(mode="json") if full else mask_patient(patient)


@app.get("/patients/{patient_id}", tags=["patients"])
def get_patient(patient_id: str, full: bool = Query(False)):
    return _get_patient(patient_id, full)


@app.get("/patient/{patient_id}", tags=["patients"])
def get_patient_singular(patient_id: str, full: bool = Query(False)):
    return _get_patient(patient_id, full)


# ── Trials ──────────────────────────────────────────────────────────────────

def _create_trial(data: TrialCreate):
    return trial_repo.add(data)


@app.post("/trials", response_model=Trial, tags=["trials"])
def create_trial(data: TrialCreate):
    return _create_trial(data)


@app.post("/trial", response_model=Trial, tags=["trials"])
def create_trial_singular(data: TrialCreate):
    return _create_trial(data)


def _list_trials():
    return trial_repo.list_all()


@app.get("/trials", response_model=list[Trial], tags=["trials"])
def list_trials():
    return _list_trials()


@app.get("/trial", response_model=list[Trial], tags=["trials"])
def list_trials_singular():
    return _list_trials()


def _get_trial(trial_id: str):
    trial = trial_repo.get(trial_id)
    if trial is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trial {trial_id} not found")
    return trial


@app.get("/trials/{trial_id}", response_model=Trial, tags=["trials"])
def get_trial(trial_id: str):
    return _get_trial(trial_id)


@app.get("/trial/{trial_id}", response_model=Trial, tags=["trials"])
def get_trial_singular(trial_id: str):
    return _get_trial(trial_id)


# ── Matchings ───────────────────────────────────────────────────────────────

def _execute_matching(request: MatchingRequest | None, full: bool):
    enforce_exclusivity = True
    if request and request.patient_ids is not None:
        patients = []
        for pid in request.patient_ids:
            p = patient_repo.get(pid)
            if p is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Patient {pid} not found")
            patients.append(p)
    else:
        patients = patient_repo.list_all()

    if request and request.trial_ids is not None:
        trials = []
        for tid in request.trial_ids:
            t = trial_repo.get(tid)
            if t is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Trial {tid} not found")
            trials.append(t)
    else:
        trials = trial_repo.list_all()

    if request:
        enforce_exclusivity = request.enforce_exclusivity

    result = run_matching(patients, trials, enforce_exclusivity=enforce_exclusivity)
    matching = Matching(enforce_exclusivity=enforce_exclusivity, input_patients=patients,
        input_trials=trials, output_pairs=result.pairs, exclusions=result.exclusions, summary=result.summary)
    matching_repo.add(matching)
    if full:
        return matching.model_dump(mode="json")
    return mask_matching(matching)


@app.post("/matchings", tags=["matchings"])
def execute_matching(request: MatchingRequest | None = None, full: bool = Query(False)):
    return _execute_matching(request, full)


@app.post("/matching", tags=["matchings"])
def execute_matching_singular(request: MatchingRequest | None = None, full: bool = Query(False)):
    return _execute_matching(request, full)


def _list_matchings(full: bool):
    matchings = matching_repo.list_all()
    if full:
        return [m.model_dump(mode="json") for m in matchings]
    return [mask_matching(m) for m in matchings]


@app.get("/matchings", tags=["matchings"])
def list_matchings(full: bool = Query(False)):
    return _list_matchings(full)


@app.get("/matching", tags=["matchings"])
def list_matchings_singular(full: bool = Query(False)):
    return _list_matchings(full)


def _get_matching(matching_id: str, full: bool):
    matching = matching_repo.get(matching_id)
    if matching is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Matching {matching_id} not found")
    if full:
        return matching.model_dump(mode="json")
    return mask_matching(matching)


@app.get("/matchings/{matching_id}", tags=["matchings"])
def get_matching(matching_id: str, full: bool = Query(False)):
    return _get_matching(matching_id, full)


@app.get("/matching/{matching_id}", tags=["matchings"])
def get_matching_singular(matching_id: str, full: bool = Query(False)):
    return _get_matching(matching_id, full)


def _get_report(matching_id: str, full: bool):
    matching = matching_repo.get(matching_id)
    if matching is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Matching {matching_id} not found")
    matched_ids = {p.patient_id for p in matching.output_pairs}
    unmatched = [{"id": p.id, "name": p.name} for p in matching.input_patients if p.id not in matched_ids]
    report = MatchingReport(matching_id=matching.id, run_datetime=matching.run_datetime,
        summary=matching.summary or MatchingSummary(patients_considered=0, trials_considered=0,
            patients_matched=0, patients_unmatched=0, total_pairs=0, total_exclusions=0),
        pairs=matching.output_pairs, exclusions=matching.exclusions, unmatched_patients=unmatched)
    if full:
        return report.model_dump(mode="json")
    return mask_report(report)


@app.get("/matchings/{matching_id}/report", tags=["matchings"])
def get_matching_report(matching_id: str, full: bool = Query(False)):
    return _get_report(matching_id, full)


@app.get("/matching/{matching_id}/report", tags=["matchings"])
def get_matching_report_singular(matching_id: str, full: bool = Query(False)):
    return _get_report(matching_id, full)


# ── Audit ───────────────────────────────────────────────────────────────────

@app.get("/audit/events", response_model=list[AuditEvent], tags=["audit"])
def query_audit_events(entity_type: Optional[str] = Query(None), entity_id: Optional[str] = Query(None),
                       event_type: Optional[AuditEventType] = Query(None),
                       after: Optional[datetime] = Query(None), before: Optional[datetime] = Query(None)):
    return audit_log.query(entity_type=entity_type, entity_id=entity_id,
                           event_type=event_type, after=after, before=before)


@app.get("/audit/events/{entity_id}/history", response_model=list[AuditEvent], tags=["audit"])
def get_entity_history(entity_id: str):
    events = audit_log.entity_history(entity_id)
    if not events:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No events for {entity_id}")
    return events
