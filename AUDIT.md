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
| Native/custom dropdowns, multi-select, date, rich text, conditional fields and iframe | Real Chromium against `examples/fixtures/controls.html`; normalized label fallback, delayed-element waits, same-origin iframe autofill and accessibility tree |
| Validation/failure/recovery | Required controls, changing DOM, stale UI, stalled Next, ambiguous/rejected upload, login/CAPTCHA handoff, browser restart and unexpected redirect gates |
| Submission protections and receipts | Synthetic fixture only: unapproved and wrong-job/page actions blocked; success/failure proof; confirmed/ambiguous attempts not replayed after restart |
| Candidate persistence/migrations | Isolated SQLite tests for profile/context/unknown values, regex scope, legacy answer migration and preserved statuses |
| Ollama and OpenAI-compatible inference | Real local Qwen3.5 4B/9B synthetic text/vision evaluation; hosted-compatible transports remain mock-tested |
| OCR | Local Tesseract command adapter and missing-installation tests; no installed Tesseract/live recognition verified |
| Greenhouse/Lever/Ashby discovery | Existing mocked public-feed tests; no employer application adapter or live submission verified |

Windows Python 3.13.7 verification: **43 passed, 0 failed, 0 skipped**; one existing Starlette TestClient/httpx deprecation warning. `node --check static/app.js`, `git diff --check` and `python -m pip check` passed. The automated suite contains unit, API, actual-HTTP dashboard and served Chromium integration tests. A separate visible-browser smoke reached final review with the owner-authorized local profile/CV and recorded zero fixture submissions; the real dashboard displayed saved data with zero JavaScript errors. An isolated server-termination smoke also reopened its persistent browser profile successfully. Local verification screenshots/results stay outside the repository under the application data directory. Live provider diagnostics returned an actionable unavailable error; no live model capability is claimed.

## Architecture and remaining release blockers

The existing FastAPI + SQLite + persistent Playwright-thread architecture is retained. `browser_tools.py` defines strict action/target schemas; `browser.py` owns the bounded deterministic orchestrator and shared browser operations; `candidate.py` derives narrow answers from supplied facts; `llm.py` validates provider proposals; `ocr.py` runs optional local OCR. The existing dashboard exposes document/destination consent, pause, journal, accessibility, OCR and provider checks.

This is a supervised local development build, **not a complete initial public release**:

1. Employer-specific application adapters and their permitted live-site behavior remain unverified. A button name alone cannot establish that an arbitrary site treats an action as navigation; unsupported flows need manual operation. There is no universal browser agent.
2. The persistent journal/submission locks do not constitute a scheduling queue, robust crash-restored SPA state, parallel multi-user sessions, or an encrypted credential vault. Inspection/navigation can recover a closed browser; mutations are never replayed automatically.
3. Loopback origin/Host checks do not authenticate other programs/users on the same machine. SQLite, screenshots, CVs and Chromium profile data rely on local OS access controls. No screenshot-redaction/retention policy or encrypted multi-user isolation is implemented.
4. PDF signature/DOCX container checks do not parse every document or prove truthful contents. Full document ingestion, bilingual document generation, granular fact expiration and a structured-profile editor remain incomplete. Manual submission acknowledgment records a user note; it does not independently reconstruct a manually chosen CV or produce browser proof.
5. Hosted text/vision, real Tesseract OCR, model thinking modes, long contexts and additional provider variants need verification. Real local Qwen3.5 4B/9B tests found repeated unsupported material answers in both models. The model remains advisory; there is no unconstrained LLM tool execution. No RAG or multi-agent framework was added.
6. Discovery scoring is heuristic. Strict 24-hour/seven-day freshness, active-vacancy verification, remote-from-Italy eligibility and complete qualification matching are not yet enforced by a discovery/application policy engine. Review opportunities manually; do not interpret score as eligibility.
7. Tab selection is an API tool; arbitrary popups/download workflows, cross-origin iframe autofill and all custom control variants are not proven. Tool/schema limits intentionally stop ambiguous operations.
8. Signed installers, first-run wizard, standalone packaging, clean-machine install validation, an explicit license choice and external operator testing remain outstanding. CI results must be assessed separately from local Windows tests.

