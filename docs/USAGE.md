# Using ForgeApply 0.4.1

[Overview](../README.md) · [Extension details](../extension/README.md) · [Release limitations](../RELEASE_READINESS.md)

ForgeApply runs on your computer. The dashboard stores your verified information; the extension assists the application tab you select. The optional Browser Agent opens a separate Playwright browser. You do not need to use both browser modes for one application.

## Install and start

Follow the Windows commands in the [README](../README.md#start-on-windows). Keep the terminal running while you use ForgeApply. Stop it with Ctrl+C. Start again from the repository:

```powershell
.venv\Scripts\python.exe -m forgeapply
```

Open `http://127.0.0.1:8765`. Do not expose this server on your network or port-forward it.

## Set up your information once

Open **Candidate & CVs**:

1. Enter your actual contact details, address and professional links, then **Save profile**.
2. Expand the background sections. Add each employment, education, certification and language record separately. Mark education completed only when the qualification was awarded. Enter exact dates only when known; do not invent missing months.
3. Enter verified skills. Planned/learning-only skills remain excluded from automatic filling.
4. Click **Save verified background**.
5. Upload an English and/or Italian CV. Dashboard uploads accept validated PDF/DOCX up to 8 MB. The employer may impose a smaller limit or different requirements.

The profile starts without private candidate defaults. A CV text preview is not a verified profile import. Keep legal eligibility, salary, availability and protected demographic information under your own review.

## Configure AI (optional)

Open **AI Settings** from the dashboard's More tools menu. Save settings, then choose **Check provider / model**.

| Mode | Settings | What to expect |
|---|---|---|
| Deterministic | Turn off AI for unfamiliar questions in extension Settings → More options | Known facts fill without a model; missing answers remain for you |
| Local Ollama | Provider `Ollama local`, exact installed model name, default endpoint `http://127.0.0.1:11434` | Local inference; no API key needed |
| Local compatible server | Provider `OpenAI-compatible API`, local model name, server's compatible base URL, usually ending in `/v1` | Compatible chat endpoint required; environment keys are not forwarded to loopback |
| Hosted compatible API | Provider `OpenAI-compatible API`, provider's exact model and HTTPS base URL | Requires explicit remote consent and process environment key |

For Ollama, verify the installation and available models in a separate terminal:

```powershell
ollama list
```

Install a model suited to your hardware if needed; model downloads can be large. The measured presets are `qwen3.5:4b` and `qwen3.5:9b`. Other Ollama models can be configured by exact name, but their output quality and capabilities are not automatically verified. Screenshots require a vision-capable model.

For hosted inference, set `FORGEAPPLY_API_KEY` in the terminal that launches ForgeApply. The following avoids putting a literal key into shell history:

```powershell
$providerSecret = Read-Host 'Provider API key' -AsSecureString
$env:FORGEAPPLY_API_KEY = [System.Net.NetworkCredential]::new('', $providerSecret).Password
.venv\Scripts\python.exe -m forgeapply
```

Set provider/model/base URL in the dashboard and enable **Allow sending candidate data and optional screenshots to a remote inference endpoint** only if you accept that transfer. Keys are read from the server process environment, not stored in SQLite. Restart after changing the environment. Never include a key in a URL, screenshot, issue, source file or Git commit.

Disabling the extension AI checkbox disables new model requests from that workflow. It does not revoke facts or documents you already sent to a remote service. Local Ollama/compatible inference and deterministic filling do not require hosted consent.

## Connect Chrome once

1. Open `chrome://extensions` and enable **Developer mode**.
2. Choose **Load unpacked** and select the repository's `extension` directory. Select the directory itself; Chrome filters the file picker to folders.
3. Open the ForgeApply toolbar icon on an application page.
4. In dashboard **AI Settings → Chrome extension**, choose **Generate connection code**.
5. Paste the code into the assistant and click **Connect ForgeApply**. Codes last five minutes and are single-use. The resulting connection has no automatic expiry and survives browser/backend restarts until revoked or disconnected.
6. Click **Keep open** to use Chrome's persistent side panel.

The default backend port is 8765. If you deliberately changed it, update the extension's port under More options. Use Reload rather than Remove when updating; removing the extension can erase its local connection.

## Fill an application

Open a permitted employer application page and sign in manually if needed. ForgeApply does not enter passwords or bypass CAPTCHA.

1. Choose the answer language: Automatic, English or Italiano.
2. Click **Prepare & Fill**. Known verified facts fill directly. A freshly opened paired panel may inspect the selected page to show a preview, but it does not fill until you request it.
3. Review outstanding answer cards. Required questions are visible; optional answers are collapsed. Enter actual answers, choose the available dropdown options, then **Fill reviewed answers**.
4. Reusable factual answers are remembered locally by default; disable **Remember verified personal answers locally** when you do not want that. Referral sources stay scoped to the application URL. Prior-employer questions stay specific to the employer/question. Birth answers are not stored as general reusable screening answers.
5. Use **Attach CV / document** to open the website's native chooser. Choose the correct reviewed file and verify the website attachment. The extension does not attach a local path from your saved profile automatically.
6. Review personal/legal fields on the website. Existing nationality and birthplace defaults are not verified candidate facts. Consent, work authorization and protected demographic declarations stay manual.
7. Choose **Continue to next step**, inspect validation errors, then use Prepare & Fill on the new step.
8. Review the employer's final summary and submit manually if you choose. No final submission button is provided by the extension.

Existing nonempty values are preserved. Invalid city-search terms or phone numbers can be repaired only when they still match a verified profile fact. When a separate explicit calling code is selected, missing national-number fields use the appropriate verified number without repeating the prefix. A country code shared by multiple choices remains ambiguous and needs review.

Recognized repeated sections can add up to ten verified records each. The controlled tests cover employment, education, languages and certifications, including Workday-style dynamic input IDs, split month/year and skills tags. Unknown dates, proficiency components and GPA are not inferred. Unsupported dropdowns should be selected on the page; a typed search term alone may not count as a selected option.

## Draft CVs and motivation letters

Choose **Draft CV** or **Motivation letter** in the assistant. Provide role/company details under Opportunity details when useful. Review every claim and edit the draft before choosing **Reviewed - download PDF** or plain text.

Deterministic drafts use verified background facts. Optional AI can refine wording or translation; a failed model request keeps the factual fallback. Downloads do not replace your saved CV automatically. Upload a reviewed result in Candidate & CVs if you want to configure it as your reusable CV.

## Practice without an employer

Start with dashboard `/demo/en` or `/demo/it`, whose final submit controls are disabled. For realistic controlled forms, run a second terminal:

```powershell
.venv\Scripts\python.exe -m examples.fixture_server --port 8766
```

| URL | Practice |
|---|---|
| `http://127.0.0.1:8766/italian-portal` | Italian source/employer/phone dropdowns, address and personal information |
| `http://127.0.0.1:8766/workday?actual=1&lang=it` | Five-stage Italian wizard and repeated background records |
| `http://127.0.0.1:8766/workday?actual=1&lang=en` | Equivalent English wizard |
| `http://127.0.0.1:8766/controls` | Dynamic controls, custom dropdown and same-origin iframe |

For a test profile isolated from your real information, launch a separate instance with an empty directory **outside the repository** and another port:

```powershell
$env:FORGEAPPLY_HOME = Join-Path $env:TEMP 'forgeapply-practice'
$env:FORGEAPPLY_PORT = '8767'
.venv\Scripts\python.exe -m forgeapply
```

Open `http://127.0.0.1:8767`, enter synthetic facts, and connect a test extension to port 8767. The directory is reused on subsequent runs; choose a new directory for a fresh practice profile. Close this terminal afterward to avoid retaining its environment overrides. Keep your usual paired extension on port 8765 unless you intend to switch it.

## Track jobs or use the separate Browser Agent

Opportunity details → **Save job** records a URL and your supplied details. Dashboard Job queue holds statuses and CSV import/export. Public Greenhouse, Lever and Ashby feeds can be added under Job discovery. A prepared/reviewed form is not a submitted application.

The dashboard **Browser Agent** uses a separate persistent Playwright Chromium profile, so its login state differs from your normal Chrome. Select a queued job, Open it, sign in manually, inspect, and fill known fields. Explicit document/destination controls and per-job submission review apply in this mode. See the [engineering workflow](ENGINEERING.md#practical-workflow). Do not operate both modes on the same application simultaneously.

## Update safely

Stop the server, back up `%USERPROFILE%\.forgeapply` privately, and update the source. If you changed `FORGEAPPLY_HOME`, back up that directory instead. Keep backups out of the repository and do not share them.

```powershell
git pull --ff-only
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m forgeapply
```

At `chrome://extensions`, click **Reload** on ForgeApply, then reopen its panel. Existing data uses additive migrations; the assistant connection stays saved. Inspect your partially completed form before continuing. Arbitrary unsaved website state is not restored after a crash/reload.

## Troubleshooting

| Symptom | Action |
|---|---|
| Empty-looking folder picker | Select the `extension` directory and click Select folder; do not search for a `.crx` |
| Backend offline | Start ForgeApply, open its loopback URL, check the port; the saved pairing need not be replaced |
| Update required / Unknown extension request | Reload ForgeApply at `chrome://extensions`, restart the backend, and reopen the panel |
| Pair code rejected | Generate a fresh code; it is single-use and expires after five minutes |
| Form does not react | Inspect required answers, native validation and custom dropdown selection; use the website manually for unsupported controls |
| Country/province/city changes other fields | Prepare & Fill re-observes within bounded limits; inspect and retry unresolved choices if the page is still loading |
| Some questions remain blank | Supply verified answers; legal/sensitive questions stay on the page. Do not make the model guess |
| Model unavailable | Check Ollama/server, exact model name and endpoint; turn off AI to continue deterministically |
| Missing upload | Use the website chooser and check its file-size/type rules; a filename readback is not proof of server acceptance |
| Page inspection limit | Collapse completed records or continue manually; Next is blocked above 100 inspected controls |
| LinkedIn/Indeed autofill unavailable | Use a permitted employer page; native inspection/autofill is disabled on these platforms |

Report a bug with the extension version, browser/OS version, ATS type, sanitized error and minimal synthetic reproduction. Remove names, contact details, CVs, applicant IDs, URL tokens and session data from reports. Do not attach your database, browser profile, raw logs or private screenshots.

## Guida rapida in italiano

1. Avvia ForgeApply e apri `http://127.0.0.1:8765`.
2. Inserisci dati verificati e CV in **Candidate & CVs**; salva anche formazione, esperienze, certificazioni e lingue.
3. In `chrome://extensions`, attiva la modalità sviluppatore e carica la cartella **extension**.
4. Genera un codice in **AI Settings → Chrome extension** e collega l'assistente una volta. La connessione resta memorizzata.
5. Apri il modulo consentito, scegli **Keep open**, lingua Italiano, quindi **Prepare & Fill**.
6. Completa le risposte mancanti, controlla i testi e premi **Fill reviewed answers**. Seleziona il CV con **Attach CV / document**.
7. Verifica sul sito dati personali, dichiarazioni e consensi. Premi **Continue to next step** per il passaggio successivo.
8. Controlla la revisione finale e invia personalmente solo se desideri. L'assistente non deve inventare dati né inviare automaticamente una candidatura.

Questa è una versione di anteprima: i test locali non garantiscono compatibilità con ogni portale aziendale.
