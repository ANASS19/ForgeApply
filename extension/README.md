# ForgeApply Chrome extension

A local-first Manifest V3 assistant using the existing profile, answers, model settings and tracker. No build step is required.

## Start in three steps

1. Run `.venv\Scripts\python.exe -m forgeapply`, open `http://127.0.0.1:8765`, and confirm **Candidate & CVs**.
2. At `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `C:\Projects\ForgeApply\extension`. For updates, use **Reload**, not Remove.
3. In dashboard **AI Settings**, generate a connection code and enter it once. Codes expire after five minutes and are single-use. The resulting connection has **no automatic expiry** and survives browser/backend restarts until disconnected or revoked. The code box disappears after connection.

Click **Keep open** at the top for Chrome's persistent side panel. Infrequent tools live under **More options**. If the background worker or backend runs an older build, the panel explains which component needs reloading; pairing stays saved. Edge's unpacked install is similar, but its UI has not been independently verified.

## Prepare and fill

Version 0.4.2 adds **Complete Application**, a bounded multi-step executor. It observes, selects a validated tool, acts and verifies, then observes again. Pause/Stop preserve page entries; Chrome/backend checkpoints support explicit resume after interruption. It stops for missing facts, file selection, required legal/personal review, server errors and final review. Limits are 80 steps, three minutes and three model requests. Closing the panel interrupts execution; it does not keep running invisibly. See [the usage guide](../docs/USAGE.md#complete-supported-steps).

The cyan cursor is a visual page overlay. Agent actions show section/row/label and verification outcomes. Optional screenshot reasoning defaults off and only sends the active authorized tab to the configured model after enabling it; hosted inference still requires remote consent. Screenshots are resized, and model tool choices remain tied to offered DOM targets. No arbitrary scripts, coordinates or OS mouse control are exposed.

On a permitted employer form, click **Prepare & Fill**. This explicit action inspects the selected page, fills verified facts, and shows editable cards for missing information and longer answers. There is no separate site-permission checkbox. Website policies and the manual final submission remain enforced.

English/Italian labels, including `Nome*Obbligatorio`, and common Workday labels such as `Given Name(s)`, `Family Name`, `Address Line 1` and `Country/Territory` share the deterministic mapper. Native selects, accessible custom dropdowns, searchable comboboxes, radio groups, factual skill checkboxes and same-origin frames are supported. Choices must uniquely match explicit facts; a beginner language level is never guessed into a CEFR level. Existing values and changed controls are protected.

Enter a missing answer and choose **Fill reviewed answers**. Verified personal answers are remembered locally by default with provenance. Recognized contact, address, postal, province and experience-year facts can be reused across English/Italian labels. Repeated-record answers stay attached to their education/employment record. Motivation letters and job-referral sources are not promoted to global personal facts. Privacy/legal declarations and protected demographic questions stay manual.

Optional unanswered controls are grouped in a collapsed list. Required answers remain visible. Italian portal labels such as `Via/Piazza`, `Canale` and separate `Prefisso` controls have regression coverage. Referral answers are saved for the application URL, and prior-employer questions remain employer-specific. Phone types are not inferred from the number. Review existing birthplace/nationality defaults on the website: the extension does not regard them as verified facts. Birth answers entered for a form are not saved as reusable screening answers.

**Attach CV / document** opens the native file picker and verifies the filename. The extension cannot assign arbitrary local paths. **Continue to next step** performs one recognized navigation action, including `Save and Continue` / `Salva e continua`, checks validation, and observes fresh state. Full document navigation recovers without clicking twice. Use Prepare & Fill on each new step. Login, CAPTCHA and final submission remain user controlled.

Changing tabs/destination clears inspected state. Unrelated pages are never inspected automatically. Invoke the toolbar/context menu again when Chrome revokes activeTab access. Browser/internal pages and cross-origin frames are unsupported.

## Workday-style multi-page workflows

The controlled `/workday?lang=en` and `/workday?lang=it` fixtures cover five stages: personal information, experience/education, application questions, voluntary disclosures and review. Recognized repeated sections can add up to ten verified records per section, then re-inspect before filling. Existing rows match by employer/title or institution; ambiguous or unknown history blocks automatic expansion. Exact dates are required; start months and ongoing employment are not inferred.

Use `/workday?actual=1&catalog=1&lang=it` (or `lang=en`) for the stricter regression fixture. It requires Enter-triggered university/discipline lookups, real committed tokens, virtualized degree/language menus and skills chips. It also verifies education year IDs, language Overall, explicit fluency, rejected oversized CVs and an accepted-file indicator. Ambiguous choices stop; replaced controls are re-observed once. [Evidence and limitations](../docs/WORKDAY_VERIFICATION.md).

Repeated employment, education, certifications and languages are supported in these fixtures, including real Workday-style dynamic input IDs without dedicated record wrappers. Split month/year fields, searchable city choices, read-only dropdowns and skills tags are verified. Known fields revealed during filling receive bounded re-observation and another pass; failed or ambiguous choices remain for review. There is a 100-control inspection limit, and Next is blocked when a page exceeds it. Structured background records can be edited in Candidate & CVs; unverified records, incomplete degrees and planned skills are excluded from automatic filling.

Public employer portals confirmed on 2026-11-13 include the owner-supplied Accenture Workday URL, [PwC Milan](https://pwc.wd3.myworkdayjobs.com/en-US/Global_Campus_Careers/job/Accounting---Associate---Milano--DIG-_766500WD), and [ING Italy](https://ing.wd3.myworkdayjobs.com/it-IT/ICSGBLCOR/job/Financial-Crime-Compliance-Senior-Specialist_REQ-10115473). These examples identify the platform, not candidate suitability or verified live automation. Authenticated Accenture pages beyond the supplied screenshots were unavailable to the development browser. Repeat-container variants, date pickers, nested/virtualized menus and tenant-specific questions still need live verification. This is **not universal Workday compatibility**.

## AI and documents

Known facts fill directly. Configured AI is enabled for unfamiliar prose by default and can be disabled under More options. Exact missing dates/years/addresses, employer-history negatives and sensitive questions are not guessed by AI. Local Ollama or explicitly opted-in hosted-compatible providers use strict schemas, valid field references and supplied evidence IDs. Citations do not prove semantic truth; model text always requires review. Outages retain manual answer cards and factual document drafts.

**Draft CV** and **Motivation letter** create editable English/Italian documents from verified context, including verified certifications in CV drafts. The model can refine/translate wording; deterministic drafts are the fallback. Review the text, then choose **Reviewed - download PDF**, or plain text. PDF rendering stays local and escapes markup. Downloads do not replace configured CVs: explicitly save a reviewed document under Candidate & CVs if desired. Uncertain employment, incomplete degrees and planned/learning-only skills are excluded. Comprehensive factual-conflict handling remains limited.

For unfamiliar contact labels, AI can propose a reference to a specific existing profile fact. The server copies that fact rather than accepting invented contact data. Review is required before use. Approved mappings remember the field and website, follow later profile edits, and stop if the referenced fact is cleared. This is an assisted mapping mechanism, not proof that any model understands every form.

For safe practice without another server, open `/demo/it` or `/demo/en` from the dashboard Start page; final submit controls are disabled. For the five-stage fixture, run `.venv\Scripts\python.exe -m examples.fixture_server --port 8766`, then open `http://127.0.0.1:8766/workday?lang=it`.

