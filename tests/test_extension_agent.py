"""Bounded extension agent, actual MV3 messaging and synthetic Chromium applications."""
import json
import base64
import re
import time
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect
from forgeapply import store
from forgeapply.app import app
from forgeapply.llm import DecisionModel,LLMError
from examples.fixture_server import FixtureServer
from tests.test_extension import paired,extension_backend


def test_typed_model_tool_choice_and_private_run_history(monkeypatch):
    candidates=[{'id':0,'tool':'fill','label':'First name'}]
    model=DecisionModel()
    monkeypatch.setattr(model,'json',lambda *a,**k:{'candidate_id':4,'reason':'Invented target'})
    with pytest.raises(LLMError):model.choose_browser_step(candidates,'My Information')
    monkeypatch.setattr(DecisionModel,'choose_browser_step',lambda *a,**k:{'candidate_id':0,'reason':'Use the offered verified action'})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        body={'url':'https://example.test/apply?secret=private','stage':'My Information','use_ai':True,'candidates':candidates}
        assert client.post('/api/extension/agent/decision',headers=headers,json=body).json()['source']=='model'
        assert client.post('/api/extension/agent/decision',headers=headers,json=body|{'screenshot':'invalid image'}).status_code==400
        assert client.post('/api/extension/agent/decision',headers=headers,json=body|{'candidates':[{'id':0,'tool':'execute_script','label':'Forbidden'}]}).status_code==422
        run={'id':'a'*8+'-'+'b'*4+'-'+'c'*4+'-'+'d'*4+'-'+'e'*12,'tab_id':4,'url':body['url'],
             'status':'paused','steps':2,'verified':1,'model_calls':1,'elapsed_ms':1000,
             'events':[{'tool':'fill','label':'First name','outcome':'verified'}]}
        assert client.post('/api/extension/agent/run',headers=headers,json=run).status_code==200
        history=client.get('/api/extension/agent/run',headers=headers).json()
        assert history[0]['url']=='https://example.test/apply' and 'private' not in str(history)
        assert client.post('/api/extension/agent/run',headers=headers,json=run|{'status':'submitted'}).status_code==422
        assert client.post('/api/extension/agent/run',headers=headers,json=run|{'url':'https://www.linkedin.com/jobs/1'}).status_code==403
        assert client.get('/api/extension/agent/run',headers={'Origin':'https://evil.example'}).status_code==403


