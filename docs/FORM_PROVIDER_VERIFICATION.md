# Form preparation and provider verification - 0.4.4

## Reproduced defects

- A visible password input alone caused the extension to classify the entire RoboForm all-fields practice page as a required sign-in. Both preparation modes stopped before filling a field.
- The practice page uses adjacent text columns with obfuscated input names. Those labels were invisible to the deterministic mapper. Adjacent-cell recognition now works in the extension and managed browser, without crossing ambiguous groups.
- The installed `qwen3-vl:8b` thinking build returned an empty final answer when Ollama constrained its output format. It generated a final answer without that constraint. A single local compatibility retry now removes the constraint, retains the schema in the prompt, and applies the same strict answer/reference validation. Thinking text is never used as an answer. The successful compatibility observation is cached for ten minutes without prompts or responses.
- Default empty answer editors were treated as user edits and concealed new AI proposals. Only actual edits now take precedence. A saved narrative was also incorrectly classified as a missing website option; it now returns as a reviewable draft.
- Ollama switching reset generation options. Those options are now preserved. A model inventory, synthetic response check and specific inference errors distinguish connectivity, authentication, missing models, output limits and model-load failures.

## Verified workflow

The actual unpacked MV3 extension runs both Prepare & Fill and Complete Application against a synthetic locally served form. It fills deterministic facts before inference, shows proposals with supporting facts, accepts one approved profile reference, rejects a proposed stack without remembering it, fills/remembers the user's replacement, and reuses both answers after a reload with AI off. Local retrieval makes relevant approved answers available as evidence for unfamiliar paraphrases. Material unknowns and sensitive declarations remain gated.

The same workflow extracts vacancy title/company/description, emphasizes only existing requested CV skills, generates a motivation letter for that role, and attaches both reviewed PDFs to separate selected controls. Existing documents are protected, and changing the vacancy invalidates attachment. General configured CVs are preserved. A selected file is not proof of server upload acceptance or final submission.

A separate visible Chromium smoke used the real [RoboForm practice page](https://www.roboform.com/filling-test-all-fields) with synthetic facts. It inspected 40 controls, verified 11 fills, reported no required login, and submitted nothing. This exercised the production DOM script and backend planner through an instrumented browser. It did not operate the user's existing Chrome toolbar grant; full extension UI evidence comes from loopback fixtures.

All five installed models (`qwen:0.5b`, `qwen:1.8b`, `qwen3-vl:8b`, `qwen3.5:4b`, `qwen3.5:9b`) passed a tiny synthetic JSON response check. Qwen-VL additionally returned a schema-valid nonempty grounded motivation-letter proposal using only synthetic evidence. These checks establish transport/format compatibility, not broad factual accuracy or equivalent model quality.

Hosted contract tests cover OpenAI, direct Anthropic Messages, DeepSeek and custom OpenAI-compatible endpoints, including authentication headers, image formats, output limits and consent gates. No live paid API was called. Implementations follow the official [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create), [DeepSeek API](https://api-docs.deepseek.com/) and [Ollama structured output API](https://docs.ollama.com/capabilities/structured-outputs).

The form/model phase full suite passed **128 tests** on Windows Python 3.13 (one existing Starlette/httpx deprecation warning), including actual Chromium MV3 workflows. Five JavaScript syntax checks, `pip check`, diff whitespace checks and a redacted Gitleaks source scan passed. The backend was restarted on loopback with version 0.4.4; protected profile/context/model/answers/jobs/pairing hashes were unchanged. Qwen-VL also passed a synthetic image tool-choice probe and the restarted backend response check.

## Run and reproduce

```powershell
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m forgeapply
```

Reload ForgeApply at `chrome://extensions` (do not remove it), verify version 0.4.4, close old panels, then invoke the toolbar on the application page and choose Keep open. Pairing should remain saved. Use Settings > Test current model and then Prepare & Fill / Complete Application.

Private QA evidence and backup live outside Git at `%USERPROFILE%\.forgeapply\qa\forms-044`.

## Remaining boundaries

The system still uses one bounded orchestrator, structured candidate facts and lexical retrieval of approved answers. It is not a measured multi-agent or vector-retrieval platform. Cross-origin frames, closed shadow roots and arbitrary screenshot-to-coordinate workflows remain unsupported. The cursor shown by the extension is a page overlay; managed Playwright has separate browser pointer tools. Local OCR requires Tesseract, which was not installed in this environment. Final submissions remain explicitly controlled and no live employer completion is claimed.

Next verification priority: a permissioned operator-led ATS workflow with current vacancy context, both tailored documents accepted by the website, screening review, and a preserved checkpoint through final review.


## OpenRouter integration - 2026-11-14

The subsequent full suite passed **152 tests** (baseline 128), one existing dependency deprecation warning, plus a repeated dashboard check after making remote consent visible. New contracts exercise model slugs/:free IDs, API-key isolation, JSON-schema/JSON-object/plain JSON modes, image handling, parameter rejection recovery, catalog outages, missing keys, credits, permissions, rate limits, upstream failures and HTTP-200 error objects. A real Chromium local form completes the planner/proposal/review/fill path through a mocked OpenRouter transport; unapproved proposals remain empty on the page.

The dashboard offers a native OpenRouter preset, public model autocomplete and advertised capabilities. A masked key can be placed in the backend environment for the current process without a restart. The key input clears after success or provider changes; no key is returned or stored in SQLite. Same-origin, expected-provider/configuration, malformed-input and consent tests pass. Key setup does not grant hosted inference consent.

Visible Chromium against the running local app loaded the live catalog (471 text models at this check), selected `google/gemma-4-31b-it:free`, displayed image/JSON capability hints, and passed a 390-pixel width check. No key was entered, settings were not saved, and no inference request was made. The catalog is not evidence of authenticated generation. The backend was restarted with this integration; profile/context/model/answers/jobs/pairing hashes matched the pre-restart backup. Its version remains 0.4.4; the existing extension protocol is unchanged.

Private evidence is under `%USERPROFILE%\.forgeapply\qa\openrouter`. The next required user step is entering a key locally and running **Test saved model (synthetic data)**. OpenRouter generation/account limits and per-model answer quality have not been live-verified. See [setup instructions](USAGE.md#use-openrouter).
