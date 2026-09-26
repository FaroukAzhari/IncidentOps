# Browser validation

The local Uvicorn backend was started on loopback and exercised through real HTTP
and headless Microsoft Edge. All seven scenarios completed with their expected
outcomes. Checks covered five visible verification results, exact retry counts,
the execution timeline, read-only incident retrieval, live-mode controls, a
390-pixel mobile viewport without horizontal overflow, and absence of JavaScript
page errors. The temporary backend process was stopped after validation.

- [Desktop: successful recovery after one retry](ui-desktop.png)
- [Mobile: bounded unresolved incident](ui-mobile.png)

Screenshots use the explicitly labeled deterministic demo, not a live Gemini run.
