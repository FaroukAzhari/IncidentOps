# Student 3 handoff to Student 4

## Completed scope

Student 2 owns the local test environment and fault injection. Student 3 owns
Diagnostic and Recovery Agents. Student 1's Monitoring Agent and the shared
state/checkpoint contracts are preserved. Student 3 adds bounded
diagnosis-to-monitoring routing to the shared graph.

- Main API on port 8001: GET /health, GET /profile, GET /logs, GET /metrics.
- Auth service on port 8002: GET /health and POST /validate.
- SQLite users table: id, username, role; seeded demo/student user.
- Shared, persistent database_down/auth_down/api_degraded/wrong_db_config flags.
- Four injection functions, reset_all_faults, and a command-line controller.
- Local HTTP/SQLite monitoring with --local; mock mode remains the default.
- Bounded calls, sanitized collection errors, recent logs and measured metrics.
- 88 automated tests, including existing Student 1/2 coverage and diagnosis/recovery regressions.

## Setup

Use Python 3.12 because the existing Monitoring Agent uses Python 3.12 syntax.
From a fresh checkout in PowerShell:

```powershell
git pull --ff-only origin main
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m environment.database
python -m pytest -q
python -m pip check
```

Set `GEMINI_API_KEY` locally for diagnosis and use `LLM_MODEL=gemini-3.5-flash-lite`.
No key is needed for the offline demo or automated tests. Without a key, local
diagnosis records an error and recovery is skipped.
Validation uses Python 3.12, the real local-service/recovery paths, and stubbed
Gemini responses. Live Gemini requests still require a valid key and model access.
Never commit .env, virtual environments, or database files.

Run each service in its own activated terminal:

```powershell
python -m uvicorn environment.auth_service.main:app --host 127.0.0.1 --port 8002
python -m uvicorn environment.app_service.main:app --host 127.0.0.1 --port 8001
```

In a third activated terminal:

```powershell
python -m environment.fault_controller reset
Invoke-RestMethod -Uri http://localhost:8001/profile -Headers @{ Authorization = 'Bearer demo-token' }
python -m incidentops.main --local
python -m environment.fault_controller inject auth_down
python -m incidentops.main --local
python -m environment.fault_controller reset
```

Restart services after editing code. If pytest's shared temporary directory has
Windows permission errors, pass --basetemp with a fresh directory beneath the
ignored .pytest_cache directory.

## Fault and evidence semantics

| Fault | API health | Auth health | DB health | Profile |
| --- | --- | --- | --- | --- |
| None | true | true | true | 200 |
| auth_down | true | false | true | 503 |
| database_down | true | true | false | 500 |
| api_degraded | false | true | true | 503 |
| wrong_db_config | true | true | true | 500 |

Faults are application-layer simulations. No process is killed or database damaged.
Wrong configuration is simulated at the application boundary, so the independent
SQLite probe remains healthy. Fault state persists separately in data/faults.db.

Exercise /profile to generate dependency-specific logs before monitoring.
Monitoring does not itself call /profile. /logs retains the last 100 application
entries; /metrics measures health/profile requests. Both reset on service restart.
Old logged failures are not proof that a fault is still active. The fixed demo
token is a test credential, not production authentication.

Connection failures or invalid responses mean unknown: the health key is omitted
and an error is recorded. A valid unhealthy 503 response produces healthy=false.
Fault-storage failures are collection errors, not confirmed outages.

## Student 3 implementation

Diagnostic and Recovery Agents use
`ChatGoogleGenerativeAI.with_structured_output(Diagnosis)`, allowlisted recovery
actions, attempt accounting, and bounded evidence routing. State mappings are in
README. Diagnosis clears stale recommendations on failure. Recovery requires a
current diagnosis with sufficient evidence and `local_services` provenance.

Additional monitoring passes are bounded by `max_evidence_attempts` (default 2),
independently of `max_recovery_attempts`. Unsupported or inconsistent evidence
requests fail validation. The default mock graph stays offline and performs no
recovery writes, even when credentials are configured.

Fault injection functions are in environment.fault_controller. Recovery may use
environment.fault_state.set_fault(name, False) to clear a specific flag. Avoid
resetting unrelated faults as a substitute for targeted recovery.

Preserve tool interfaces, node names, state meanings, and partial updates. Return
only new errors/history entries. Health/logs/metrics replace the latest snapshot.
Never let Monitoring diagnose or resolve incidents. Bound evidence loops separately
from recovery attempts. Keep mock tools and offline tests.

Student 4 owns verification, final retry routing, UI, and evaluation. The current
finalizer always returns incident_resolved=False. Provisional statuses are
monitoring_only, diagnosis_failed, evidence_exhausted, recovery_skipped, and
awaiting_verification. Student 4 must add independent health/profile checks,
verification-based retries, and verified terminal outcomes. Recovery success
alone does not prove resolution. There is no IncidentOps UI on port 8000 yet.

## Sequential Git workflow

One student works and pushes at a time. Run tests, dependency checks, and the CLI
before handing off. Pull main before the next student starts.
Repository: https://github.com/FaroukAzhari/IncidentOps.git.
