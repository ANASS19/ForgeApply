# Contributing

Use Python 3.11+ (Windows development is verified with 3.13). Preserve existing APIs and local data; use additive, idempotent SQLite migrations. Keep the compact blue dashboard and deterministic execution as the default.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m pytest -q
node --check static\app.js
git diff --check
```

Tests isolate SQLite, browser profiles and uploaded files in temporary directories. Browser integration tests require installed Chromium. The synthetic server is available via `python -m examples.fixture_server --port 8766`. Never use employer submissions as an unattended regression test.

For browser changes, cover the resulting state as well as the action: attachment readback, select/checkbox/radio state, dynamic replacement, stale snapshots, validation, missing candidate facts, timeout or outage, explicit review and submission replay prevention. Do not add model-generated facts to the verified profile. New tools need a strict schema and a defined sensitive-action boundary.

Before committing, inspect every staged path and diff. Never stage personal context handoffs, candidate profiles, real CVs, screenshots, cookies, databases, logs or credentials. `FORGEAPPLY_HOME` can isolate a development installation. It must point outside tracked source. Browser sessions and saved screening facts are sensitive even when no password is present.

Report fixture evidence separately from live ATS/model verification. ForgeApply is licensed under Apache-2.0; see LICENSE and NOTICE. Retain applicable copyright and attribution notices, mark modifications as required by the license, and contribute only code you have the right to submit. Third-party dependencies retain their own licenses. New contributions are accepted under Apache-2.0 unless explicitly stated otherwise.

The MV3 test loads the unpacked `extension/` directory in Chromium; do not remove origin/token/CSP checks to make it pass. Optional real inference benchmarks require `benchmarks/requirements.txt` and installed local models. Do not run paid APIs in CI or commit benchmark output directories. See `benchmarks/README.md` for the fixed protocol, privacy boundary and audited scoring rules.
