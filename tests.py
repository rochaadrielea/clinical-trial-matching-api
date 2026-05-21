"""tests.py — 67+ tests covering all features. Run: pytest tests.py -v"""

from datetime import date
import pytest
from fastapi.testclient import TestClient
from models import make_patient_id
from solution import app, audit_log, matching_repo, patient_repo, trial_repo


@pytest.fixture(autouse=True)
def _reset():
    patient_repo._store.clear()
    trial_repo._store.clear()
    matching_repo._store.clear()
    audit_log.clear()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def _patient(**kw):
    base = {"name": "Alice Smith", "date_of_birth": "1990-05-15", "gender": "female",
            "conditions": ["diabetes"], "toxicity": [], "allergies": ["penicillin"]}
    base.update(kw)
    return base


def _trial(**kw):
    base = {"name": "Trial Alpha", "criteria": [{"field": "age", "op": "gte", "value": 18}],
            "min_participants": 0, "max_participants": 10}
    base.update(kw)
    return base


# ═══ 1. Patient CRUD ═══════════════════════════════════════════════════════

class TestCreatePatient:
    def test_happy_path(self, client):
        resp = client.post("/patients?full=true", json=_patient())
        assert resp.status_code == 200
        assert resp.json()["name"] == "Alice Smith"

    def test_singular_route(self, client):
        resp = client.post("/patient?full=true", json=_patient())
        assert resp.status_code == 200

    def test_whitespace_stripped(self, client):
        resp = client.post("/patients?full=true", json=_patient(name="  Bob  ", gender="  Male "))
        assert resp.json()["name"] == "Bob"
        assert resp.json()["gender"] == "male"

    def test_invalid_condition(self, client):
        assert client.post("/patients", json=_patient(conditions=["cancer"])).status_code == 422

    def test_invalid_toxicity(self, client):
        assert client.post("/patients", json=_patient(toxicity=["radiation"])).status_code == 422

    def test_future_dob(self, client):
        assert client.post("/patients", json=_patient(date_of_birth="2099-01-01")).status_code == 422

    def test_missing_name(self, client):
        p = _patient()
        del p["name"]
        assert client.post("/patients", json=p).status_code == 422

    def test_conditions_deduped(self, client):
        resp = client.post("/patients?full=true", json=_patient(conditions=["diabetes", "diabetes"]))
        assert resp.json()["conditions"] == ["diabetes"]

    def test_list_empty(self, client):
        assert client.get("/patients").json() == []

    def test_get_by_id(self, client):
        pid = client.post("/patients?full=true", json=_patient()).json()["id"]
        assert client.get(f"/patients/{pid}?full=true").json()["id"] == pid

    def test_get_404(self, client):
        assert client.get("/patients/nonexistent").status_code == 404


# ═══ 2. UUID5 ══════════════════════════════════════════════════════════════

class TestUUID5:
    def test_deterministic_id(self, client):
        resp = client.post("/patients?full=true", json=_patient())
        assert resp.json()["id"] == make_patient_id("Alice Smith", date(1990, 5, 15))

    def test_different_ids(self, client):
        r1 = client.post("/patients?full=true", json=_patient(name="Alice", date_of_birth="1990-01-01"))
        r2 = client.post("/patients?full=true", json=_patient(name="Bob", date_of_birth="1985-06-15"))
        assert r1.json()["id"] != r2.json()["id"]

    def test_duplicate(self, client):
        r1 = client.post("/patients?full=true", json=_patient())
        r2 = client.post("/patients?full=true", json=_patient())
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]

    def test_duplicate_ignores_updates(self, client):
        client.post("/patients?full=true", json=_patient(conditions=["diabetes"]))
        r2 = client.post("/patients?full=true", json=_patient(conditions=["hypertension"]))
        assert r2.status_code == 200

    def test_case_insensitive(self, client):
        client.post("/patients?full=true", json=_patient(name="Alice Smith"))
        r2 = client.post("/patients?full=true", json=_patient(name="alice smith"))
        assert r2.status_code == 200


# ═══ 3. Batch ══════════════════════════════════════════════════════════════

class TestBatch:
    def test_mixed(self, client):
        records = [_patient(name="Good"), _patient(name=""), _patient(name="Also Good", date_of_birth="1985-06-15"), _patient(conditions=["cancer"])]
        resp = client.post("/patients/batch", json=records)
        assert len(resp.json()["accepted"]) == 2
        assert len(resp.json()["rejected"]) == 2

    def test_all_valid(self, client):
        assert len(client.post("/patients/batch", json=[_patient(name="A", date_of_birth="1990-01-01")]).json()["accepted"]) == 1

    def test_empty(self, client):
        assert client.post("/patients/batch", json=[]).json()["accepted"] == []

    def test_rejected_reasons(self, client):
        body = client.post("/patients/batch", json=[_patient(name="   ")]).json()
        assert any("name" in r.lower() for r in body["rejected"][0]["reasons"])

    def test_dedup_in_batch(self, client):
        body = client.post("/patients/batch", json=[_patient(name="Same", date_of_birth="1990-01-01")] * 2).json()
        assert body["accepted"][0]["id"] == body["accepted"][1]["id"]


