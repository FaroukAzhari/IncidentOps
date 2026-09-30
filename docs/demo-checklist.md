# Live Gemini authentication demo checklist

Use this checklist to rehearse the live authentication scenario. It records
expected results, not a claim that a particular run passed. For installation and
service startup commands, see the [README](../README.md#live-gemini-mode-and-local-services).

## Prepare the baseline

- [ ] Confirm IncidentOps (8000), the application (8001), and authentication (8002)
  are running. Existing background processes are sufficient.
- [ ] Open http://127.0.0.1:8000 and select **Local services | Gemini**.
- [ ] Confirm the Gemini key is configured locally; keep `.env` out of the recording.
  Key presence alone does not confirm model access or quota.
- [ ] Under **Controlled fault lab**, click **Clear faults**, then **Try sign in**.
  The portal should load the demo user's profile before introducing a failure.
- [ ] Leave **Thread ID** blank and **Maximum retries** at 2. For a short recording,
  uncheck **Presentation walkthrough after execution** to skip recorded playback.

## Run the incident

1. Select **Authentication unavailable** in the fault dropdown and click
   **Trigger fault**. Confirm the portal shows failed authentication.
2. Enter `Users cannot log in` in **Incident report** and click **Run investigation**.
   The report describes the symptom; the fault was created by the previous step.
3. Inspect Monitoring's current auth/profile evidence and Gemini's diagnosis.
   Do not infer success from the report text or from a repair message alone.
4. Inspect Recovery's action and the fresh Verification checks: API health,
   auth health, database health, login, and profile.
5. Confirm the final result is **Resolved**, with `incident_resolved` and
   `verification_passed` both true. The portal should work again.

## Capture state evidence

- [ ] Expand **Execution timeline & state details**.
- [ ] Open the Diagnostic entry and show **Partial state update**, including the
  diagnosed cause and recommended action.
- [ ] Open the Recovery entry and show its action, result, and attempt count.
- [ ] Open the Verification entry and show its check results and verdict.

A successful single-auth run may not retry. To demonstrate a conditional path
change, use the [multiple-fault walkthrough](demo-story.md#multiple-faults-and-conditional-recovery)
in **Isolated demo** and show failed verification, the retry, and the next cycle.
Label that scenario as deterministic diagnosis; it does not call Gemini.

## If the expected result does not appear

- Service `ConnectError`: check the configured app/auth URLs and running processes.
- Profile timeout: check the local service configuration and inspect the actual
  profile response before repeating an investigation.
- Diagnosis failure: inspect the recorded error and check key, model access,
  quota, and connectivity. Do not describe an unresolved run as a successful repair.
- Before another rehearsal, wait for the current run to finish, then click
  **Clear faults** and confirm a healthy portal again.
