import json
import re
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from forgeapply import store
from forgeapply.app import app
from forgeapply.site_policy import capabilities
from examples.fixture_server import FixtureServer


IDENTIFIER='a'*32
ORIGIN='chrome-extension://'+IDENTIFIER


def paired(client):
    code=client.post('/api/extension/pairing-code').json()['code']
    response=client.post('/api/extension/pair',json={'extension_id':IDENTIFIER,'code':code},headers={'Origin':ORIGIN})
    assert response.status_code==200
    return {'Origin':ORIGIN,'X-ForgeApply-Extension':IDENTIFIER,'Authorization':'Bearer '+response.json()['token']},code


def test_pairing_scopes_rotation_revocation_and_cors():
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,code=paired(client)
        assert client.get('/api/extension/status',headers=headers).status_code==200
        assert client.get('/api/profile',headers=headers).status_code==403
        assert client.post('/api/browser/open',headers=headers,json={'url':'https://example.org'}).status_code==403
        assert client.post('/api/extension/pairing-code',headers=headers).status_code==403
        assert client.post('/api/extension/pair',json={'extension_id':IDENTIFIER,'code':code},headers={'Origin':ORIGIN}).status_code==401
        bad=headers|{'Origin':'https://evil.example'}
        assert client.get('/api/extension/status',headers=bad).status_code==403
        preflight=client.options('/api/extension/plan',headers={'Origin':ORIGIN,'Access-Control-Request-Method':'POST'})
        assert preflight.status_code==204 and preflight.headers['access-control-allow-origin']==ORIGIN
        assert client.options('/api/extension/plan',headers={'Origin':'https://evil.example'}).status_code==403
        assert client.get('/api/extension/status',headers={'Origin':ORIGIN,'X-ForgeApply-Extension':IDENTIFIER}).status_code==401
        assert client.delete('/api/extension/sessions/'+IDENTIFIER).status_code==200
        assert client.get('/api/extension/status',headers=headers).status_code==401


def test_shared_plans_never_invent_and_restricted_native_sites_stay_manual():
    store.save_profile({'first_name':'Fixture','city':'Milano'})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        fields=[{'index':0,'token':'first','label':'First name','required':True,'valid':False},
                {'index':1,'token':'visa','label':'Visa sponsorship','required':True,'valid':False},
                {'index':2,'token':'declaration','label':'I certify this declaration','type':'checkbox','required':True,'valid':False}]
        body={'url':'https://example.org/apply','snapshot_id':'snapshot','fields':fields,'site_authorized':True}
        result=client.post('/api/extension/plan',headers=headers,json=body).json()
        assert len(result['actions'])==1 and result['actions'][0]['value']=='Fixture'
        assert set(result['unknown'])=={'Visa sponsorship','I certify this declaration'}
        assert not result['proposals']
        assert client.post('/api/extension/plan',headers=headers,json=body|{'url':'https://www.linkedin.com/jobs/view/123'}).status_code==403
        assert client.post('/api/extension/plan',headers=headers,json=body|{'site_authorized':False}).status_code==403
        job={'url':'https://www.linkedin.com/jobs/view/123','title':'User supplied role','company':'Synthetic'}
        first=client.post('/api/extension/jobs',headers=headers,json=job).json()
        second=client.post('/api/extension/jobs',headers=headers,json=job).json()
        assert first['id']==second['id'] and first['created'] and not second['created']
        assert store.get_job(first['id'])['source']=='extension:linkedin'
        external=client.post('/api/extension/jobs',headers=headers,json={'url':'https://example.org/apply','title':'External role','origin_url':job['url']}).json()
        assert store.get_job(external['id'])['origin_url']==job['url']
        safe=client.post('/api/extension/answer',headers=headers,json={'question':'First name'}).json()
        unknown=client.post('/api/extension/answer',headers=headers,json={'question':'Visa sponsorship required?'}).json()
        assert safe['answer']=='Fixture' and safe['needs_review']
        assert unknown['answer']=='' and unknown['needs_information']


def test_platform_matching_uses_hostname_boundaries():
    assert capabilities('https://www.linkedin.com/jobs')['automation']=='manual_only'
    assert capabilities('https://linkedin.com.evil.example')['automation']!='manual_only'
    assert capabilities('https://jobs.lever.co/synthetic')['platform']=='lever'
    assert not capabilities('chrome://settings')['dom_inspection']
    assert capabilities('https://fr.indeed.fr/jobs')['automation']=='manual_only'