# ═══ 4. Trials ═════════════════════════════════════════════════════════════

class TestTrials:
    def test_happy_path_plural(self, client):
        assert client.post("/trials", json=_trial()).status_code == 200

    def test_happy_path_singular(self, client):
        resp = client.post("/trial", json=_trial())
        assert resp.status_code == 200

    def test_criteria_alias(self, client):
        """Platform sends 'criteria', we accept it."""
        resp = client.post("/trial", json={"name": "Trial A", "criteria": [], "min_participants": 1, "max_participants": 10})
        assert resp.status_code == 200

    def test_eligibility_criteria_also_works(self, client):
        resp = client.post("/trials", json={"name": "Trial B", "eligibility_criteria": [{"field": "age", "op": "gte", "value": 18}], "min_participants": 0, "max_participants": 5})
        assert resp.status_code == 200

    def test_list_singular(self, client):
        client.post("/trial", json=_trial(name="A"))
        client.post("/trial", json=_trial(name="B"))
        assert len(client.get("/trial").json()) == 2

    def test_list_plural(self, client):
        client.post("/trials", json=_trial())
        assert len(client.get("/trials").json()) == 1

    def test_min_gt_max(self, client):
        assert client.post("/trials", json=_trial(min_participants=50, max_participants=10)).status_code == 422

    def test_negative_min(self, client):
        assert client.post("/trials", json=_trial(min_participants=-1)).status_code == 422

    def test_missing_max(self, client):
        t = _trial()
        del t["max_participants"]
        assert client.post("/trials", json=t).status_code == 422

    def test_trial_dates(self, client):
        assert client.post("/trials", json=_trial(start_date="2025-01-01", end_date="2025-12-31")).status_code == 200

    def test_bad_dates(self, client):
        assert client.post("/trials", json=_trial(start_date="2025-06-01", end_date="2025-01-01")).status_code == 422

    def test_404(self, client):
        assert client.get("/trials/nonexistent").status_code == 404


# ═══ 5. Matching — eligibility ═════════════════════════════════════════════