@pytest.mark.parametrize('language',['en','it'])
def test_real_agent_catalog_pause_resume_upload_and_final_review(tmp_path,extension_backend,language):
    store.save_profile({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.test','phone':'+39 351 000 0000',
                        'street_address':'Synthetic Street 7','postal_code':'20100','city':'Milano','province':'MI','country':'Italy'})
    store.set_setting('candidate_context',{
        'experience':[{'title':'Developer','employer':'First Company','start':'2022-06','end':'2023-12'}],
        'education':[{'institution':'First University','degree':'Computer Science','level':'masters','completed':True,'start':'2022-10','graduated_at':'2025-10','grade':'97/110'}],
        'languages':{'English':'Advanced / C1','French':'Fluent'},'skills':{'programming':['Python','SQL']}})
    extension=Path('extension').resolve();started=time.perf_counter()
    with FixtureServer() as fixture,sync_playwright() as playwright:
        url=fixture.url+'/workday?actual=1&catalog=1&lang='+language
        source='How Did You Hear About Us?' if language=='en' else 'Come ci hai conosciuto?'
        previous='Have you ever worked for Synthetic Employer?' if language=='en' else 'Hai mai lavorato per Synthetic Employer?'
        store.set_setting('application_specific_answers',{store.normalized_url(url):[{'pattern':'^'+re.escape(source)+'$','answer':'Company careers site','enabled':True}]})
        store.upsert_answer('^'+re.escape(previous)+'$','No',source='user:synthetic-confirmed')
        context=playwright.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            identifier=worker.url.split('/')[2];worker.evaluate('async()=>await chrome.storage.local.set({aiMode:false})')
            page=context.new_page();page.goto(url)
            tab_id=worker.evaluate("async()=> (await chrome.tabs.query({})).find(t=>(t.url||'').includes('/workday')).id")
            worker.evaluate('async id=>await chrome.storage.session.set({requestedTab:id})',tab_id)
            panel=context.new_page();panel.goto(f'chrome-extension://{identifier}/panel.html?sidepanel=1')
            errors=[];panel.on('pageerror',lambda error:errors.append(str(error)));page.on('pageerror',lambda error:errors.append(str(error)))
            code=httpx.post(f'http://127.0.0.1:{extension_backend}/api/extension/pairing-code').json()['code']
            panel.locator('#settingsToggle').click();panel.locator('#backendPort').fill(str(extension_backend))
            panel.locator('#pairCode').fill(code);panel.locator('#pair').click();expect(panel.locator('#connection')).to_contain_text('Connected locally')
            panel.locator('#settingsToggle').click();panel.locator('#runAgent').click()
            expect(panel.locator('#agentPause')).to_be_enabled();panel.locator('#agentPause').click()
            expect(panel.locator('#agentGoal')).to_contain_text('paused',timeout=15000)
            checkpoint=panel.evaluate("async()=> (await chrome.storage.local.get('agentCheckpoint')).agentCheckpoint")
            panel.reload();expect(panel.locator('#runAgent')).to_have_text('Resume application')
            panel.locator('#runAgent').click()
            expect(panel.locator('#agentGoal')).to_contain_text('human review',timeout=45000)
            expect(page.locator('[data-test-row^=education-] [data-automation-id=selectedItem]').first).to_have_text('First University')
            expect(page.locator('[id$="--degree"]')).to_have_text('Master Degree')
            expect(page.locator('[name=gpa1]')).to_have_value('')
            expect(page.locator('#skillChips [data-automation-id=selectedItem]')).to_have_text(['Python','SQL'])
            assert page.locator('[data-test-row^=workExperience-]').count()==1
            assert page.locator('#forgeapply-cursor').count()==1
            cv=tmp_path/'synthetic.pdf';cv.write_bytes(b'%PDF-1.4\nSynthetic\n%%EOF')
            with page.expect_file_chooser() as chooser:panel.locator('#chooseFile').click()
            chooser.value.set_files(str(cv));expect(page.locator('#uploadStatus')).to_contain_text('Upload accepted')
            panel.locator('#runAgent').click()
            expect(page.locator('[name=motivation]')).to_be_visible(timeout=15000)
            expect(panel.locator('#agentGoal')).to_contain_text('human review')
            question='Years of Python experience' if language=='en' else 'Anni di esperienza con Python'
            panel.get_by_label(question,exact=True).fill('3');panel.locator('#applyReviewed').click()
            expect(page.locator('[name=motivation]')).to_have_value(re.compile('^Dear Hiring Team' if language=='en' else '^Gentile team'))
            panel.locator('#runAgent').click();expect(page.locator('[name=privacy]')).to_be_visible(timeout=15000)
            expect(panel.locator('#agentGoal')).to_contain_text('human review');expect(page.locator('[name=privacy]')).not_to_be_checked()
            page.locator('[name=privacy]').check();panel.locator('#runAgent').click()
            expect(panel.locator('#agentGoal')).to_contain_text('review ready',timeout=15000)
            history=panel.evaluate("async()=>await send('agent_history')")
            assert len(history)==1 and history[0]['id']==checkpoint['run']['id']
            assert history[0]['status']=='review_ready' and history[0]['model_calls']==0
            assert history[0]['steps']<=80 and history[0]['verified']>20
            assert page.evaluate('saves')==4 and not fixture.submissions and not errors
            page.set_viewport_size({'width':1600,'height':900});panel.set_viewport_size({'width':390,'height':900})
            assert panel.evaluate('document.documentElement.scrollWidth<=innerWidth')
            image=page.screenshot(path=str(tmp_path/'final-review.png'),full_page=True)
            panel.screenshot(path=str(tmp_path/'agent-panel.png'),full_page=True)
            (tmp_path/'evidence.json').write_text(json.dumps({'language':language,'status':history[0]['status'],
                'steps':history[0]['steps'],'verified':history[0]['verified'],'model_calls':0,'submissions':0,
                'elapsed_seconds':round(time.perf_counter()-started,3)}),encoding='utf-8')
            # Real tab activation during a mocked capture must discard the image, not expose another tab.
            page.bring_to_front()
            preview=worker.evaluate("""async data=>{const capture=chrome.tabs.captureVisibleTab;chrome.tabs.captureVisibleTab=async()=>data.image;
              try{const result=await captureCurrentTab(data.id);const raw=atob(result.url.split(',')[1]);const bitmap=await createImageBitmap(new Blob([Uint8Array.from(raw,c=>c.charCodeAt(0))],{type:'image/jpeg'}));const width=bitmap.width;bitmap.close();return {width,jpeg:result.url.startsWith('data:image/jpeg;base64,')};}
              finally{chrome.tabs.captureVisibleTab=capture;}}
            """,{'id':tab_id,'image':'data:image/png;base64,'+base64.b64encode(image).decode()})
            assert preview['jpeg'] and preview['width']==1280
            race=worker.evaluate("""async id=>{const capture=chrome.tabs.captureVisibleTab;let other;
              chrome.tabs.captureVisibleTab=async()=>{other=await chrome.tabs.create({url:'about:blank',active:true});return 'data:image/jpeg;base64,/9j/';};
              try{await captureCurrentTab(id);return 'UNSAFE';}catch(error){return error.message;}
              finally{chrome.tabs.captureVisibleTab=capture;if(other)await chrome.tabs.remove(other.id);}}
            """,tab_id)
            assert 'Image discarded' in race
        finally:context.close()


