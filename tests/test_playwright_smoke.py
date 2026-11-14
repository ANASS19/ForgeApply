"""Chromium form detection, fill, and screenshot smoke test."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from forgeapply.browser import FIELD_SCRIPT
from examples.fixture_server import FixtureServer


def test_extension_login_detection_and_adjacent_label_boundaries():
    script=Path('extension/content.js').read_text(encoding='utf-8')
    cases=[
        ('<form><label>Email<input type=email></label><label>Password<input type=password></label><button>Sign in</button></form>',True),
        ('<form><input autocomplete=username><input type=password autocomplete=current-password></form>',True),
        ('<form><label>Nome utente<input></label><input type=password><button>Accedi</button></form>',True),
        ('<form><label>First Name<input></label><label>Email<input type=email></label><input type=password><button>Create account</button></form>',False),
        ('<form><input type=password autocomplete=new-password><button>Sign in</button></form>',False),
        ('<form><input type=password></form>',False),
        ('<form><input type=password disabled><button>Sign in</button></form>',False),
        ('<form><input type=password style="display:none"><button>Sign in</button></form>',False),
        ('<form><input type=password><input type=password><button>Reset password</button></form>',False),
        ('<iframe srcdoc="&lt;label&gt;Password&lt;input type=password&gt;&lt;/label&gt;&lt;button&gt;Sign in&lt;/button&gt;"></iframe>',True),
    ]
    with FixtureServer() as fixture,sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            page=browser.new_page();page.goto(fixture.url)
            for html,expected in cases:
                page.set_content(html);page.evaluate(script)
                assert page.evaluate('ForgeApplyPage.inspect().needs_login') is expected,html
            page.set_content('<table><tr><td>First Name</td><td><input id=table></td></tr></table>'
                             '<div><div>City</div><div><input id=ambiguous><input></div></div>'
                             '<div><div>Wrong label</div><div><label for=explicit>Last Name</label><input id=explicit></div></div>')
            page.evaluate(script)
            fields={f['id']:f['label'] for f in page.evaluate('ForgeApplyPage.inspect().fields')}
            assert fields['table']=='First Name' and fields['ambiguous']=='' and fields['explicit']=='Last Name'
            managed={f['id']:f['label'] for f in page.evaluate(FIELD_SCRIPT)}
            assert managed['table']=='First Name' and managed['ambiguous']=='' and managed['explicit']=='Last Name'
        finally:browser.close()


def test_playwright_chromium_form_and_screenshot(tmp_path):
    with sync_playwright() as playwright:
        binary = Path(playwright.chromium.executable_path)
        if not binary.is_file():
            pytest.skip('Install Chromium with python -m playwright install chromium')
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content('<html><body><label for="email">Email address</label>'
                             '<input id="email" type="email" required>'
                             '<button type="button">Next</button></body></html>')
            fields = page.evaluate(FIELD_SCRIPT)
            assert len(fields) == 1
            assert fields[0]['required'] is True
            assert fields[0]['label'] == 'Email address'
            page.locator('#email').fill('candidate@example.org')
            assert page.locator('#email').input_value() == 'candidate@example.org'
            screenshot = tmp_path / 'form.png'
            page.screenshot(path=str(screenshot))
            assert screenshot.read_bytes().startswith(b'\x89PNG')
        finally:
            browser.close()
