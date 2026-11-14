# Changelog

## 0.4.3 — Partial-form and execution recovery · 2026-11-14

- Retain verified row bindings when a university lookup fails after dates fill; recover uniquely identifiable partial rows without guessing ambiguous records. Invalidate bindings when source facts change.
- Continue independent fields after an unresolved selection, then pause for review. Keep tool candidate IDs bounded and tied to their original actions.
- Normalize old checkpoints before resume/save; expose the failing operation and safe HTTP validation details instead of a generic interruption/version error.
- Support legacy Enter key codes, scoped tree items and numbered option labels. Block Next when required custom controls remain invalid.
- Distinguish missing information from catalog mismatches and unmatched records; preserve reviewed bilingual record aliases.
- Verification: 108 local tests, including actual MV3 Chromium EN/IT catalog failure/recovery, two education records, four languages, certification, committed skills and accepted synthetic CV. No authenticated live Workday completion or real submission is claimed.

See [evidence](docs/WORKDAY_VERIFICATION.md), [reload instructions](docs/USAGE.md#update-safely) and [remaining limits](RELEASE_READINESS.md).

## 0.4.2 — Agent and Workday regression preview · 2026-11-14

- Add Complete Application: a short-horizon observe/plan/act/verify loop with 80-step, three-minute and three-model-call bounds. Supported steps advance automatically; unknown facts, documents, validation, legal review and final review stop for the user.
- Add pause/stop/resume, Chrome/backend checkpoints, human-readable action traces, and safe recovery after a panel reload. The page cursor overlay shows targets; it does not move the OS pointer.
- Fix Enter-triggered catalog queries, scoped portal menus, bounded virtual-list scrolling, actual committed-chip verification, and one retry for replaced controls.
- Map education year IDs and language Overall; preserve original grading scales and require explicit GPA. Verify skills as tags and distinguish file rejection from selection.
- Keep the side panel bound to its application tab when its own UI receives focus. Distinguish page permission from backend connection.
- Add allowlisted model tool choices, strict Ollama JSON schemas, optional resized screenshot reasoning and local screenshot preview. Vision defaults off; hosted consent and live DOM guards still apply.
- Expand the synthetic Workday fixture and Italian/HRM forms using read-only public inspection, screenshots and captured control metadata. Add ambiguous, rerender, server-error, source-dependency, upload and final-review regressions.
- Validation: 103 local tests, real EN/IT Chromium run-to-review evidence, both installed Qwen models exercised with small synthetic text/vision probes, and private profile/database/pairing preservation checks. No real employer application submitted.

See [regression evidence](docs/WORKDAY_VERIFICATION.md), [usage](docs/USAGE.md) and [release limitations](RELEASE_READINESS.md). This is a supervised development preview, not universal Workday compatibility.

## 0.4.1 — Development preview · 2026-11-14

This source release combines the local browser-executor foundation, paired Chrome assistant, bilingual form preparation and enterprise-form regressions. It is intended for supervised evaluation, not a claim of universal ATS compatibility.

### Application workflow

- Compact extension with one Prepare & Fill action, editable answer cards, optional questions collapsed, and Keep open side panel.
- Persistent authenticated pairing without automatic expiry; five-minute single-use setup codes, explicit disconnect/revocation and update guidance.
- Shared English/Italian fact mapping, native/custom/search dropdowns, factual checkboxes/radios, same-origin frames, CV chooser and multi-page review.
- Workday-style repeated employment, education, certification and language records; dynamic IDs, split month/year and skills tags.
- Italian enterprise-form coverage for Via/Piazza, Canale, province and separate phone calling codes; application-scoped referral answers.
- Bounded re-observation after dynamic changes, stale/manual-edit protection, validation checks and honest unresolved-field reporting.

### Profile, AI and documents

- Structured background editor preserving existing metadata; additive SQLite answer-mapping metadata migrations.
- Ollama and OpenAI-compatible inference, deterministic mode, validated advisory responses and reviewed references to current profile facts.
- Bilingual CV/motivation-letter drafts, verified certifications, editable review and local PDF/text export. Saved CVs are preserved.
- Model diagnostics and synthetic benchmark tooling; both measured local presets still require human review.
- Backend health/OpenAPI and extension metadata aligned to version 0.4.1. Older backend 1.0.0 strings were placeholder metadata, not a stable-release guarantee.

### Documentation and publication

- Forge AI navy/cyan SVG banner, concise project overview, full usage guide with Italian quick start, upgrade/troubleshooting steps and release evidence matrix.
- Source archive publication replaces the legacy encoded-source bootstrap workflow. No applicant data, CVs, browser profiles, secrets or private handoff documents belong in the release.
- Consolidated public commit uses GitHub noreply metadata; private working data remains outside Git.

### Verification and limits

91 tests pass on Windows Python 3.13, including the actual unpacked MV3 extension against a real FastAPI server and served Chromium fixtures. JavaScript syntax and dependency checks pass. CI is configured for Windows/Ubuntu and Python 3.11/3.13; consult the published commit's Actions run for its result.

No real application was submitted. Authenticated employer completion, all dropdown/tenant variants, cross-origin frames, shadow DOM, live hosted-provider behavior, clean operator installation and production reliability remain unverified or unsupported. See [release readiness](RELEASE_READINESS.md). Final submissions, passwords, CAPTCHA and sensitive declarations remain user-controlled. No Web Store/PyPI distribution or selected source license is included.

Start with the [usage guide](docs/USAGE.md), then practice on the local fixture before trying a permitted employer workflow.
