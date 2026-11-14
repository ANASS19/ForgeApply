# Enterprise-form regression evidence — 0.4.3

## Recovery regressions added in 0.4.3

The earlier fixture did not reproduce an important partial-completion state: dates had filled but the university reference had not committed. The binder treated that row as unidentified, so known education facts disappeared from subsequent plans. Row bindings now live in the content script's isolated world, with a fingerprint of the verified source. Reinspection retains the binding; changed source facts or contradictory identities stop reuse. Already partial rows can recover only from a unique match across their populated, recognized facts. Ambiguous or unknown populated data stays manual. User-reviewed English/Italian catalog aliases remain tied to their record.

The earlier executor also aborted at its first unresolved selection. It now defers that field once, continues other independent verified actions, and pauses for selection/validation review before navigation. A regression caught and corrected candidate-ID numbering after deferred actions were removed. Limits remain unchanged.

Older malformed checkpoints could send extra metadata or a missing/nonfinite elapsed time to strict API models. Checkpoints now project onto the current schema before resume/save. The worker reports safe validation locations instead of classifying every HTTP 422 as a version mismatch. Failed runs retain the failing operation and error category, including `save_progress` before any browser action. The screenshots alone do **not** establish which exception caused the owner's particular zero-action run; authenticated browser access was unavailable. The repaired paths are reproduced below.

The new real-MV3 regression runs in both languages with two education records, four language records, one certification and two skills. It deliberately fails university lookup while other fields fill, restores the catalog, resumes, commits both universities and accepts a synthetic CV. It also tests legacy `keyCode`/`which` Enter handlers, scoped tree items, virtual numbered proficiency choices, a simulated checkpoint transport failure, a malformed older checkpoint, and real backend 422 redaction. No employer is contacted and no submission occurs. Synthetic screenshots and JSON evidence remain outside Git under the local QA directory.

Known facts without a matching website option are now labeled `selection_unresolved`; unmatched populated records are `record_unresolved`. Neither is presented as missing candidate information. An unknown degree equivalence, GPA or proficiency scale still requires review.

## What was reproduced

Earlier fixtures used simpler record controls than the supplied Workday screenshots. They did not establish reliability for virtualized menus, Enter-triggered catalog searches, `Overall` language labels or split education-year IDs. This phase adds those behaviors to the existing application fixture rather than replacing the product.

| Supplied form | Read-only inspection and reconstruction | Local Chromium verification |
|---|---|---|
| HRM / Teamtailor-style Italian application | Anonymous public application opened; language radios, required helper labels, contact/address fields, CV/additional file inputs and two consent fields inspected | `/italian`, actual extension filling, missing answers, radio/checkbox policies, native file chooser, stale manual edits and document review |
| PwC Italian enterprise portal | Anonymous public controls inspected; native selects, source-category → Canale dependency, contact/address, calling-code and personal fields | `/italian-portal`, both direct and dependent-source variants, exact option selection, phone prefix changes, reviewed unknown facts, personal defaults preserved |
| Accenture / Workday application | Anonymous page reaches Sign In; authenticated controls were available only through user screenshots and local extension metadata | `/workday?actual=1&catalog=1`, EN/IT five-stage workflow, dynamic record IDs, catalog references, virtualized menus, skills, uploads, validation and final review |

