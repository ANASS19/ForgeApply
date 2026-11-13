"""Actual HTTP server and Chromium UI regression, using synthetic candidate facts."""
import socket
import threading
import time

import httpx
from playwright.sync_api import sync_playwright
import uvicorn
from forgeapply.app import app
from forgeapply import store


def test_dashboard_saved_profile_context_and_safe_defaults(tmp_path):
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.org'})
    store.set_setting('candidate_context',{'education':[{'degree':'Fixture MSc','completed':True}],
                                          'languages':{'Italian':'Beginner'}})
    sock=socket.socket()
    sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}',wait_until='networkidle')
                page.get_by_role('button',name='Candidate & CVs',exact=True).click()
                page.wait_for_function("document.querySelector('#profileForm [name=first_name]').value==='Fixture'")
                assert page.locator('#profileForm [name=email]').input_value()=='fixture@example.org'
                page.wait_for_function("document.querySelector('#candidateContext').textContent.includes('Beginner')")
                for key in ('years_python','work_authorized','needs_sponsorship','notice_period','salary_expectation'):
                    assert page.locator(f'#profileForm [name={key}]').input_value()==''
                page.locator('#profileForm [name=city]').fill('Fixture City')
                page.get_by_role('button',name='Save profile',exact=True).click()
                page.wait_for_function("document.querySelector('#notice').textContent==='Profile saved'")
                assert httpx.get(f'http://127.0.0.1:{port}/api/profile').json()['city']=='Fixture City'
                page.get_by_role('button',name='AI Settings',exact=True).click()
                page.wait_for_function("document.querySelector('#llmForm [name=model]').value!==''")
                assert not page.locator('[name=allow_remote]').is_checked()
                page.get_by_role('button',name='Browser Agent',exact=True).click()
                assert not page.locator('#useAI').is_checked()
                assert not page.locator('#allowResumeUpload').is_checked()
                page.screenshot(path=str(tmp_path/'dashboard.png'))
                assert not errors
            finally: browser.close()
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()
