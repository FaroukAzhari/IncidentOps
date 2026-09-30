# Presenting the IncidentOps story

For a live model run, use the [Gemini authentication demo checklist](demo-checklist.md).
The walkthroughs below use isolated demo scenarios.

## Launch

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn incidentops.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and refresh with Ctrl+F5 if an older interface is cached.
If this server is already running, do not start a second server on the same port.
The isolated demo needs no Gemini key or separately launched services. Gemini
mode retains the existing README service/key prerequisites and configured model.

## Authentication failure

1. Select **Isolated demo** and **Authentication unavailable**.
2. Point to the Employee Portal's failed sign-in. Its **Scenario preview** label
   makes clear that this is an illustration, not a real login session.
3. Enter “Users cannot log into the application.” Keep the presentation
   walkthrough enabled, then click **Run investigation**.
4. Explain the four summaries: observed auth failure, structured diagnosis from
   deterministic demo rules, the allowlisted application-layer repair, and five
   independent verification checks. Do not describe the repair as an OS restart.
5. The recorded walkthrough is labeled and uses real returned snapshots. Only
   the actual final verified result switches the portal to the welcome/profile view.
6. Show the before/after auth change and expand the execution timeline if needed.

## Multiple faults and conditional recovery

1. Select **Authentication and database unavailable**.
2. Enter “Login and database-backed profile requests are failing.” Run the demo.
3. Follow the first recorded diagnosis and targeted action. The exact order comes
   from the backend snapshots, not from the UI.
4. At failed verification, show the remaining problem, still-failed portal, and
   explicit **Retry 1 / Cycle 2** display. A successful action alone is insufficient.
5. Follow fresh diagnosis, the next targeted action, and passing verification.
6. Only now show the restored portal and final resolved banner. Replay is read-only.

For a contrasting failure ending, select **Authentication fault with deliberately
blocked recovery**. Verification keeps failing; the attempt/retry limits end the
run unresolved. The portal must stay failed.

## Presentation behavior

- The existing live stream remains in use. No new backend transport was added.
- Automatic recorded playback is optional and defaults on unless reduced-motion
  preferences are set. Each snapshot takes 800 ms; **Show final result** skips it.
- Playback does not generate tool calls, call Gemini, mutate checkpoints, or rerun
  recovery. Execution timings remain the actual timings returned by the backend.
- The portal is always a clearly labeled visualization. In live Gemini mode,
  writing a report does not inject faults, and previews never invent current health.
- Scenario/mode changes clear the old presentation. Incident reports remain editable.
- Missing confidence remains “Not available”; unknown health stays unknown.
  Before-run login is “Not tested,” because Monitoring has no standalone login tool.
- The final check table can show passed health with an unresolved overall result;
  it never forces all cells red or green based on the outcome banner.
- Timeline details retain state snapshots and execution history. Retrieval loads a
  stored completed incident without creating a new run. Server restart loses history.

## Validation for this change

- 141 pytest tests passed; pip dependency validation passed.
- All seven scenarios exercised through the API, with completed-incident retrieval.
- Added frontend presentation-rule tests using the actual seven scenario traces:
  no premature restoration, failed partial repair, unknown checks, exact tool counts,
  healthy no-action behavior, and persistent failure.
- HTML element references, unique IDs, served script assets, encoding safety, and
  JavaScript syntax checked. DOM contract tests exercise startup, fragmented
  streamed responses, all seven outcomes, replay without requests, incident
  retrieval, and switching to live mode. These use a small DOM test double, not a
  real browser or layout engine. Frontend tests use an already-installed Node
  executable with built-in assertions only; the app has no Node runtime dependency.
- No existing Python/backend/test source changed during this UI task. Model,
  responsibilities, routing, recovery, retries, and evaluation semantics are preserved.
- Manual browser/layout/console validation could not run: the computer-use tools
  expose no connected browser, and attempting to open Chrome returned unavailable.
  API and presentation-rule tests do not replace a visual browser check.

Suggested final browser check on a laptop: run all seven scenarios, inspect
auth_down/multiple_faults playback, skip/replay, switch to Gemini (unknown preview),
retrieve a completed thread, expand snapshots, and check narrow-screen layout and
the browser console. Do not treat historical browser screenshots as validation of
this new layout.
