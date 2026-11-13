# Changelog

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
