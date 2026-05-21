"""matching.py — Three-stage matching pipeline: rules → exclusivity → capacity."""

from __future__ import annotations
import operator as op_module
from dataclasses import dataclass, field
from typing import Any, Callable
from models import (EligibilityCriterion, ExclusionRecord, MatchingSummary,
                    Operator, Patient, PatientTrialPair, Trial)

_COMPARE: dict[Operator, Callable[[Any, Any], bool]] = {
    Operator.EQ: op_module.eq, Operator.NEQ: op_module.ne,
    Operator.GT: op_module.gt, Operator.GTE: op_module.ge,
    Operator.LT: op_module.lt, Operator.LTE: op_module.le,
}

FIELD_EXTRACTORS: dict[str, Callable[[Patient], Any]] = {
    "age": lambda p: p.age(), "gender": lambda p: p.gender,
    "conditions": lambda p: [c.value for c in p.conditions],
    "toxicity": lambda p: [t.value for t in p.toxicity],
    "allergies": lambda p: p.allergies,
}


@dataclass
class MatchingResult:
    pairs: list[PatientTrialPair] = field(default_factory=list)
    exclusions: list[ExclusionRecord] = field(default_factory=list)
    summary: MatchingSummary | None = None


def _evaluate_criterion(patient: Patient, criterion: EligibilityCriterion) -> bool:
    extractor = FIELD_EXTRACTORS.get(criterion.field)
    if extractor is None:
        return False
    val = extractor(patient)
    if criterion.op == Operator.CONTAINS:
        return str(criterion.value).lower() in val if isinstance(val, list) else str(criterion.value).lower() == str(val).lower()
    if criterion.op == Operator.NOT_CONTAINS:
        return str(criterion.value).lower() not in val if isinstance(val, list) else str(criterion.value).lower() != str(val).lower()
    cmp = _COMPARE.get(criterion.op)
    if cmp is None:
        return False
    try:
        return cmp(val, criterion.value)
    except TypeError:
        return False


def check_eligibility(patient: Patient, trial: Trial) -> str | None:
    for c in trial.eligibility_criteria:
        if not _evaluate_criterion(patient, c):
            actual = FIELD_EXTRACTORS.get(c.field, lambda _: "?")
            return f"failed rule: {c.field} {c.op.value} {c.value} (actual: {actual(patient)})"
    return None


def check_exclusivity(patient: Patient, trial: Trial) -> str | None:
    if trial.start_date is None:
        return None
    for tp in patient.trial_participations:
        if tp.overlaps(trial.start_date, trial.end_date):
            end_str = str(tp.end_date) if tp.end_date else "ongoing"
            return f"exclusivity conflict: already enrolled in trial {tp.trial_id} ({tp.start_date} to {end_str})"
    return None


def run_matching(patients: list[Patient], trials: list[Trial], *,
                 enforce_exclusivity: bool = True) -> MatchingResult:
    pairs, exclusions, matched_ids = [], [], set()
    for trial in trials:
        eligible = []
        for patient in patients:
            rule_reason = check_eligibility(patient, trial)
            if rule_reason:
                exclusions.append(ExclusionRecord(patient_id=patient.id, patient_name=patient.name,
                                                  trial_id=trial.id, trial_name=trial.name, reason=rule_reason))
                continue
            if enforce_exclusivity:
                excl_reason = check_exclusivity(patient, trial)
                if excl_reason:
                    exclusions.append(ExclusionRecord(patient_id=patient.id, patient_name=patient.name,
                                                      trial_id=trial.id, trial_name=trial.name, reason=excl_reason))
                    continue
            eligible.append(patient)
        assigned = eligible[:trial.max_participants]
        if len(assigned) < trial.min_participants:
            for p in assigned:
                exclusions.append(ExclusionRecord(patient_id=p.id, patient_name=p.name, trial_id=trial.id,
                    trial_name=trial.name, reason=f"trial requires min {trial.min_participants} but only {len(assigned)} eligible"))
            continue
        for p in assigned:
            pairs.append(PatientTrialPair(patient_id=p.id, patient_name=p.name, trial_id=trial.id, trial_name=trial.name))
            matched_ids.add(p.id)
    summary = MatchingSummary(patients_considered=len(patients), trials_considered=len(trials),
        patients_matched=len(matched_ids), patients_unmatched=len(patients) - len(matched_ids),
        total_pairs=len(pairs), total_exclusions=len(exclusions))
    return MatchingResult(pairs=pairs, exclusions=exclusions, summary=summary)