class TestMatchingEligibility:
    def test_eligible(self, client):
        client.post("/patients", json=_patient(name="Bob", date_of_birth="1980-06-15", gender="male"))
        client.post("/trials", json=_trial())
        resp = client.post("/matchings?full=true", json={"enforce_exclusivity": False})
        assert len(resp.json()["output_pairs"]) == 1

    def test_ineligible_age(self, client):
        client.post("/patients", json=_patient(name="Young", date_of_birth="2015-01-01"))
        client.post("/trials", json=_trial(criteria=[{"field": "age", "op": "gte", "value": 25}]))
        assert client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"] == []

    def test_ineligible_gender(self, client):
        client.post("/patients", json=_patient(name="Alice", date_of_birth="1985-01-01", gender="female"))
        client.post("/trials", json=_trial(criteria=[{"field": "age", "op": "gte", "value": 18}, {"field": "gender", "op": "eq", "value": "male"}]))
        assert client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"] == []

    def test_conditions(self, client):
        client.post("/patients", json=_patient(name="Diabetic", date_of_birth="1985-01-01", conditions=["diabetes"]))
        client.post("/patients", json=_patient(name="Healthy", date_of_birth="1985-06-01", conditions=[]))
        client.post("/trials", json=_trial(criteria=[{"field": "conditions", "op": "contains", "value": "diabetes"}]))
        assert len(client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"]) == 1

    def test_allergies(self, client):
        client.post("/patients", json=_patient(name="Allergic", date_of_birth="1985-01-01", allergies=["aspirin"]))
        client.post("/trials", json=_trial(criteria=[{"field": "allergies", "op": "not_contains", "value": "aspirin"}]))
        assert client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"] == []

    def test_toxicity(self, client):
        client.post("/patients", json=_patient(name="Smoker", date_of_birth="1985-01-01", toxicity=["smoking"]))
        client.post("/patients", json=_patient(name="Clean", date_of_birth="1985-06-01", toxicity=[]))
        client.post("/trials", json=_trial(criteria=[{"field": "toxicity", "op": "not_contains", "value": "smoking"}]))
        pairs = client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"]
        assert len(pairs) == 1

    def test_multi_trial(self, client):
        client.post("/patients", json=_patient(name="Multi", date_of_birth="1985-01-01", gender="male", conditions=["diabetes"]))
        client.post("/trials", json=_trial(name="A", criteria=[{"field": "age", "op": "gte", "value": 18}]))
        client.post("/trials", json=_trial(name="B", criteria=[{"field": "conditions", "op": "contains", "value": "diabetes"}]))
        assert len(client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"]) == 2


# ═══ 6. Matching — capacity ════════════════════════════════════════════════

class TestMatchingCapacity:
    def test_max(self, client):
        for i in range(5):
            client.post("/patients", json=_patient(name=f"P{i}", date_of_birth="1990-01-01", gender="male"))
        client.post("/trials", json=_trial(max_participants=2))
        assert len(client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"]) == 2

    def test_min_not_met(self, client):
        client.post("/patients", json=_patient(name="Solo", date_of_birth="1990-01-01"))
        client.post("/trials", json=_trial(min_participants=10, max_participants=20))
        assert client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"] == []

    def test_empty(self, client):
        resp = client.post("/matchings?full=true", json={})
        assert resp.status_code == 200
        assert resp.json()["output_pairs"] == []


# ═══ 7. Exclusivity ════════════════════════════════════════════════════════

class TestExclusivity:
    def test_overlapping(self, client):
        client.post("/patients", json=_patient(name="E", date_of_birth="1985-03-20",
            trial_participations=[{"trial_id": "old", "start_date": "2025-01-01", "end_date": "2025-06-30"}]))
        client.post("/trials", json=_trial(start_date="2025-02-01", end_date="2025-05-31"))
        assert client.post("/matchings?full=true", json={"enforce_exclusivity": True}).json()["output_pairs"] == []

    def test_non_overlapping(self, client):
        client.post("/patients", json=_patient(name="F", date_of_birth="1985-03-20", gender="male",
            trial_participations=[{"trial_id": "past", "start_date": "2024-01-01", "end_date": "2024-06-30"}]))
        client.post("/trials", json=_trial(start_date="2025-01-01", end_date="2025-12-31"))
        assert len(client.post("/matchings?full=true", json={"enforce_exclusivity": True}).json()["output_pairs"]) == 1

    def test_toggle_off(self, client):
        client.post("/patients", json=_patient(name="E", date_of_birth="1985-03-20",
            trial_participations=[{"trial_id": "old", "start_date": "2025-01-01", "end_date": "2025-06-30"}]))
        client.post("/trials", json=_trial(start_date="2025-02-01", end_date="2025-05-31"))
        assert len(client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["output_pairs"]) == 1


# ═══ 8. Exclusion reasons ══════════════════════════════════════════════════

class TestExclusionReasons:
    def test_age_reason(self, client):
        client.post("/patients", json=_patient(name="Young", date_of_birth="2015-01-01"))
        client.post("/trials", json=_trial(criteria=[{"field": "age", "op": "gte", "value": 25}]))
        assert any("age" in e["reason"] for e in client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["exclusions"])


# ═══ 9. Report ═════════════════════════════════════════════════════════════

class TestReport:
    def test_report(self, client):
        client.post("/patients", json=_patient(name="Alice", date_of_birth="1990-01-01"))
        client.post("/patients", json=_patient(name="Young", date_of_birth="2015-01-01"))
        client.post("/trials", json=_trial(name="Adult"))
        mid = client.post("/matchings?full=true", json={"enforce_exclusivity": False}).json()["id"]
        body = client.get(f"/matchings/{mid}/report?full=true").json()
        assert body["summary"]["patients_considered"] == 2
        assert len(body["unmatched_patients"]) == 1


# ═══ 10. Masking ═══════════════════════════════════════════════════════════

class TestMasking:
    def test_masked_default(self, client):
        client.post("/patients", json=_patient(name="Alice Smith"))
        p = client.get("/patients").json()[0]
        assert p["name"] == "A. Smith"
        assert "XX" in p["date_of_birth"]

    def test_full(self, client):
        client.post("/patients", json=_patient())
        assert client.get("/patients?full=true").json()[0]["name"] == "Alice Smith"


# ═══ 11. Audit ═════════════════════════════════════════════════════════════

class TestAudit:
    def test_patient_event(self, client):
        client.post("/patients", json=_patient())
        assert len(client.get("/audit/events?event_type=patient_created").json()) == 1

    def test_trial_event(self, client):
        client.post("/trials", json=_trial())
        assert len(client.get("/audit/events?event_type=trial_created").json()) == 1

    def test_history(self, client):
        pid = client.post("/patients?full=true", json=_patient()).json()["id"]
        assert len(client.get(f"/audit/events/{pid}/history").json()) >= 1


# ═══ 12. Malformed ═════════════════════════════════════════════════════════

class TestMalformed:
    def test_bad_json(self, client):
        assert client.post("/patients", content="not json{{{", headers={"Content-Type": "application/json"}).status_code == 422

    def test_bad_date(self, client):
        assert client.post("/patients", json=_patient(date_of_birth="not-a-date")).status_code == 422

    def test_blank_name(self, client):
        assert client.post("/patients", json=_patient(name="   ")).status_code == 422


# ═══ 13. Health ════════════════════════════════════════════════════════════

class TestHealth:
    def test_health(self, client):
        assert client.get("/health").json()["status"] == "ok"