Public inspection did not fill, upload or submit applicant information. Fixtures use invented people and organizations, without employer branding or private applicant records. Actual portal references: [HRM](https://careers.hrm.group/jobs/8614069-ai-engineer-freelance), [PwC](https://jobs-it.pwc.com/it/it/apply?jobSeqNo=PWAPIUIT685056WDEXTERNALITIT), [Accenture](https://accenture.wd103.myworkdayjobs.com/en-US/AccentureCareers/job/Milano/Agentic---Ontology-Architect_R00369633/apply/applyManually).

## Corrected behavior

- References open a scoped portal, type, trigger Enter when required, inspect actual choices, choose one unique match and verify a committed token/chip. Uncommitted search text is not counted as a valid selection.
- Custom menus scroll within their own bounded list, and preceding menus close. Ambiguous matches stop without selecting the first result. Available choices can be offered for review.
- Record bindings retain employment/education/language identity. Education `firstYearAttended` / `lastYearAttended` map to known years. `Overall` is a language-level control, separate from a fluent checkbox.
- Original national grades are not converted or copied into GPA fields. Unknown years, schools, degree levels, proficiency scales and legal facts require user input.
- Skills are selected individually and checked as committed tags. File selection reports rejection when the website's validator rejects it and otherwise asks the user to verify acceptance. The catalog fixture exposes an accepted-file indicator and rejects oversized files.
- A replaced field is re-observed and retried once. A page/server error, missing permission or unresolved required control stops progress. Failures identify section/row/label and cause.
- The side panel retains its authorized tab when its own UI receives focus or reloads. Backend connectivity and page permission are distinct.

## Agent evidence

The real unpacked MV3 extension pairs with an actual FastAPI server and drives the served fixture in Chromium. Both English and Italian tests:

1. Start, pause, reload the panel and resume the same checkpoint.
2. Fill personal information and move to the experience page.
3. Add/bind records and commit university, degree, field of study, language level and skill choices.
4. Pause for explicit native CV selection and verify the fixture's upload acceptance.
5. Pause for a missing factual answer and reviewed motivation text.
6. Pause for manual consent, resume explicitly and stop at final review.

A measured synthetic run used **33 steps, 29 verified actions and zero model calls**, with zero submissions. Wall time including test interactions was **15.683 s (English)** and **17.541 s (Italian)** on the local Windows test machine. These are individual fixture measurements, not production latency or completion-rate estimates.

Separate real Chromium cases verify duplicate/ambiguous results, a control replaced during catalog search, page/server errors, and final-review detection with Workday's concatenated progress label. Existing tests cover same-origin frames, multiple pages, upload rejection, manual-edit preservation, pairing and security boundaries.

The full local suite has **108 passing tests**, no skips/failures, and one Starlette/httpx deprecation warning. CI results must be checked for the published commit. Private test screenshots, traces and metrics are outside Git; only synthetic fixture/test source is published.

## Model and visual checks

Both local `qwen3.5:4b` and `qwen3.5:9b` were exercised with two synthetic tool-choice cases and one synthetic screenshot choice each. The final schema-constrained responses selected valid offered tools. Earlier unstructured attempts produced invalid responses, which were rejected; strict Ollama JSON schemas corrected that transport gap. The implementation follows [Ollama's structured-output contract](https://docs.ollama.com/capabilities/structured-outputs).

These are small smoke probes, not model safety certification or full model-driven website evaluations. Tool IDs, field snapshots, profile values, policy and user-review gates remain authoritative. Hosted-provider behavior has mocked transport coverage and still needs live verification.

## Reproduce

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest tests/test_extension_agent.py tests/test_workday_extension.py -q
.venv\Scripts\python.exe -m pytest tests/test_extension_agent.py -k partial_records -q
.venv\Scripts\python.exe -m forgeapply
```

In another terminal:

```powershell
.venv\Scripts\python.exe -m examples.fixture_server --port 8766
```

Reload ForgeApply at `chrome://extensions` and reopen the side panel. Use synthetic profile data in an isolated instance as described in [the usage guide](USAGE.md#practice-without-an-employer). Open `http://127.0.0.1:8766/workday?actual=1&catalog=1&lang=it`, then Complete Application. Supply missing facts and a synthetic CV, review drafts, handle consent on the fixture, and resume to final review. Do not submit a real employer application during testing.

## Remaining boundaries

This is a bounded preparation agent, not a completed universal browser platform. No authenticated live Workday/PwC completion is proven. Nested catalogs, undisclosed canonical IDs, closed shadow roots, cross-origin frames, arbitrary coordinate clicking, OS mouse control, persistent execution with the panel closed, every ATS tenant and unknown applicant facts remain unsupported or require manual verification. See [release readiness](../RELEASE_READINESS.md).