@pytest.mark.parametrize('variant',['ambiguous','rerender','site_error','review'])
def test_actual_extension_stops_or_recovers_without_guessing(tmp_path,extension_backend,variant):
    store.set_setting('candidate_context',{'education':[{'institution':'First University','degree':'Computer Science',
        'completed':True,'level':'masters','start':'2022-10','graduated_at':'2025-10'}]})
    extension=Path('extension').resolve()
    with FixtureServer() as fixture,sync_playwright() as playwright:
        context=playwright.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            identifier=worker.url.split('/')[2];worker.evaluate('async()=>await chrome.storage.local.set({aiMode:false})')
            page=context.new_page();page.goto(fixture.url+'/workday?actual=1&catalog=1&'+variant+'=1')
            page.evaluate('step=1;show()') # Fixture-only setup, never an employer page.
            if variant=='review':page.evaluate("step=4;show();document.querySelector('[aria-current=step]').textContent='current step 5 of 5Review'")
            if variant=='site_error':page.evaluate("document.querySelector('main').insertAdjacentHTML('afterbegin','<p role=alert>Page Error: temporary server failure</p>')")
            tab_id=worker.evaluate("async()=> (await chrome.tabs.query({})).find(t=>(t.url||'').includes('/workday')).id")
            panel=context.new_page();panel.goto(f'chrome-extension://{identifier}/panel.html?tab={tab_id}')
            code=httpx.post(f'http://127.0.0.1:{extension_backend}/api/extension/pairing-code').json()['code']
            panel.locator('#settingsToggle').click();panel.locator('#backendPort').fill(str(extension_backend))
            panel.locator('#pairCode').fill(code);panel.locator('#pair').click();expect(panel.locator('#connection')).to_contain_text('Connected locally')
            panel.locator('#settingsToggle').click();panel.locator('#runAgent').click()
            expect(panel.locator('#agentGoal')).to_contain_text('review ready' if variant=='review' else 'human review',timeout=30000)
            history=panel.evaluate("async()=>await send('agent_history')")[-1]
            if variant=='ambiguous':
                expect(panel.locator('#error')).to_contain_text('education 1 → School or University')
                expect(panel.locator('#error')).to_contain_text('Several matching options')
                assert page.locator('[data-test-row^=education-] [data-automation-id=selectedItem]').count()==0
            elif variant=='rerender':
                expect(page.locator('[data-test-row^=education-] [data-automation-id=selectedItem]').first).to_have_text('First University')
                assert any('re-observing replaced control' in e['label'] for e in history['events'])
                assert page.locator('[data-test-row^=education-]').count()==1
            elif variant=='site_error':
                assert history['steps']==history['verified']==0
                expect(panel.locator('#agentGoal')).to_contain_text('page/server error')
            else:assert history['status']=='review_ready' and history['steps']==0
            assert history['steps']<20 and not fixture.submissions
        finally:context.close()


