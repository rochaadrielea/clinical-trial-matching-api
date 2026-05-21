"""security.py — PII masking for patient data."""

from __future__ import annotations
from models import ExclusionRecord, Matching, MatchingReport, Patient, PatientTrialPair


def mask_name(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return "***"
    if len(parts) == 1:
        return f"{parts[0][0].upper()}."
    return f"{parts[0][0].upper()}. {parts[-1]}"


def mask_dob(dob_str: str) -> str:
    parts = dob_str.split("-")
    return f"{parts[0]}-XX-XX" if len(parts) == 3 else "XXXX-XX-XX"


def mask_patient(patient: Patient) -> dict:
    data = patient.model_dump(mode="json")
    data["name"] = mask_name(patient.name)
    data["date_of_birth"] = mask_dob(str(patient.date_of_birth))
    return data


def mask_patient_list(patients: list[Patient]) -> list[dict]:
    return [mask_patient(p) for p in patients]


def mask_pair(pair: PatientTrialPair) -> dict:
    data = pair.model_dump(mode="json")
    data["patient_name"] = mask_name(pair.patient_name)
    return data


def mask_exclusion(exc: ExclusionRecord) -> dict:
    data = exc.model_dump(mode="json")
    data["patient_name"] = mask_name(exc.patient_name)
    return data


def mask_matching(matching: Matching) -> dict:
    data = matching.model_dump(mode="json")
    data["input_patients"] = mask_patient_list(matching.input_patients)
    data["output_pairs"] = [mask_pair(p) for p in matching.output_pairs]
    data["exclusions"] = [mask_exclusion(e) for e in matching.exclusions]
    return data


def mask_report(report: MatchingReport) -> dict:
    data = report.model_dump(mode="json")
    data["pairs"] = [mask_pair(p) for p in report.pairs]
    data["exclusions"] = [mask_exclusion(e) for e in report.exclusions]
    data["unmatched_patients"] = [
        {**p, "name": mask_name(p.get("name", ""))} for p in report.unmatched_patients
    ]
    return data
