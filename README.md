# ForgeApply — Local AI Job Application Workspace

A complete runnable **local application workspace** with an embedded browser agent, local/hosted LLM inference, screenshot capture, deterministic/AI-assisted form filling, job-board discovery, CSV import/export, resume management and auditable application tracking.

> **Scope:** A working local tool, not a promise that LinkedIn/Indeed permit unattended mass submission. Sites and employers differ. The app handles supported forms and asks for final submission approval; LinkedIn/Indeed final submission remains manual. No CAPTCHA evasion, anti-bot bypass, or credential collection.

## Windows: run in 3 steps

1. Install **Python 3.11+** and optionally [Ollama](https://ollama.com/). For local form understanding, run `ollama pull qwen3:4b`; choose a vision-capable Ollama model such as `gemma3:4b` if you want screenshot understanding (check installed Ollama tags).
2. Unzip this project, then double-click **`start_windows.bat`**. The first run creates a venv, installs requirements and downloads Playwright Chromium.
3. Open **http://127.0.0.1:8765** in your browser. The app stores its local SQLite database, resumes and Chromium login state under `%USERPROFILE%\.forgeapply`.

PowerShell manual setup:

```powershell
py -3.11 -m venv .venv
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
5. **Browser Agent** — manually sign in to a job site in this visible browser, then click **Auto-fill known fields**. Form fields are detected from live DOM labels and filled deterministically. Unknown fields may be answered by your configured LLM using verified facts. **AI + vision fill** sends a screenshot to a *vision-capable* model. Unanswered questions are shown in the dashboard.
6. **Next / Review** progresses supported multi-page forms. **Upload EN/IT CV** chooses the locally saved resume for that language.
7. For LinkedIn/Indeed, click the final Submit button in the visible browser, verify success, then mark **I submitted it manually** in the dashboard. For supported employer websites, select explicit approval mode and click **Submit / confirm**; the app only marks success when the page shows confirmation.
8. **Export CSV** for a complete application record. A submitted status cannot be accidentally reverted during re-import.

## Inference

- **Ollama:** local `POST http://127.0.0.1:11434/api/chat`, JSON outputs, configured via AI Settings. Works offline when the model is downloaded. Vision requires a multimodal Ollama model.
- **Hosted:** OpenAI-compatible `POST /v1/chat/completions`. Configure provider `openai`, model, and optional base URL. Set `FORGEAPPLY_API_KEY` (or `OPENAI_API_KEY`) in the process environment. No API key is saved in SQLite.
- **Deterministic first:** personal facts and your saved screening answers are filled before any LLM call. LLM never receives account cookies or passwords. HTML page text and optional screenshots may contain sensitive information; choose hosted inference only if you accept that data transfer.

## Agent capabilities / limitations

| Function | Status |
|---|---|
| Persistent browser, login, navigation | Implemented |
| Detect form fields and labels | Implemented, DOM-first |
| Click Easy Apply, Next, Review | Implemented with visible browser; may need manual site interaction |
| Fill personal details and saved answers | Implemented |
| AI-assisted questions (Ollama/hosted) | Implemented; results depend on model quality |
| Screenshot capture and image understanding | Implemented; requires VLM for analysis |
| OCR | Via model vision; no separate OCR engine |
| CV file upload | Implemented for visible file input controls |
| ATS discovery: Greenhouse, Lever, Ashby | Implemented public read-only feeds |
| CSV import/export and local SQLite tracker | Implemented |
| Automatically defeat CAPTCHA/site security | Not supported |
| Unrestricted LinkedIn/Indeed 100-job mass submission | Not supported or guaranteed |
| Fully autonomous browser agent on arbitrary sites | Not guaranteed; app combines deterministic controls and model suggestions, not unconstrained arbitrary actions |

## Tests

```bash
python -m pytest -q
```

API documentation at `http://127.0.0.1:8765/api/docs`.

## Security

The HTTP server binds **127.0.0.1 only**. Do not port-forward it, expose it publicly, or store it on a shared computer. Browser login cookies live in the local Chromium profile. Resumes and answers live only in your local folder unless you expressly send information to a hosted model. Never put private data or API keys into source control. Confirm work authorization answers yourself before using them in legal declarations.

## Technical architecture

- `forgeapply/app.py`: FastAPI server and local application API
- `forgeapply/store.py`: SQLite schema, status auditing, normalization/dedup
- `forgeapply/discovery.py`: company ATS discovery + scoring + CSV import
- `forgeapply/browser.py`: persistent Playwright Chromium and live DOM form executor
- `forgeapply/llm.py`: Ollama/OpenAI-compatible JSON decisions, optional screenshots
- `static/`: responsive dark-blue dashboard
- `tests/`: focused tests for data integrity, job parsing and app API

This is a local application, not a ChatGPT-installed skill or a cloud scheduler. It is suitable for further packaging as a native executable or MCP server if you later want those integrations.
