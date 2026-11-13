# ForgeApply implementation audit and verification

Audit date: 2026-11-13. Baseline: commit `84c1f1d`, Windows, repository `.venv`, Python 3.13.7. Existing user handoff/context files were untracked and were preserved. Personal application storage was backed up outside Git before updating the running installation.

## Baseline and repairs

Baseline `python -m pytest -q`: **12 passed**, one FastAPI/Starlette TestClient deprecation warning. The browser test only filled an email on an in-memory page; it did not exercise the application executor, CV upload or multi-page preparation.

Evidence-based gaps repaired in this change:

- Field snapshots and edits used independently filtered numeric lists. Snapshots now assign stable DOM tokens, record frame identity, check field semantics immediately before fill, and accept a snapshot ID to reject stale dashboard actions.
- Required radios/checkboxes were interpreted via their nonempty default value. Snapshots now include checked/validity state and validation messages. Native selects, accessible custom comboboxes, contenteditable fields, dates and same-origin iframe fields have Chromium coverage.
- Hidden file inputs were missed by preparation; upload always selected the first input. Hidden CV inputs are included, multiple inputs require a unique resume label, and filename/size attachment readback is verified. Uploads require per-job preparation consent. Hashed filenames preserve previous documents.
- Partial button text could reach final submission through general clicks. General clicks now allow known navigation/dropdown controls only; ambiguous navigation targets are rejected, Enter is excluded from generic key actions, and a stalled Next is not repeated.
- Preparation reopened the application after missing-answer handoff and lost progress. In-session resume retains the current page. A SQLite journal records observations, plans, actions, verification and stops. Steps, elapsed time and model calls are bounded; pause is cooperative. Initial GET navigation has one retry; mutations are not automatically replayed.
- Preparation could call a final review page with no inputs unsupported. Recognized final review now stops with a job/URL/page fingerprint. Final approval checks that context again, rejects previously confirmed submissions, and persists a lock before attempting a submission. Ambiguous attempts remain locked after restart. Controlled receipts include confirmation text, metadata, actual attached CV hash/language and the journal.
- Newly generated AI answers were treated as facts. Form decisions now use strict schemas, permitted field IDs and human-review proposals. Sensitive declarations are excluded from automatic answers, including saved wildcard matches. Deterministic execution remains the default.
- Remote inference did not have a separate consent gate; local compatible servers unnecessarily required a hosted API key. Remote inference now needs explicit consent and HTTPS. Environment API keys are not forwarded to loopback endpoints. Provider inventory diagnostics, latency/usage readback and an optional local OCR adapter are integrated.
- The request guard accepted every localhost port and did not validate Host. Mutations now require the same origin when Origin is present, reject cross-site Fetch Metadata, and validate local Host names. API caching and framing are disabled. New application origins require explicit review before automatic data entry/upload.
- New installations shipped a candidate location/title as defaults. New profiles are blank. Structured candidate context, timestamped profile/answer provenance and additive answer-schema migrations retain existing records.
- URL normalization forced HTTP fixture URLs to HTTPS. It now preserves the requested scheme, rejects embedded credentials and retains tracking-parameter deduplication.

## Verified capabilities

| Capability | Evidence/status |
|---|---|
| FastAPI and compact blue dashboard | Actual locally served dashboard exercised in Chromium; profile save, context view and safe settings defaults verified |
| Persistent visible Chromium | Separate manual local smoke with the running app, actual local profile and authorized local CV; no employer submission |
| Multi-page preparation | Served fixtures: fill, hidden CV upload, Next, missing-answer handoff, manual synthetic answers, resume, final review |
| Native/custom dropdowns, date, rich text, conditional fields and iframe | Real Chromium against `examples/fixtures/controls.html`; same-origin iframe autofill and accessibility tree |
| Validation/failure/recovery | Required controls, changing DOM, stale UI, stalled Next, ambiguous/rejected upload, login/CAPTCHA handoff, browser restart and unexpected redirect gates |
| Submission protections and receipts | Synthetic fixture only: unapproved and wrong-job/page actions blocked; success/failure proof; confirmed/ambiguous attempts not replayed after restart |
| Candidate persistence/migrations | Isolated SQLite tests for profile/context/unknown values, regex scope, legacy answer migration and preserved statuses |
| Ollama and OpenAI-compatible inference | Mock HTTP/schema/outage tests; no live successful model inference on this machine |
| OCR | Local Tesseract command adapter and missing-installation tests; no installed Tesseract/live recognition verified |
| Greenhouse/Lever/Ashby discovery | Existing mocked public-feed tests; no employer application adapter or live submission verified |