The next highest-value blocker is a permitted ATS adapter with an explicit capability manifest, complete validation/approval evidence, and restart-safe application attempts, followed by conservative vacancy eligibility gating.

## Extension and local inference phase

The subsequent implementation adds an installable MV3 extension, a revocable one-time-paired local bridge, current-tab inspection, shared deterministic form mapping, native file chooser handling, multi-page navigation and manual question lookup. Restricted LinkedIn/Indeed native inspection/autofill is now disabled in both the extension and managed executor. Operator-provided URL imports, matching and original-listing links remain traceable in the dashboard. See [extension setup and boundaries](extension/README.md).

The suite now passes **61 tests on Windows Python 3.13**, including a real unpacked MV3 service worker/UI against a real local FastAPI server and served forms, native chooser, same-origin iframe, navigation, token revocation and source-listing links. A separate running-installation smoke used the owner-authorized local profile and CV, stopped at final review with zero submissions, and confirmed the candidate profile/context/answers were unchanged. PDF/DOCX extraction is a local, unverified text preview rather than automatic fact ingestion.

The [reusable benchmark](benchmarks/README.md) ran 300 case-trials over 50 synthetic cases, plus separate production-provider and timing checks. Both installed models were exercised with text and images. No actual CV/candidate information or paid inference was used. The 9B model is the new-install advisory preference; the smaller model remains a fast preset. Both failed the material-fact safety gate, and quality intervals overlap. Private reports, raw outputs and charts stay under the local user data directory. Existing saved model selections are preserved and presets require explicit Save.

These improvements do not complete the scheduling queue, free-running general agent, bilingual document drafting, verified employer ATS adapters, cross-origin extension frames, normal Chrome/Edge operator testing or public release packaging. They do establish a tested extension/managed-browser preparation workflow with an explicit manual final boundary.

## Bilingual extension and Workday-style preparation phase (2026-11-13)

This phase fixes observed Italian required-helper matching and extension/backend/background-worker version mismatches. The compact panel uses one Prepare & Fill action, persistent pairing without session expiry, a visible Keep open control, and review cards instead of raw JSON. The dashboard starts with profile/connection/practice actions and collapses secondary tools. Existing profile/CV/database records are preserved; no credentials or applicant files are included in source changes.

Shared English/Italian mappings now cover contact/address/postal/province fields, verified education/languages, factual checkbox/radio choices and explicit option equivalences. Missing answers require user entry and review, then save locally with provenance. Record-specific answers remain tied to their exact education/employment record, including bilingual date-question keys. Job-specific referral/motivation text is not saved as a global personal fact. Privacy, work authorization, legal and demographic declarations remain manual even with broad saved regex rules.

Recognized Workday-style repeated sections expand within bounded limits and re-inspect before filling. Existing identities bind by employer/title or institution, blank rows allocate unused verified records, ambiguous history stops expansion, and repeat preparation does not duplicate records. Searchable dropdowns, required validation, Save and Continue / Salva e continua and full-document transitions have actual Chromium coverage. A background-tab animation-frame bottleneck was removed; mutations are verified without waiting indefinitely for a foreground rendering frame. Five recent control-structure reports are stored locally for adapter debugging; entered answers/record identities are excluded, and access is dashboard-only.

Application documents now have factual bilingual CV/letter drafts, optional model translation/wording, editable review, local searchable PDF/text export, and deterministic fallback during model failure. Generated downloads never replace configured CVs automatically. Synthetic PDFs were rendered and visually inspected with accented Italian text; extraction preserved their text. A live local Qwen3.5 9B synthetic question and document probe passed schema/evidence validation, with all output still advisory. The owner's unavailable previous model choice was replaced with the installed 9B model after their request to enable model assistance; prior settings remain in local history and remote inference stays disabled. The owner-entered address was saved only in local profile storage, with provenance.

Verification at this phase: full Windows Python 3.13 suite **84 passed**, no failures/skips, one existing Starlette/httpx warning; JavaScript syntax and pip dependency checks passed. The real unpacked MV3 tests include both English and Italian five-stage Workday-style applications, repeated work/education rows, search/custom dropdowns, unknown radio answers, CV chooser, motivation review, answer reuse, required-consent validation and final review with zero fixture submissions. Earlier fixtures, persistent pairing/revocation, same-origin frames, manual-edit protection, PDF download and mobile dashboard checks also pass.

