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
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.test','phone':'+39 351 000 0000','city':'Milano','country':'Italy','github':'https://example.test/source'})
    from forgeapply.candidate import screening_answers
    for answer in screening_answers(store.get_setting('profile'),{'education':[{'level':'masters','completed':True}],'languages':{'Italian':'Beginner'}}):
        store.upsert_answer(answer['pattern'],answer['answer'])
    with FixtureServer() as fixture, sync_playwright() as playwright:
        context=playwright.chromium.launch_persistent_context(str(tmp_path/'extension-profile'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            identifier=worker.url.split('/')[2]
            page=context.new_page();page.goto(fixture.url+'/apply')
            tab_id=worker.evaluate("async()=> (await chrome.tabs.query({})).find(t=>(t.url||'').includes('/apply')).id")
            panel=context.new_page();panel.goto(f'chrome-extension://{identifier}/panel.html?tab={tab_id}')
            expect(panel.locator('#site')).to_have_text(re.compile('^http'))
            assert not panel.locator('#fields').inner_text()
            code=httpx.post(f'http://127.0.0.1:{extension_backend}/api/extension/pairing-code').json()['code']
            panel.locator('#backendPort').fill(str(extension_backend));panel.locator('#pairCode').fill(code)
            panel.locator('#pair').click()
            expect(panel.locator('#connection')).to_contain_text('Connected locally')
            panel.locator('#analyze').click()
            expect(panel.locator('#fields')).to_contain_text('First name')
            panel.locator('#authorized').check();panel.locator('#fill').click()
            page.locator('[name=first_name]').wait_for()
            page.wait_for_function("document.querySelector('[name=first_name]').value==='Fixture'")
            expect(page.locator('[name=email]')).to_have_value('fixture@example.test')
            expect(panel.locator('#summary')).to_contain_text('fields verified')
            # Browser-native chooser: no arbitrary local path is assigned by the extension.
            cv=tmp_path/'synthetic.pdf';cv.write_bytes(b'%PDF-1.4\nsynthetic fixture\n%%EOF')
            with page.expect_file_chooser() as chooser:
                panel.locator('#chooseFile').click()
            chooser.value.set_files(str(cv))
            panel.locator('#analyze').click()
            expect(panel.locator('#fields')).to_contain_text('Resume')
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
            panel.locator('#saveJob').click()
            expect(panel.locator('#summary')).to_contain_text('saved')
            assert store.list_jobs()[0]['source']=='extension:generic'
            page.goto(fixture.url+'/controls')
            expect(panel.locator('#site')).to_contain_text('/controls')
            assert not panel.locator('#fields').inner_text()  # Navigation never silently re-inspects.
            panel.locator('#analyze').click()
            expect(panel.locator('#fields')).to_contain_text('GitHub')
            panel.locator('#authorized').check();panel.locator('#fill').click()
            expect(page.frame_locator('iframe').get_by_label('GitHub')).to_have_value('https://example.test/source')
            expect(panel.locator('#summary')).to_contain_text('fields verified')
            # The side-panel API is installed; no browser security flags are disabled.
            options=worker.evaluate('async()=>await chrome.sidePanel.getOptions({})')
            assert options['path']=='panel.html?sidepanel=1'
            httpx.delete(f'http://127.0.0.1:{extension_backend}/api/extension/sessions/{identifier}').raise_for_status()
            panel.reload()
            expect(panel.locator('#error')).to_contain_text('revoked')
            assert fixture.submissions==[]
        finally: context.close()