Windows Python 3.13.7 verification: **42 passed, 0 failed, 0 skipped**; one existing Starlette TestClient/httpx deprecation warning. `node --check static/app.js`, `git diff --check` and `python -m pip check` passed. The automated suite contains unit, API, actual-HTTP dashboard and served Chromium integration tests. A separate visible-browser smoke reached final review with the owner-authorized local profile/CV and recorded zero fixture submissions; the real dashboard displayed saved data with zero JavaScript errors. Local verification screenshots/results stay outside the repository under the application data directory. Live provider diagnostics returned an actionable unavailable error; no live model capability is claimed.

## Architecture and remaining release blockers

The existing FastAPI + SQLite + persistent Playwright-thread architecture is retained. `browser_tools.py` defines strict action/target schemas; `browser.py` owns the bounded deterministic orchestrator and shared browser operations; `candidate.py` derives narrow answers from supplied facts; `llm.py` validates provider proposals; `ocr.py` runs optional local OCR. The existing dashboard exposes document/destination consent, pause, journal, accessibility, OCR and provider checks.

This is a supervised local development build, **not a complete initial public release**:

1. Employer-specific application adapters and their permitted live-site behavior remain unverified. A button name alone cannot establish that an arbitrary site treats an action as navigation; unsupported flows need manual operation. There is no universal browser agent.
2. The persistent journal/submission locks do not constitute a scheduling queue, robust crash-restored SPA state, parallel multi-user sessions, or an encrypted credential vault. Inspection/navigation can recover a closed browser; mutations are never replayed automatically.
3. Loopback origin/Host checks do not authenticate other programs/users on the same machine. SQLite, screenshots, CVs and Chromium profile data rely on local OS access controls. No screenshot-redaction/retention policy or encrypted multi-user isolation is implemented.
4. PDF signature/DOCX container checks do not parse every document or prove truthful contents. Full document ingestion, bilingual document generation, granular fact expiration and a structured-profile editor remain incomplete. Manual submission acknowledgment records a user note; it does not independently reconstruct a manually chosen CV or produce browser proof.
5. Live Ollama, hosted text/vision, real local OCR and provider capability variations need verification. The model is advisory; there is no unconstrained LLM tool execution. No RAG or multi-agent framework was added.
6. Discovery scoring is heuristic. Strict 24-hour/seven-day freshness, active-vacancy verification, remote-from-Italy eligibility and complete qualification matching are not yet enforced by a discovery/application policy engine. Review opportunities manually; do not interpret score as eligibility.
7. Tab selection is an API tool; arbitrary popups/download workflows, cross-origin iframe autofill and all custom control variants are not proven. Tool/schema limits intentionally stop ambiguous operations.
8. Signed installers, first-run wizard, standalone packaging, clean-machine install validation, an explicit license choice and external operator testing remain outstanding. CI results must be assessed separately from local Windows tests.

The next highest-value blocker is a permitted ATS adapter with an explicit capability manifest, complete validation/approval evidence, and restart-safe application attempts, followed by conservative vacancy eligibility gating.

## Reproduce locally

```powershell
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m pytest -q
node --check static\app.js
git diff --check
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m forgeapply
```

Dashboard: `http://127.0.0.1:8765`. API schemas: `/api/docs`.

In another terminal: `.venv\Scripts\python.exe -m examples.fixture_server --port 8766`. Use `/apply` for a multi-page local application or `/controls` for dynamic controls and an iframe. Keep final submission manual unless explicitly testing the synthetic fixture. Stop the fixture server with Ctrl+C.