@pytest.mark.parametrize('language',['en','it'])
def test_real_extension_partial_records_legacy_catalog_and_checkpoint_recovery(tmp_path,extension_backend,language):
    """Reproduce dates surviving failed university lookup, then resume the actual MV3 executor."""
    store.set_setting('candidate_context',{
        'education':[{'institution':'First University','degree':'Computer Science','level':'masters','completed':True,'start_year':2022,'end_year':2025},
                     {'institution':'Second University','degree':'Mathematics','level':'bachelors','completed':True,'start_year':2019,'end_year':2022}],
        'languages':{'Arabic':'Native','English':'Advanced / C1','French':'Fluent','Italian':'Beginner'},
        'certifications':[{'name':'Synthetic Certificate','issuer':'Example Institute'}],
        'skills':{'programming':['Python','SQL']}})
    extension=Path('extension').resolve()
    with FixtureServer() as fixture,sync_playwright() as playwright:
        context=playwright.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,
            args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            identifier=worker.url.split('/')[2];worker.evaluate('async()=>await chrome.storage.local.set({aiMode:false})')
            page=context.new_page();page.goto(fixture.url+'/workday?actual=1&catalog=1&legacy=1&lang='+language)
            page.evaluate("step=1;show();document.querySelector('[data-test-section=experience]').remove();window.blockSchool=true")
            tab_id=worker.evaluate("async()=> (await chrome.tabs.query({})).find(t=>(t.url||'').includes('/workday')).id")
            panel=context.new_page();panel.goto(f'chrome-extension://{identifier}/panel.html?tab={tab_id}')
            errors=[];panel.on('pageerror',lambda error:errors.append(str(error)));page.on('pageerror',lambda error:errors.append(str(error)))
            code=httpx.post(f'http://127.0.0.1:{extension_backend}/api/extension/pairing-code').json()['code']
            panel.locator('#settingsToggle').click();panel.locator('#backendPort').fill(str(extension_backend))
            panel.locator('#pairCode').fill(code);panel.locator('#pair').click();expect(panel.locator('#connection')).to_contain_text('Connected locally')
            panel.locator('#settingsToggle').click()
            # Exercise real backend 422 diagnostics; entered values must never appear in the error.
            diagnostic=worker.evaluate("""async()=>{try{await api('/agent/run','POST',{private:'DO_NOT_LOG_THIS'});}catch(error){return {message:error.message,code:error.code};}}""")
            assert diagnostic['code']=='validation_failed' and 'body.id' in diagnostic['message']
            assert 'DO_NOT_LOG_THIS' not in diagnostic['message'] and 'versions differ' not in diagnostic['message']
            # A checkpoint transport failure before the first action must retain its actual stage.
            worker.evaluate("()=>{globalThis.realApi=api;api=async(path,...args)=>{if(path==='/agent/run')throw Object.assign(Error('Synthetic checkpoint transport failure'),{code:'offline'});return realApi(path,...args);};}")
            panel.locator('#runAgent').click();expect(panel.locator('#agentGoal')).to_contain_text('save_progress failed (offline)')
            expect(panel.locator('#agentGoal')).to_contain_text('No browser action started')
            worker.evaluate('()=>{api=realApi;}')
            # Simulate an older checkpoint: undefined elapsed time and surplus backend metadata caused strict schema rejection.
            panel.evaluate("""async()=>{const saved=(await chrome.storage.local.get('agentCheckpoint')).agentCheckpoint;
              delete saved.run.elapsed_ms;saved.run.at='legacy metadata';saved.run.events.push({tool:'unsupported',outcome:'old'});
              await chrome.storage.local.set({agentCheckpoint:saved});}""")
            panel.reload();expect(panel.locator('#runAgent')).to_have_text('Resume application')
            # The executor continues independent fields after catalog failure instead of stopping at its first lookup.
            panel.locator('#runAgent').click();expect(panel.locator('#agentGoal')).to_contain_text('human review',timeout=45000)
            edu=page.locator('[data-test-row^=education-]')
            expect(edu.nth(0).locator('[name=to1]')).to_have_value('2025')
            expect(edu.nth(1).locator('[name=to2]')).to_have_value('2022')
            assert edu.locator('[data-automation-id=selectedItem]').count()==2 # Field-of-study chips; universities still failed.
            state=panel.evaluate("({fields:snapshot.fields.filter(f=>f.section==='education'),drafts:plan.drafts,actions:plan.actions})")
            assert all(f['bound_record'] in (0,1) for f in state['fields'])
            assert not any(d['kind']=='missing_fact' and ('University' in d['label'] or 'Universit' in d['label']) for d in state['drafts'])
            assert panel.evaluate("ForgeApplyAgent.run.events.some(e=>e.label.includes('continuing independent fields'))")
            # Catalog becomes available. Resume uses known records, selects every value, and stops for the CV.
            page.evaluate('window.blockSchool=false')
            panel.locator('#runAgent').click();expect(panel.locator('#agentGoal')).to_contain_text('human review',timeout=45000)
            expect(edu.nth(0).locator('[data-automation-id=selectedItem]').first).to_have_text('First University')
            expect(edu.nth(1).locator('[data-automation-id=selectedItem]').first).to_have_text('Second University')
            expect(edu.nth(0).locator('[id$="--degree"]')).to_have_text('Master Degree')
            expect(edu.nth(1).locator('[id$="--degree"]')).to_have_text('Bachelor Degree')
            for i,(name,level) in enumerate(store.get_setting('candidate_context')['languages'].items()):
                row=page.locator('[data-test-row^=languages-]').nth(i)
                expect(row.locator('[id$="--language"]')).to_have_text(name)
                expect(row.locator('[id$="--overall"]')).to_contain_text(level)
            expect(page.locator('#skillChips [data-automation-id=selectedItem]')).to_have_text(['Python','SQL'])
            assert edu.count()==2 and page.locator('[data-test-row^=languages-]').count()==4
            cv=tmp_path/'synthetic.pdf';cv.write_bytes(b'%PDF-1.4\nSynthetic\n%%EOF')
            with page.expect_file_chooser() as chooser:panel.locator('#chooseFile').click()
            chooser.value.set_files(str(cv));expect(page.locator('#uploadStatus')).to_contain_text('Upload accepted')
            history=panel.evaluate("async()=>await send('agent_history')")[-1]
            assert history['verified']>=2 and isinstance(history['elapsed_ms'],int)
            assert not errors and not fixture.submissions
            page.screenshot(path=str(tmp_path/'partial-records-recovered.png'),full_page=True)
            panel.screenshot(path=str(tmp_path/'recovered-panel.png'),full_page=True)
            (tmp_path/'evidence.json').write_text(json.dumps({'language':language,'education':2,'languages':4,'certifications':1,
                'skills':['Python','SQL'],'upload':'accepted','checkpoint_recovered':True,'submissions':0}),encoding='utf-8')
        finally:context.close()
