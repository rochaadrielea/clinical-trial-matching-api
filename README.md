# Clinical Trial Matching API

REST API that takes patient data and clinical trial rules, and returns which patients should go into which trials — with a full explanation of every decision.

```bash
pip install -r requirements.txt
uvicorn solution:app --reload --port 8888
```

Interactive docs at `http://127.0.0.1:8888/docs`

---

## Architecture

```
solution.py   → HTTP routes, entry point
  ├── storage.py    → Repositories, batch processing
  │     └── audit.py      → Append-only event log
  ├── matching.py   → Three-stage pipeline: rules → exclusivity → capacity
  ├── security.py   → PII masking
  └── models.py     → Pydantic v2 data contracts (every file imports this)
```

---

## How it works

1. **Data comes in** — patients and trials are created through the API
2. **Validation catches bad data** — invalid conditions, future dates, missing fields are rejected immediately
3. **Matching runs** — each patient is checked against each trial's eligibility rules
4. **Results explain every decision** — who matched, who didn't, and exactly why
5. **Everything is recorded** — every action gets a timestamped audit event

---

## Endpoints

| # | Method | Endpoint | What it does |
|---|--------|----------|-------------|
| 1 | POST | `/patients` | Create one patient |
| 2 | POST | `/patients/batch` | Create many (good ones saved, bad ones quarantined) |
| 3 | GET | `/patients` | List all patients |
| 4 | GET | `/patients/{id}` | Get one patient |
| 5 | POST | `/trials` | Create a trial with eligibility rules |
| 6 | GET | `/trials` | List all trials |
| 7 | GET | `/trials/{id}` | Get one trial |
| 8 | POST | `/matchings` | Run the matching algorithm |
| 9 | GET | `/matchings` | List past matching runs |
| 10 | GET | `/matchings/{id}` | Get one matching result |
| 11 | GET | `/matchings/{id}/report` | Full audit report with exclusion reasons |
| 12 | GET | `/audit/events` | Query the audit log |
| 13 | GET | `/audit/events/{id}/history` | Timeline of one entity |
| 14 | GET | `/health` | Server alive check |

All patient/trial/matching endpoints also exist in singular form (`/patient`, `/trial`, `/matching`).

---

## Eligibility rules

Rules are data, not code. A trial defines its criteria as a list of rules:

```json
[
  {"field": "age",        "op": "gte",          "value": 25},
  {"field": "gender",     "op": "eq",           "value": "male"},
  {"field": "conditions", "op": "contains",     "value": "diabetes"},
  {"field": "toxicity",   "op": "not_contains", "value": "smoking"}
]
```

Each rule reads as a question: *"Is the patient's age ≥ 25?"*, *"Does the patient have diabetes?"*. New criteria can be added through the API — no code changes needed.

Operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `not_contains`

---

## Why FastAPI + Pydantic v2

The assessment required FastAPI. FastAPI is built on Pydantic — they work as a team.

**FastAPI handles the HTTP layer** — it receives requests, routes them to the right function, and sends back responses.

**Pydantic handles the data layer** — it defines what the data looks like, validates it, and converts it.

When someone sends a request to create a patient, FastAPI receives the raw JSON and hands it to Pydantic's `PatientCreate` model. Pydantic checks every field — is the name blank? Is the date in the future? Is `"cancer"` a valid condition? If anything fails, a 422 error is returned automatically. If everything passes, the validated data moves to storage and matching.

FastAPI only uses Pydantic at the request/response boundary. In this project, Pydantic goes further — it's also used inside the matching engine, the audit log, and storage. The `EligibilityCriterion` model isn't an API endpoint — it's an internal data structure the matching pipeline evaluates. The `AuditEvent` model isn't a request body — it's a record created internally every time something happens.

**Enums** enforce closed sets of allowed values. `Condition` only permits `"diabetes"` and `"hypertension"`. Anything else is rejected automatically — no manual checking needed.

FastAPI is the door. Pydantic is the language spoken inside the building.

---

## Design decisions

| Chose | Instead of | Because |
|-------|-----------|---------|
| Rules as data | Hardcoded if/else | A researcher can add new criteria through the API without deploying code |
| Partial batch processing | Reject entire batch | In real clinical pipelines, 1 bad record shouldn't kill 99 good ones |
| Exclusion reasons captured | Silent filtering | Regulators need to know *why* a patient wasn't matched |
| Repository pattern | Direct dict access | Storage can be swapped from in-memory to a database with zero upstream changes |
| Append-only audit log | No logging | Healthcare requires traceability — every action timestamped, nothing deleted |
| PII masking (opt-in) | Full data by default | Patient names and dates are sensitive — masking shows awareness of healthcare data privacy |

---

## Storage

Data is stored in-memory (Python dictionaries). When the server stops, all data is gone. This is intentional for the assessment — the repository pattern means swapping in a real database later only requires replacing the storage classes. Nothing else changes.

---

## Tests

```bash
pytest tests.py -v
```

65 tests across 12 areas: patient CRUD, validation, batch/quarantine, trial CRUD, eligibility rules, capacity, exclusivity, exclusion reasons, matching reports, PII masking, audit log, and malformed input handling.