def test_bilingual_reviewed_answers_and_missing_facts():
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.test','phone':'123'})
    store.set_setting('candidate_context',{'education':[{'degree':'Computer Science','level':'masters','completed':True}],
                                          'skills':{'programming':['Python']}})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        fields=[{'index':i,'token':str(i),'label':label,'type':'text','checked':False,'required':True} for i,label in enumerate(
            ['Nome*Obbligatorio','Indirizzo*Obbligatorio','Lettera di motivazione*Obbligatorio','Quanti anni di esperienza con Python?*Obbligatorio','Accetto la privacy'])]
        body={'url':'https://example.test/apply','snapshot_id':'s','fields':fields,'site_authorized':True,'page_language':'it'}
        response=client.post('/api/extension/plan',headers=headers,json=body)
        assert response.status_code==200
        plan=response.json()
        assert len(plan['actions'])==1 and plan['actions'][0]['value']=='Fixture'
        drafts={d['index']:d for d in plan['drafts']}
        assert drafts[2]['language']=='it' and drafts[2]['value'].startswith('Gentile team')
        assert drafts[1]['value']==drafts[3]['value']=='' and 4 not in drafts
        reviewed=body|{'reviewed':True,'answers':[{'index':1,'token':'1','value':'Synthetic Street 1','remember':True}]}
        assert client.post('/api/extension/reviewed-plan',headers=headers,json=reviewed|{'reviewed':False}).status_code==403
        # Validate all references before remembering any part of an invalid batch.
        bad=reviewed|{'answers':reviewed['answers']+[{'index':4,'token':'4','value':'Yes'}]}
        assert client.post('/api/extension/reviewed-plan',headers=headers,json=bad).status_code==403
        assert not store.get_setting('profile').get('street_address')
        result=client.post('/api/extension/reviewed-plan',headers=headers,json=reviewed)
        assert result.status_code==200 and result.json()['remembered']==1
        assert store.get_setting('profile')['street_address']=='Synthetic Street 1'
        assert store.list_answers()[0]['source']=='user:extension-reviewed-exact'
        next_plan=client.post('/api/extension/plan',headers=headers,json=body).json()
        assert any(a['index']==1 and a['value']=='Synthetic Street 1' for a in next_plan['actions'])
        letter=client.post('/api/extension/motivation-letter',headers=headers,json={'language':'en','company':'Synthetic'}).json()
        assert letter['value'].startswith('Dear Hiring Team') and 'Synthetic' in letter['value']
        prefilled=reviewed|{'fields':[f|{'value':'Already answered'} if f['index']==1 else f for f in fields]}
        assert client.post('/api/extension/reviewed-plan',headers=headers,json=prefilled).status_code==409
        duplicate=body|{'fields':[fields[0],fields[0]]}
        assert client.post('/api/extension/plan',headers=headers,json=duplicate).status_code==400


def test_explicit_local_model_selection_preserves_configuration(monkeypatch):
    import forgeapply.extension_api as bridge
    previous={'provider':'openai','model':'existing-model','allow_remote':False,'base_url':'http://127.0.0.1:1234'}
    store.set_setting('llm',previous)
    monkeypatch.setattr(bridge,'local_models',lambda identifier:{'models':['fixture-local'],'available':True})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        assert store.get_setting('llm')==previous
        assert client.post('/api/extension/local-model',headers=headers,json={'model':'not-installed'}).status_code==400
        response=client.post('/api/extension/local-model',headers=headers,json={'model':'fixture-local'})
        assert response.status_code==200
        assert store.get_setting('llm')['model']=='fixture-local'
        assert not store.get_setting('llm')['allow_remote']
        assert store.get_setting('llm_selection_history')[-1]['settings']==previous


def test_document_drafts_and_reviewed_pdf_export_preserve_configured_cv():
    import base64
    from io import BytesIO
    from pypdf import PdfReader
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','resume_en':'existing-private-cv.pdf'})
    store.set_setting('candidate_context',{'education':[{'degree':'Computer Science','institution':'Università sintetica','completed':True}],
                                          'skills':{'programming':['Python']}})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        draft=client.post('/api/extension/cv-draft',headers=headers,json={'language':'it'}).json()
        assert draft['kind']=='cv' and 'FORMAZIONE' in draft['value'] and draft['needs_review']
        body={'text':draft['value']+'\n<script>literal text</script>','kind':'cv','reviewed':True}
        assert client.post('/api/extension/document-pdf',headers=headers,json=body|{'reviewed':False}).status_code==403
        response=client.post('/api/extension/document-pdf',headers=headers,json=body)
        assert response.status_code==200
        document=PdfReader(BytesIO(base64.b64decode(response.json()['base64'])))
        assert len(document.pages)==1
        text=document.pages[0].extract_text()
        assert 'Università sintetica' in text and '<script>literal text</script>' in text
        assert store.get_setting('profile')['resume_en']=='existing-private-cv.pdf'


@pytest.fixture
def extension_backend():
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        assert server.started
        yield port
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()
        assert not thread.is_alive()


