# Final integration handoff

The complete Monitoring → Diagnostic → Recovery → Verification workflow is now
implemented. See README.md for setup, API/UI, retry semantics, scenarios, and tests;
see AUDIT.md for baseline findings and measured validation.

## Contracts to preserve

- Node names remain monitor, diagnose, recover, verify, and finalize. The retry
  utility increments one counter and returns to diagnose with current verification evidence.
- Return partial state updates. Only new errors/history entries are appended;
  tool-call counts add, while observation snapshots replace older values.
- Recovery is allowlisted, targeted, and bound to the same settings/fault store as
  monitoring and verification. It never declares incident resolution.
- Resolution requires five independent passing checks, including login/profile.
- max_retries=2 means initial cycle + two retries. Recovery and evidence budgets
  are separate; no-action paths are bounded too.
- Default mock CLI remains observation-only. Full deterministic demos are explicitly
  labeled; actual Gemini runs use gemini-3.5-flash-lite and require credentials.
- MemorySaver and API run history are in-process; use one backend worker on loopback.
- Existing environment services/DB/fault code remains intact.

## Quick commands

```powershell
python -m uvicorn incidentops.api:app --host 127.0.0.1 --port 8000
python -m incidentops.main --demo multiple_faults
python -m pytest -q
python -m evaluation.evaluate --output evaluation/results.json
```

Open http://127.0.0.1:8000 for the UI. No key or separate services are required for
the isolated demo. Live mode setup and its limitations are documented in README.md.