Public Workday usage was checked on Accenture's supplied portal, PwC's Milan portal and ING's Italy portal; sources and exact fixture commands are in [the extension guide](extension/README.md). These are platform examples, not recommended jobs or proof of employer automation permission. Only the supplied screenshots and publicly accessible pages were available: the development browser could not inspect the user's authenticated Accenture steps. Therefore **live Accenture/Workday completion, all tenant variants, nested/virtualized options, every repeated-section layout, account creation and arbitrary multi-page portals remain unverified**. The next highest-value blocker is comparing the locally recorded control structure of an authorized authenticated Workday session against these tested patterns, then adding regressions for actual mismatches. No universal/perfect compatibility or real application submission is claimed.

## Reproduce locally

### Workday catalog and bounded extension agent (2026-11-14, preview 0.4.2)

User regressions exposed gaps not covered by the original native-select record fixtures. The updated fixture now reconstructs Enter-triggered references, portal/virtual menus, split education-year IDs, Overall language controls, committed skills and upload acceptance/rejection. Human-readable field failures replace raw index-only errors. Original grades are not treated as GPA; unknown applicant facts remain unresolved. Public HRM/PwC controls were inspected read-only; anonymous Workday reached Sign In, so authenticated field evidence came from screenshots/local metadata.

The extension now has a bounded observe/plan/act/verify run-to-review loop, local Chrome/backend checkpoints, pause/stop/resume and a visible cursor overlay. Models choose only offered tool IDs; strict Ollama schemas reject malformed or invented choices. Screenshot reasoning is optional, resized, limited to the active authorized tab and still grounded to DOM candidates. No OS cursor, arbitrary scripts, unverified coordinates or automatic final submission is implemented.

The full local suite passes **103 tests** with one existing dependency warning. Real Chromium tests cover EN/IT full runs with manual fact/document/consent checkpoints, panel interruption/reload, ambiguity, replaced controls, server errors and compact final-review labels. Synthetic runs recorded 33 steps / 29 verified actions / zero submissions, with model calls disabled for repeatable end-to-end evidence. Small live 4B/9B text/vision probes separately passed schema-constrained choices. Private reports stay outside Git.

The actual server was backed up and restarted. Hashes of profile, candidate context, saved answers, jobs and existing pairing were unchanged. These checks do not establish universal ATS compatibility or live employer completion. [Detailed evidence](docs/WORKDAY_VERIFICATION.md) records the tested boundaries.

### Follow-up: real control metadata and Italian portal (2026-11-14)

Local control diagnostics revealed Workday input IDs without record wrappers and an Italian enterprise portal with `Via/Piazza`, `Canale`, native dropdowns and a separate `Prefisso`. The shared mapper and extension now cover these shapes, all four repeated background categories, explicit skills tags, selected-prefix reads, and bounded re-observation after dependent changes. Missing choices and optional questions have review cards; sensitive fields and existing personal defaults remain visible for manual review. The confirmed referral source is stored only for its application URL. No owner facts or supplied private implementation guide were added to source.

The dashboard has a structured background editor preserving existing metadata. AI can propose references to exact allowed scalar profile facts, with schema/type checks and review before learning a host-scoped mapping. Such mappings read the current profile value rather than a stale literal. Additive answer metadata migrations preserve older databases. Bilingual CV drafts also include verified certifications.

The final Windows Python 3.13 result is **91 passed**, zero failures/skips, one Starlette/httpx deprecation warning. Actual Chromium tests cover the Italian portal and both Workday-style languages. One regression caught an overly broad phone repair; the final implementation preserves valid existing values and repairs only invalid numbers matching the verified profile. Dependency/syntax/whitespace and changed-source private-data scans pass. The local backend and demo routes return HTTP 200 and existing pairing remains present. No real employer submission was performed.

See [release readiness](RELEASE_READINESS.md) for the exact verified matrix and remaining public-release blockers. Received control metadata improves the fixtures but does not prove authenticated employer completion. Open/closed shadow roots, cross-origin frames, all tenant variants and live hosted-provider behavior are still unverified or unsupported.

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
