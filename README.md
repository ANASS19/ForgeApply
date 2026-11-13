# ForgeApply — Local AI Job Application Workspace

A runnable **local application workspace under active development** with a persistent browser, optional local/hosted inference, deterministic form preparation, job-board discovery, resume management and application tracking. Controlled Chromium fixtures verify the supported form workflow; arbitrary employer sites remain unverified.

> **Scope:** A working local tool, not a promise that LinkedIn/Indeed permit unattended mass submission. Sites and employers differ. The app handles supported forms and asks for final submission approval; LinkedIn/Indeed final submission remains manual. No CAPTCHA evasion, anti-bot bypass, or credential collection.

## Windows: run in 3 steps

1. Install **Python 3.11+** and optionally [Ollama](https://ollama.com/). For local form understanding, run `ollama pull qwen3:4b`; choose a vision-capable Ollama model such as `gemma3:4b` if you want screenshot understanding (check installed Ollama tags).
2. Unzip this project, then double-click **`start_windows.bat`**. The first run creates a venv, installs requirements and downloads Playwright Chromium.
3. Open **http://127.0.0.1:8765** in your browser. The app stores its local SQLite database, resumes and Chromium login state under `%USERPROFILE%\.forgeapply`.

PowerShell manual setup:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m forgeapply
```

Mac/Linux: `sh start_linux_mac.sh`, then open `http://127.0.0.1:8765`.

## Practical workflow

1. **Candidate & CVs** — supply your verified info. Upload one English and one Italian resume (PDF or DOCX). Uncertain legal/immigration questions should remain blank until verified.
2. **Screening Answers** — add reusable regex patterns with truthful answers, such as `(?i)years.*python` → your actual Python experience.
3. **Job Sources** — add public company job-board slugs for Greenhouse, Lever, or Ashby. Sync to discover active listings directly via public APIs. Or import a CSV of listings. LinkedIn and Indeed have no general, unrestricted applicant-facing submission API.
4. **Job Queue** — review titles, scores, statuses and external links. Click **Open** to launch the separate persistent Playwright Chromium browser.
5. **Browser Agent** — sign in manually in the visible browser. Select a job and click **Auto-fill known fields**, or **Agent: prepare current job**. Deterministic filling is the default. Enable **Allow CV upload** for the selected job before preparation attaches a document. Unexpected destination origins require a separate approval. AI proposals for unknown fields require manual review and are never filled as verified facts. **AI + vision fill** requests a screenshot proposal from a vision-capable model.
6. **Next / Review** progresses supported multi-page forms. **Upload EN/IT CV** chooses the locally saved resume for that language.
7. Preparation always stops for review. On LinkedIn/Indeed, final submission is manual. On permitted employer sites, explicit approval is tied to the prepared job, URL and page fingerprint. A changed page requires review again. A submission attempt is persisted before the click; ambiguous attempts cannot be replayed automatically. Inspect and confirm manually when success is unclear.
8. **Export CSV** for a complete application record. A submitted status cannot be accidentally reverted during re-import.

## Inference

- **Ollama:** local `POST http://127.0.0.1:11434/api/chat`, JSON outputs, configured via AI Settings. Works offline when the model is downloaded. Vision requires a multimodal Ollama model.
- **Hosted:** OpenAI-compatible `POST /v1/chat/completions`. Configure provider `openai`, model and base URL, and explicitly enable remote inference. Remote endpoints require HTTPS. Set `FORGEAPPLY_API_KEY` (or `OPENAI_API_KEY`) in the process environment. No API key is saved in SQLite. Loopback OpenAI-compatible servers can run without a key; environment keys are not sent to local endpoints.
- **Deterministic first:** personal facts and your saved screening answers are filled before any LLM call. LLM never receives account cookies or passwords. HTML page text and optional screenshots may contain sensitive information; choose hosted inference only if you accept that data transfer.

## Agent capabilities / limitations

| Function | Status |
|---|---|
| Persistent browser, login, navigation | Implemented |
| Detect form fields and labels | Implemented, DOM-first |
| Click Easy Apply, Next, Review | Implemented with visible browser; may need manual site interaction |
| Fill personal details and saved answers | Implemented |
| AI-assisted questions (Ollama/hosted) | Validated proposals requiring human review; provider transports tested with mocks |
| Screenshot capture and image understanding | Implemented; requires VLM for analysis |
| OCR | Optional local Tesseract adapter; explicit vision OCR alternative |
| CV file upload | Hidden inputs and labelled multiple inputs; attachment readback verified in fixtures |
| Native/custom dropdowns, rich text, dates, dynamic fields, same-origin iframes | Controlled Chromium fixtures; site variants need review |
| Execution journal, bounded steps/time/model calls, pause/resume | Integrated API/dashboard; journal persists in SQLite |
| Browser tools and accessibility inspection | Typed API with bounded locators and navigation controls |
| ATS discovery: Greenhouse, Lever, Ashby | Implemented public read-only feeds |
| CSV import/export and local SQLite tracker | Implemented |
| Automatically defeat CAPTCHA/site security | Not supported |
| Unrestricted LinkedIn/Indeed 100-job mass submission | Not supported or guaranteed |
| Fully autonomous browser agent on arbitrary sites | Not guaranteed; app combines deterministic controls and model suggestions, not unconstrained arbitrary actions |

## Tests

```bash
python -m pytest -q
```

Windows validation uses `.venv\Scripts\python.exe -m pytest -q`. CI covers Python 3.11/3.13 on Windows/Ubuntu. Launch the synthetic form server separately with `.venv\Scripts\python.exe -m examples.fixture_server --port 8766`, then open `http://127.0.0.1:8766/controls` in the Browser Agent. No employer applications are involved.

The API exposes `POST /api/browser/tool` with validated tools for inspection, accessibility, navigation, exact role/label/field targeting, fill/type/clear/select/check, restricted clicks/keys, hover, scroll, waits, screenshots, resume upload and tab selection. Frame-specific role/label targets are supported. Arbitrary scripts, selectors and shell execution are not accepted. See `/api/docs` for schemas. Use `snapshot_id` when editing an inspected field to reject stale UI actions.

Flat profile compatibility is retained. Structured education, experience, skills, languages and preferences use `GET/PUT /api/candidate-context`; profile and screening answers retain provenance timestamps. The dashboard displays the structured context. No personal candidate defaults are shipped.

**Local OCR:** install a Tesseract OCR distribution for your OS and add its installation directory to `PATH` (verify with `tesseract --version`), then restart ForgeApply. It is optional and not bundled. A missing executable produces installation guidance. Choosing vision OCR uses the configured provider and requires remote consent when applicable.

API documentation at `http://127.0.0.1:8765/api/docs`.

## Security

The HTTP server binds **127.0.0.1 only**. Do not port-forward it, expose it publicly, or store it on a shared computer. Browser login cookies live in the local Chromium profile. Resumes and answers live only in your local folder unless you expressly send information to a hosted model. Never put private data or API keys into source control. Confirm work authorization answers yourself before using them in legal declarations.

Mutations reject cross-site requests and mismatched origins, including different loopback ports. Host validation reduces DNS rebinding exposure. API responses disable caching. Credentials in navigation URLs are rejected. Legal/sensitive declarations are not automatically answered, even by a broad saved answer. Cross-origin iframe fields are not filled from profile data automatically. Browser sessions and SQLite remain ordinary local OS files, without application-level encryption or multi-user isolation.

CV uploads allow PDF/DOCX up to 8 MB, check signatures/container structure, and use content-hashed filenames so previous files are preserved. These checks do not establish factual accuracy, document safety or employer acceptance. Application receipts record actual attachment hashes when uploaded through the browser. No screenshot/CV is sent to inference in deterministic mode. Remote inference is off unless explicitly enabled; when enabled it can receive candidate facts, page text and optionally a screenshot. No telemetry is implemented.

Restart preserves records, journals, submission locks and Chromium session cookies. It does **not** restore arbitrary unsaved SPA form state. Resume and inspect before taking further action. Employer form adapters, strict vacancy recency/eligibility gating, a durable scheduling queue, encrypted multi-user profiles and signed installers remain unfinished. This is suitable for supervised local development, not a complete public release. See [the audit](AUDIT.md) for evidence and limitations.

## Technical architecture

- `forgeapply/app.py`: FastAPI server and local application API
- `forgeapply/store.py`: SQLite schema, status auditing, normalization/dedup
- `forgeapply/discovery.py`: company ATS discovery + scoring + CSV import
- `forgeapply/browser.py`: persistent Playwright Chromium and live DOM form executor
- `forgeapply/browser_tools.py`: strict browser action/target schemas
- `forgeapply/candidate.py`: narrowly scoped reusable answers from supplied verified facts
- `forgeapply/ocr.py`: optional local OCR adapter
- `forgeapply/llm.py`: Ollama/OpenAI-compatible JSON decisions, optional screenshots
- `static/`: responsive dark-blue dashboard
- `tests/`: focused tests for data integrity, job parsing and app API

This is a local application, not a ChatGPT-installed skill or a cloud scheduler. It is suitable for further packaging as a native executable or MCP server if you later want those integrations.
