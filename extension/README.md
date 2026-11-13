# ForgeApply Chrome extension

A Manifest V3 extension sharing the existing local profile, screening answers, model configuration and tracker. No framework/build step or cloud service is required. It requests `activeTab`, `scripting`, `storage`, `sidePanel`, `contextMenus`, and loopback-only host access. It does not request cookies, passwords, all-site access, debugger permission or external messaging. Content code is injected only after an explicit UI action.

## Install and pair

1. Start ForgeApply with `.venv\Scripts\python.exe -m forgeapply`.
2. Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `C:\Projects\ForgeApply\extension`.
3. Open the local dashboard → AI Settings → Chrome extension pairing → **Generate pairing code**.
4. On the desired web page, click the ForgeApply toolbar button. Enter the one-time code and click **Pair extension**. The local backend port defaults to 8765; change it only if using another local ForgeApply port.
5. Check the connected model, profile status and available document filenames. Pin the toolbar button for convenience. Edge's unpacked installation is similar, but Edge UI behavior has not been independently verified.

Codes expire in five minutes and are single-use. The backend stores only token hashes. Extension tokens live in trusted-context-only `chrome.storage.local`, never the page or injected content script. Disconnect revokes the token when the backend is reachable; if offline, revoke the session later in the dashboard. Restarting the backend preserves pairs. Re-pairing the same extension rotates its token.

## Permitted employer form workflow

Click **Analyze current page**. Review the detected fields and job information. Confirm the site permits this assistance, then **Fill supported fields**. The shared deterministic mapper fills known values, verifies them and flags errors/unknowns. Saved answers and source details are shown. **Request AI proposals** is separate; proposals are displayed for review and never automatically written into the page. Remote inference requires the backend's separate explicit consent setting.

**Choose CV on page** opens the page's native file picker, where you select the document yourself. A content script cannot assign an arbitrary local path. The extension does not download the CV into the site or expose the whole document library. Inspect again to verify the chosen filename. Managed Playwright mode retains separately approved local-library uploads.

**Next / Review step** performs one recognized, unambiguous navigation action and checks for a state change. It does not repeatedly click a stalled control. Final submission, legal declarations, checkboxes/radios and unfamiliar custom controls remain manual in this extension version. Native text/email/tel/date, textarea, select, contenteditable and same-origin iframe fields are supported. Cross-origin frames without an explicit implementation are skipped and counted.

The side panel uses the same UI and can stay open while browsing. Changing tabs or destination resets the inspected state and site authorization; it never automatically inspects unrelated pages. Invoke the toolbar/context menu again when Chrome revokes `activeTab`. The context menu opens the assistant on an explicitly chosen page. Restricted browser pages are unsupported.

## LinkedIn-first manual assistance

On LinkedIn/Indeed, **no content script is injected** and native scraping, Easy Apply clicks, autofill and uploads are disabled. Save the current URL with a title/company/description you enter yourself. Use text matching, the verified-answer lookup and available CV filenames for manual application preparation. The answer lookup accepts one question typed/pasted by you; missing/legal facts remain unanswered. Duplicate URLs reuse the existing job. External employer opportunities can be imported separately with their original listing URL for traceability.

LinkedIn's official [prohibited software policy](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions) prohibits extensions that scrape or automate its site. Its [User Agreement](https://www.linkedin.com/legal/user-agreement) sets the relevant restrictions. [Apply Connect](https://learn.microsoft.com/en-us/linkedin/talent/apply-connect) is an ATS/LinkedIn partner integration; it is not an unrestricted applicant automation API. ForgeApply has no such partner authorization. These official integration paths were reviewed on 2026-11-13; no native automation is claimed.

## Security boundary

The authenticated `/api/extension/*` bridge exposes only status, narrow field plans, manual answer lookup, operator-supplied job import/matching and activity. It cannot invoke arbitrary managed-browser tools or read arbitrary local files. Origin/ID/token checks, explicit CORS, one-time pairing, dashboard-only revocation and same-origin protections for the normal API are tested. Candidate profile data stays in the backend; content code receives only values needed for the selected fill plan. The page can naturally see values intentionally filled into its own controls.

No extension source is exposed as a web-accessible resource, and webpage/content-script messages cannot request bridge privileges. Local OS users and already-privileged extensions are outside the loopback API's authentication threat model. Pairing is not a substitute for OS account security. Screenshots, profiles, tokens and private benchmark outputs must stay outside Git.

## Verification and limits

Real Chromium tests load the unpacked MV3 service worker and UI, pair against an actual local server, fill a served application, use the native file chooser, advance through multiple pages to final review, verify same-origin iframe filling, save/deduplicate jobs and revoke the pairing. Security/API tests reject bad origins/tokens, unauthorized controls, unapproved filling and restricted-site automation. The side-panel API configuration is checked; normal Chrome toolbar/side-panel placement and Edge still need an operator smoke test.

Greenhouse, Lever, Ashby, Workday and SmartRecruiters are recognized by the capability registry, with generic accessible-form assistance requiring operator authorization. This recognition is **not** proof of a verified employer ATS adapter or permission to automate that employer. No real employer submissions, account logins, CAPTCHA bypass or automated LinkedIn-native actions were tested or performed.

Official Chrome implementation references: [activeTab grants](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab), [Side Panel API](https://developer.chrome.com/docs/extensions/reference/api/sidePanel), and [extension network requests](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests).
