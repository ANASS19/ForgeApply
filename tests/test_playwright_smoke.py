"""Chromium form detection, fill, and screenshot smoke test."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from forgeapply.browser import FIELD_SCRIPT


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
