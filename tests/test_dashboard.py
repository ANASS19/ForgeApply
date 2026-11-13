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
    store.set_setting('candidate_context',{'education':[{'degree':'Fixture MSc','completed':True,'thesis':'Preserve original thesis'}],
                                          'languages':{'Italian':'Beginner'},'skills':{'programming':['Python'],'planned':['LearningOnly']},
                                          'private_annotations':{'preserve':'untouched'}})
    store.add_job(title='Synthetic employer role',url='https://example.org/apply',origin_url='https://www.linkedin.com/jobs/view/fixture-123')
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
                from playwright.sync_api import expect
                expect(page.locator('#setupSummary')).to_contain_text('Profile ready')
                expect(page.get_by_role('link',name='Try Prepare & Fill',exact=False)).to_have_attribute('href','/demo/it')
                assert not page.locator('#moreTools').evaluate('e=>e.open')
                page.screenshot(path=str(tmp_path/'dashboard-start.png'),full_page=True)
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
                page.locator('#backgroundEditor [data-section=skills] > summary').click()
                page.locator('#verifiedSkills').fill('Python\nSQL')
                page.locator('#backgroundEditor [data-section=education] > summary').click()
                page.get_by_role('button',name='Add education',exact=True).click()
                page.get_by_label('Education 2 - School / university',exact=True).fill('Second University')
                page.get_by_label('Education 2 - Degree / field of study',exact=True).fill('Mathematics')
                page.get_by_label('Education 2 - Qualification completed',exact=True).check()
                page.locator('#backgroundEditor [data-section=certifications] > summary').click()
                page.get_by_role('button',name='Add certification',exact=True).click()
                page.get_by_label('Certifications 1 - Certification',exact=True).fill('Synthetic Certificate')
                page.get_by_label('Certifications 1 - Issuing organization',exact=True).fill('Example Institute')
                assert page.locator('#verifiedSkills').input_value()=='Python\nSQL'
                page.get_by_role('button',name='Save verified background',exact=True).click()
                expect(page.locator('#backgroundStatus')).to_contain_text('saved locally')
                background=httpx.get(f'http://127.0.0.1:{port}/api/candidate-context').json()
                assert background['education'][0]['thesis']=='Preserve original thesis'
                assert background['education'][1]['institution']=='Second University'
                assert background['certifications'][0]['name']=='Synthetic Certificate'
                assert background['private_annotations']=={'preserve':'untouched'}
                assert background['skills']['planned']==['LearningOnly']
                assert 'SQL' in background['skills']['additional']
                page.get_by_role('button',name='AI Settings',exact=True).click()
                page.wait_for_function("document.querySelector('#llmForm [name=model]').value!==''")
                assert not page.locator('[name=allow_remote]').is_checked()
                page.get_by_role('button',name='Job Queue',exact=True).click()
                expect(page.get_by_role('link',name='Source opportunity',exact=True)).to_have_attribute('href','https://www.linkedin.com/jobs/view/fixture-123')
                page.locator('#moreTools > summary').click()
                page.get_by_role('button',name='Browser Agent',exact=True).click()
                assert not page.locator('#useAI').is_checked()
                assert not page.locator('#allowResumeUpload').is_checked()
                page.screenshot(path=str(tmp_path/'dashboard.png'))
                page.get_by_role('button',name='Start',exact=True).click()
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                page.screenshot(path=str(tmp_path/'dashboard-mobile.png'),full_page=True)
                page.goto(f'http://127.0.0.1:{port}/demo/it')
                expect(page.locator('button[type=submit]')).to_be_disabled()
                assert not errors
            finally: browser.close()
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()
