# ForgeApply verification and release gaps

Updated 2026-11-14. This is an engineering status, not a universal compatibility claim.

## Verified locally

Windows Python 3.13, actual FastAPI server, SQLite and real Playwright Chromium load the unpacked MV3 extension. The test suite covers:

| Area | Evidence |
|---|---|
| Extension connection | Pair once, reload without losing connection, reject wrong origin/token, revoke |
| English/Italian forms | Text, required helpers, native selects, radio groups, factual checkboxes, custom/search dropdowns, same-origin frames |
| Workday-style wizard | Five stages, dynamic nonsequential input IDs, repeat employment/education/certification/language rows, split month/year, skills tags |
| Italian enterprise portal | Source and prior-employer choices, Via/Piazza, opaque province options, separate calling code/national number, missing date of birth, manual personal fields, review |
| Recovery | Fresh inspection after dynamic dependencies, one replaced-control retry, stale/manual edit protection, validation errors, full document navigation without clicking twice |
| Extension agent | EN/IT bounded run-to-review, pause/reload/resume, local checkpoints, action trace, virtual cursor and manual checkpoints |
| Catalog variants | Enter-to-search university/field-of-study references, virtualized degree/language lists, committed chips, ambiguous options and server errors |
| Documents | Native CV chooser, reviewed bilingual CV/letter drafts, local PDF/text export; configured CVs retained |
| Local profile | Multiple editable background records, unknown metadata retained, learning-only skills excluded, completed degree checks |
| Model assistance | Strict structured responses, reviewed references to current profile facts, host-scoped learned mappings, deterministic/manual fallback |
| Privacy and storage | Origin/CSRF controls, loopback-only server, additive SQLite migrations, no credentials or applicant files in source |

The full suite currently has 103 passing tests and one dependency deprecation warning. No tests are skipped. JavaScript syntax, dependency integrity and diff whitespace checks also pass. [Detailed reconstruction and evidence](docs/WORKDAY_VERIFICATION.md) distinguishes read-only public inspection from authenticated workflows.

The Italian portal and actual Workday input shapes were reconstructed from locally received control metadata and screenshots. Tests use synthetic people, organizations and documents. The development tools could not access the user's authenticated browser session. An employer's visible default nationality/birthplace is never evidence about the candidate.

A live local Qwen3.5 9B synthetic probe returned three exact profile references and left an unknown numerical question unanswered. Both installed 4B/9B models also passed small schema-constrained text/screenshot tool-choice probes. Earlier safety evaluations still found factual failures: model output remains advisory and field facts stay gated. Hosted transports have mocked tests; no live paid-provider compatibility or cross-provider reliability is claimed.

## Public release blockers

- Verify permitted authenticated tenant workflows with operators, especially nested/virtualized menus, dependent selects, rerender timing, repeated-section variants and uploads. No live PwC/Accenture end-to-end completion or real submission has been verified.
- Test clean installation and upgrade with independent Windows/Chrome operators; verify Edge/macOS and normal side-panel interaction separately. CI defines Windows/Ubuntu and Python 3.11/3.13, but the current local result is Windows 3.13 only.
- Cross-origin frames and closed shadow roots are unsupported. Open shadow roots are not traversed by the extension yet. Passwords, CAPTCHA, legal/consent and protected demographic declarations remain manual.
- A page inspection is bounded to 100 controls; Next is blocked when truncated. Repeat expansion is bounded to ten records per recognized section. Arbitrary site navigation is not an autonomous all-purpose agent.
- Extension runs are bounded to 80 steps, three minutes and three model requests. Panel closure interrupts execution; checkpoints require explicit fresh observation/resume. The virtual cursor is a DOM overlay. Unrestricted coordinate actions and OS mouse control are not implemented.
- Review personal data defaults on every employer site. Birth answers are not saved as reusable screening answers; sensitive fields have no generalized automatic consent mechanism.
- Saved exact question patterns currently have one host scope per pattern; learning the same label on another host can replace its earlier mapping. Canonical profile fields remain available. Revisit this schema for broader mapping libraries.
- Record-specific remembered answers can become outdated when the underlying history changes; review before reuse. Comprehensive conflict resolution and per-field reuse policies remain incomplete.
- Multi-profile isolation, credential encryption/keychain onboarding, packaging, general RAG and measured specialist-agent orchestration remain future work. The existing browser task journal is not evidence of a completed multi-agent platform.

## Reproduce

From the repository in PowerShell:

```powershell
.venv\Scripts\python.exe -m pytest -q
node --check extension\content.js
node --check extension\panel.js
node --check static\app.js
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m forgeapply
```

Open `http://127.0.0.1:8765`. For a separate synthetic portal:

```powershell
.venv\Scripts\python.exe -m examples.fixture_server --port 8766
```

Open `/italian-portal`, `/workday?actual=1&catalog=1&lang=it`, or `/workday?actual=1&catalog=1&lang=en` at `http://127.0.0.1:8766`. Load the repository's `extension` folder at `chrome://extensions`, connect once, choose Keep open, then Complete Application. Enter missing verified answers, apply reviewed answers, choose a synthetic CV, and resume to review. Prepare & Fill this page remains available. Never submit a real application during a smoke test.

The next highest-value verification is an operator-assisted permitted live flow, comparing actual dropdown and validation behavior with these regressions. See [extension usage](extension/README.md) and [audit history](AUDIT.md).