The same fixture server serves `/italian-portal`, a synthetic Italian enterprise form reconstructed from control metadata. It includes source/prior-employer/phone-type choices, separate calling codes, address, personal fields, review, and no automatic submission. It does not contact an employer.

## Restricted platforms

LinkedIn/Indeed native inspection, scraping, Easy Apply automation, autofill and uploads are disabled. Import the current URL with manually supplied title/company/description, match verified skills, draft documents, or look up one pasted question. Duplicate URLs reuse existing jobs; external employer opportunities retain their original source URL.

LinkedIn's [prohibited software policy](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions) and [User Agreement](https://www.linkedin.com/legal/user-agreement) define its restrictions. [Apply Connect](https://learn.microsoft.com/en-us/linkedin/talent/apply-connect) is a partner integration, not an unrestricted applicant API. ForgeApply has no partner authorization. No native LinkedIn automation is claimed.

## Security and verification

Permissions are activeTab, scripting, storage, sidePanel, contextMenus and loopback-only host access. There are no cookie, debugger or all-site permissions, external messages, automatic content scripts or web-accessible resources. Only the extension UI can request bridge privileges. Backend pairing stores token hashes; Chrome keeps the token in trusted-context-only local storage. Re-pairing rotates it. Offline Disconnect removes the local token; revoke the backend session from the dashboard when it is reachable.

The authenticated bridge exposes preparation/review plans, local document drafts/PDF export, explicit installed-model selection, answer lookup, job import/matching and activity. It cannot read arbitrary local files or execute managed-browser commands. Origin/ID/token checks, scoped CORS and dashboard-only revocation are tested. Candidate facts stay in the backend; content code receives values selected for this form. Recent control labels/types/automation IDs are retained locally for debugging; entered values and record identities are excluded. Dashboard-only `/api/extension/control-diagnostics` is unavailable to extension origins. OS account security remains necessary.

Real Chromium tests load the actual unpacked worker/UI, pair with an actual local FastAPI server, fill served forms, choose a CV, traverse multiple stages and full document navigation, handle same-origin frames and stale edits, export reviewed PDFs, preserve pairing, and revoke access. The bilingual Workday-style fixtures include repeated records, custom/search dropdowns, missing-choice handoff, validation and final review. No real employer submission, CAPTCHA bypass or account creation was performed. Normal Chrome side-panel placement, authenticated employer flows, hosted inference and additional ATS variants need operator verification.

Chrome references: [activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab), [Side Panel API](https://developer.chrome.com/docs/extensions/reference/api/sidePanel), [network requests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests).