def test_real_mv3_pair_inspect_fill_upload_next_and_revoke(tmp_path,extension_backend):
    extension=Path('extension').resolve()
    manifest=json.loads((extension/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['manifest_version']==3 and '<all_urls>' not in manifest.get('host_permissions',[])
    assert 'cookies' not in manifest['permissions'] and not manifest.get('content_scripts')
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.test','phone':'+39 351 000 0000','city':'Milano','country':'Italy','github':'https://example.test/source','portfolio':'https://example.test/projects'})
    store.upsert_answer('^Show follow-up$','true',source='user:explicit-fixture-preference')
    from forgeapply.candidate import screening_answers
    for answer in screening_answers(store.get_setting('profile'),{'education':[{'level':'masters','completed':True}],'languages':{'Italian':'Beginner'}}):
        store.upsert_answer(answer['pattern'],answer['answer'])
    with FixtureServer() as fixture, sync_playwright() as playwright:
        context=playwright.chromium.launch_persistent_context(str(tmp_path/'extension-profile'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            identifier=worker.url.split('/')[2]
            worker.evaluate('async()=>await chrome.storage.local.set({aiMode:false})')
            page=context.new_page();page.goto(fixture.url+'/apply')
            tab_id=worker.evaluate("async()=> (await chrome.tabs.query({})).find(t=>(t.url||'').includes('/apply')).id")
            panel=context.new_page();panel.goto(f'chrome-extension://{identifier}/panel.html?tab={tab_id}')
            expect(panel.locator('#site')).to_have_text(re.compile('^http'))
            assert not panel.locator('#fields').inner_text()
            code=httpx.post(f'http://127.0.0.1:{extension_backend}/api/extension/pairing-code').json()['code']
            panel.locator('#settingsToggle').click()
            panel.locator('#backendPort').fill(str(extension_backend));panel.locator('#pairCode').fill(code)
            panel.locator('#pair').click()
            expect(panel.locator('#connection')).to_contain_text('Connected locally')
            expect(panel.locator('#pairSetup')).to_be_hidden()
            panel.reload()
            expect(panel.locator('#connection')).to_contain_text('Connected locally')
            expect(panel.locator('#pairSetup')).to_be_hidden()
            assert panel.locator('#authorized').count()==0
            panel.locator('#fill').click()
            page.locator('[name=first_name]').wait_for()
            page.wait_for_function("document.querySelector('[name=first_name]').value==='Fixture'")
            expect(page.locator('[name=email]')).to_have_value('fixture@example.test')
            expect(panel.locator('#summary')).to_contain_text('fields verified')
            # Browser-native chooser: no arbitrary local path is assigned by the extension.
            cv=tmp_path/'synthetic.pdf';cv.write_bytes(b'%PDF-1.4\nsynthetic fixture\n%%EOF')
            with page.expect_file_chooser() as chooser:
                panel.locator('#chooseFile').click()
            chooser.value.set_files(str(cv))
            expect(panel.locator('#summary')).to_contain_text('CV selected')
            panel.locator('#next').click()
            page.get_by_role('heading',name='Screening details').wait_for()
            expect(panel.locator('#fields')).to_contain_text('Italian language proficiency')
            panel.locator('#fill').click()
            page.wait_for_function("document.querySelector('select').value==='Beginner'")
            panel.locator('#next').click()
            page.get_by_role('heading',name='Final review - controlled local fixture').wait_for()
            assert fixture.submissions==[]
            # No final submission control exists in the extension UI.
            assert not panel.get_by_role('button',name='Submit application',exact=True).count()
            panel.locator('#settingsToggle').click()
            panel.locator('#jobDetails > summary').click()
            panel.locator('#saveJob').click()
            expect(panel.locator('#summary')).to_contain_text('saved')
            assert store.list_jobs()[0]['source']=='extension:generic'
            page.goto(fixture.url+'/controls')
            expect(panel.locator('#site')).to_contain_text('/controls')
            assert not panel.locator('#fields').inner_text()  # Navigation never silently re-inspects.
            panel.locator('#fill').click()
            expect(page.frame_locator('iframe').get_by_label('GitHub')).to_have_value('https://example.test/source')
            expect(page.locator('#follow-up input')).to_have_value('https://example.test/projects')
            expect(panel.locator('#summary')).to_contain_text('fields verified')
            # The side-panel API is installed; no browser security flags are disabled.
            expect(panel.locator('#sidepanel')).to_be_visible()
            options=worker.evaluate('async()=>await chrome.sidePanel.getOptions({})')
            assert options['path']=='panel.html?sidepanel=1'
            # Full document navigation destroys the old injected JS context; recover by observing, never re-clicking.
            page.goto(fixture.url+'/navigation')
            expect(panel.locator('#site')).to_contain_text('/navigation')
            panel.locator('#fill').click()
            expect(panel.locator('#next')).to_be_enabled()
            panel.locator('#next').click()
            expect(page.locator('h1')).to_contain_text('esempio locale')
            expect(panel.locator('#summary')).to_contain_text('Next step opened')
            panel.locator('#fill').click()
            expect(page.locator('#nome')).to_have_value('Fixture')
            httpx.delete(f'http://127.0.0.1:{extension_backend}/api/extension/sessions/{identifier}').raise_for_status()
            panel.reload()
            expect(panel.locator('#error')).to_contain_text('revoked')
            assert fixture.submissions==[]
        finally: context.close()


def test_real_mv3_italian_form_letters_review_missing_answers_and_stale_state(tmp_path,extension_backend):
    extension=Path('extension').resolve()
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.test','phone':'+39 351 000 0000','country':'Italy'})
    store.set_setting('candidate_context',{'education':[{'degree':'Computer Science','level':'masters','completed':True}],
                                          'skills':{'programming':['Python','SQL']},'languages':{'English':'Advanced / C1'}})
    with FixtureServer() as fixture,sync_playwright() as playwright:
        context=playwright.chromium.launch_persistent_context(str(tmp_path/'profile'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            identifier=worker.url.split('/')[2]
            worker.evaluate('async()=>await chrome.storage.local.set({aiMode:false})')
            page=context.new_page();page.goto(fixture.url+'/italian')
            tab_id=worker.evaluate("async()=> (await chrome.tabs.query({})).find(t=>(t.url||'').includes('/italian')).id")
            panel=context.new_page();panel.goto(f'chrome-extension://{identifier}/panel.html?tab={tab_id}')
            errors=[];panel.on('pageerror',lambda e:errors.append(str(e)))
            code=httpx.post(f'http://127.0.0.1:{extension_backend}/api/extension/pairing-code').json()['code']
            panel.locator('#settingsToggle').click();panel.locator('#backendPort').fill(str(extension_backend))
            panel.locator('#pairCode').fill(code);panel.locator('#pair').click()
            expect(panel.locator('#connection')).to_contain_text('Connected locally')
            panel.locator('#settingsToggle').click()
            panel.locator('#fill').click()
            expect(page.locator('#nome')).to_have_value('Fixture')
            expect(page.locator('#cognome')).to_have_value('Candidate')
            expect(page.locator('#email')).to_have_value('fixture@example.test')
            expect(page.locator('#telefono')).to_have_value('+39 351 000 0000')
            expect(panel.locator('#summary')).to_contain_text('7 fields verified')
            expect(page.locator('[name=english][value=C1]')).to_be_checked()
            expect(page.locator('#country')).to_have_value('it')
            expect(page.locator('#skill_python')).to_be_checked()
            expect(page.locator('#skill_unknown')).not_to_be_checked()
            expect(panel.locator('#reviewArea')).to_be_visible()
            motivation=panel.get_by_label('Lettera di motivazione',exact=True)
            expect(motivation).to_have_value(re.compile('^Gentile team'))
            expect(page.locator('#motivation')).to_have_value('')
            expect(page.locator('#python_years')).to_have_value('')
            panel.get_by_label('Indirizzo',exact=True).fill('Synthetic Street 7')
            # Page-side edit after inspection must survive the reviewed fill attempt.
            page.locator('#motivation').fill('My manual text')
            panel.locator('#applyReviewed').click()
            expect(panel.locator('#error')).to_contain_text('modified this field')
            expect(page.locator('#motivation')).to_have_value('My manual text')
            expect(page.locator('#address')).to_have_value('Synthetic Street 7')
            expect(page.locator('#privacy')).not_to_be_checked()
            assert store.get_setting('profile')['street_address']=='Synthetic Street 7'
            page.locator('#motivation').fill('')
            panel.locator('#fill').click()
            expect(panel.get_by_label('Lettera di motivazione',exact=True)).to_have_value(re.compile('^Gentile team'))
            panel.locator('#applyReviewed').click()
            expect(page.locator('#motivation')).to_have_value(re.compile('^Gentile team'))
            panel.locator('#language').select_option('en')
            panel.locator('#letter').click()
            expect(panel.locator('#letterText')).to_have_value(re.compile('^Dear Hiring Team'))
            panel.locator('#cv').click()
            expect(panel.locator('#letterHeading')).to_have_text('Curriculum Vitae')
            expect(panel.locator('#letterText')).to_have_value(re.compile('Computer Science'))
            with panel.expect_download() as download:
                panel.locator('#downloadPDF').click()
            path=tmp_path/'reviewed-synthetic-cv.pdf';download.value.save_as(str(path))
            from pypdf import PdfReader
            assert 'Fixture Candidate' in PdfReader(path).pages[0].extract_text()
            assert panel.locator('#next').is_hidden() # Italian final submission is never navigation.
            assert not errors and fixture.submissions==[]
            panel.screenshot(path=str(tmp_path/'italian-panel.png'),full_page=True)
        finally: context.close()
