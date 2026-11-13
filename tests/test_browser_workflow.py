"""Served multi-page fixture exercised through the real API and Chromium executor."""
import pytest
from fastapi.testclient import TestClient
from forgeapply import app as app_module, store
from forgeapply.browser import BrowserManager
from forgeapply.browser_tools import BrowserToolCall
from examples.fixture_server import FixtureServer


FORM = '''<!doctype html><title>Controlled application</title>
<main><h1>Candidate details</h1><form onsubmit="event.preventDefault();next()">
<input hidden id="decoy"><input disabled id="disabled">
<label>First name<input name="first_name" required></label>
<label>Email address<input name="email" type="email" required></label>
<label for="cv">Resume</label><input id="cv" name="resume" type="file" required style="display:none">
<button>Next</button></form></main>
<script>
function next(){
sessionStorage.setItem('candidate',document.querySelector('[name=first_name]').value);
sessionStorage.setItem('cv',document.querySelector('#cv').files[0].name);
document.querySelector('main').innerHTML=`<h1>Screening</h1>
<form onsubmit="event.preventDefault();review()">
<label>Years of Python experience<input name="python_years" required></label>
<label><input name="declaration" type="checkbox" required>I certify this declaration</label>
<fieldset><legend>Contact method</legend><label><input type="radio" name="contact" value="email" required>Email</label>
<label><input type="radio" name="contact" value="phone" required>Phone</label></fieldset>
<button>Review</button></form>`;
}
function review(){document.querySelector('main').innerHTML=`<h1>Final review</h1>
<p id="review">${sessionStorage.getItem('candidate')} - ${sessionStorage.getItem('cv')}</p>
<button onclick="fetch('/submit',{method:'POST'}).then(()=>document.querySelector('main').innerHTML='Application received')">Submit application</button>`;}
</script>'''


@pytest.fixture
def fixture_site():
    with FixtureServer(application_html=FORM) as fixture:
        yield fixture.url+'/apply',fixture.submissions


def test_api_chromium_prepare_upload_unknown_resume_and_final_review(tmp_path,monkeypatch,fixture_site):
    url,submissions=fixture_site
    manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
    monkeypatch.setattr(app_module,'browser',manager)
    with TestClient(app_module.app,base_url='http://127.0.0.1:8765') as client:
        try:
            client.put('/api/profile',json={'data':{'first_name':'Fixture','email':'fixture@example.org'}}).raise_for_status()
            upload=client.post('/api/resumes/en',files={'file':('fixture.pdf',b'%PDF-1.4\nfixture document\n%%EOF','application/pdf')})
            assert upload.status_code==200
            jid=client.post('/api/jobs',json={'title':'Fixture AI Engineer','company':'Controlled fixture','url':url}).json()['id']
            # HTTP must be preserved; normalization formerly forced HTTPS and broke local forms.
            assert store.get_job(jid)['url']==url
            assert client.post('/api/browser/agent/prepare',json={'job_id':jid,'use_ai':False}).json()['status']=='needs_document_approval'
            result=client.post('/api/browser/agent/prepare',json={'job_id':jid,'use_ai':False,'allow_uploads':True}).json()
            assert result['status']=='needs_answers'
            assert any('Python' in q for q in result['unknown'])
            assert any('certify' in q for q in result['unknown'])
            assert submissions==[]
            state=client.get('/api/browser/state').json()
            assert 'Screening' in state['text']
            # Required radio groups use checked/valid state, not the default value "on".
            assert any(not f['valid'] for f in state['fields'] if f['type']=='radio')
            initial=state['snapshot_id']
            client.get('/api/browser/state')
            assert client.post('/api/browser/fill',json={'index':0,'value':'4','snapshot_id':initial}).status_code==400
            # Explicit manual interaction on the synthetic form only; no candidate facts inferred.
            for index,value in ((0,'4'),(1,'true'),(2,'true')):
                assert client.post('/api/browser/fill',json={'index':index,'value':value}).status_code==200
            # Resume on the current step, without reopening/resetting the form.
            result=client.post('/api/browser/agent/prepare',json={'job_id':jid,'use_ai':False}).json()
            assert result['status']=='ready_for_review'
            assert 'Fixture - CV_en_' in result['snapshot']['text']
            assert store.get_job(jid)['status']=='prepared'
            assert submissions==[]
            assert client.post('/api/browser/click',json={'kind':'other','text':'application'}).status_code==400
            assert client.post('/api/browser/click',json={'kind':'other','text':'Submit application'}).status_code==400
            assert client.post('/api/browser/submit',json={'job_id':jid,'approved':False}).status_code==400
            assert submissions==[]
            # Already confirmed applications must be rejected before any navigation/click.
            store.set_status(jid,'submitted','Fixture manual acknowledgment',acknowledged=True)
            assert client.post('/api/browser/submit',json={'job_id':jid,'approved':True}).status_code==400
            assert client.post('/api/browser/agent/prepare',json={'job_id':jid,'use_ai':False}).status_code==400
            assert submissions==[]
        finally: manager.close()


def test_stale_dom_never_fills_another_field(tmp_path,fixture_site):
    manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
    try:
        state=manager.navigate(fixture_site[0])
        assert len(state['fields'])==3  # Includes hidden CV input, excludes disabled/hidden decoys.
        async def replace():
            await manager._page.locator('[name=first_name]').evaluate("e=>e.outerHTML='<input name=replacement>'")
        manager.call(replace())
        with pytest.raises(ValueError,match='Form changed'):
            manager.fill(0,'must not reach replacement')
        assert manager.snapshot()['fields'][0]['value']==''
    finally: manager.close()


def test_native_custom_dynamic_and_iframe_tools(tmp_path,fixture_site):
    manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
    try:
        origin=fixture_site[0].rsplit('/',1)[0]
        manager.navigate(origin+'/controls')
        store.save_profile({'country':'Italy','city':'Milano','github':'https://example.org/fixture'})
        result=manager.autofill(False,False)
        assert not result['errors']
        state=manager.snapshot()
        assert next(f for f in state['fields'] if f['name']=='country')['value']=='it'
        assert next(f for f in state['fields'] if f['type']=='combobox')['value']=='Milano'
        assert next(f for f in state['fields'] if f['name']=='github')['value']=='https://example.org/fixture'
        def tool(**data): return manager.execute_tool(BrowserToolCall(**data))
        tool(action='fill',target={'label':'Date'},value='2026-11-13')
        tool(action='fill',target={'role':'textbox','name':'Notes'},value='Fixture notes')
        tool(action='check',target={'label':'Show follow-up'},value='true')
        state=tool(action='fill',target={'label':'Portfolio'},value='https://example.org/portfolio')
        assert any(f['name']=='portfolio' and f['value']=='https://example.org/portfolio' for f in state['fields'])
        tree=tool(action='accessibility')
        assert len(tree['frames'])==2 and 'GitHub' in tree['frames'][1]['tree']
        tool(action='scroll',direction='down')
        tool(action='wait',target={'label':'GitHub','frame_index':1})
        assert 'validation_errors' in tool(action='validation')
        with pytest.raises(PermissionError): tool(action='navigate',url='https://example.org/unapproved')
        with pytest.raises(PermissionError): tool(action='press_key',target={'label':'Date'},value='Enter')
        with pytest.raises(PermissionError): tool(action='click',target={'role':'button','name':'Replace field'})
        assert fixture_site[1]==[]
    finally: manager.close()


@pytest.mark.parametrize(('path','expected'),[('/login','needs_login'),('/captcha','blocked'),('/failure','blocked')])
def test_human_handoffs(tmp_path,fixture_site,path,expected):
    manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
    try:
        jid,_=store.add_job(title='Fixture',url=fixture_site[0].rsplit('/',1)[0]+path)
        result=manager.agent_prepare(jid,use_ai=False)
        assert result['status']==expected
        assert store.get_job(jid)['status']=='blocked'
        assert store.get_browser_run(jid)['trace']
        assert fixture_site[1]==[]
    finally: manager.close()


@pytest.mark.parametrize('confirmation',[True,False])
def test_explicit_fixture_submission_receipt_and_no_replay(tmp_path,confirmation):
    outcome='Application received' if confirmation else 'Upload rejected: application not sent'
    html=f'''<h1>Controlled review</h1><label>Resume<input name="resume" type="file" required></label>
    <button onclick="fetch('/submit',{{method:'POST'}}).then(()=>document.body.innerHTML='{outcome}')">Submit application</button>'''
    cv=tmp_path/'fixture.pdf'
    cv.write_bytes(b'%PDF-1.4\nfixture\n%%EOF')
    store.save_profile({'resume_en':str(cv)})
    with FixtureServer(application_html=html) as fixture:
        jid,_=store.add_job(title='Fixture role',company='Controlled fixture',url=fixture.url+'/apply')
        other,_=store.add_job(title='Other fixture role',url=fixture.url+'/other')
        manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
        try:
            assert manager.agent_prepare(jid,allow_uploads=True)['status']=='ready_for_review'
            with pytest.raises(ValueError,match='Prepare this job'):
                manager.submit(other,True)
            async def change_page():
                await manager._page.locator('h1').evaluate("e=>e.textContent='Changed destination'")
            manager.call(change_page())
            with pytest.raises(PermissionError,match='page changed'):
                manager.submit(jid,True)
            assert not fixture.submissions
            assert manager.agent_prepare(jid,allow_uploads=True)['status']=='ready_for_review'
            result=manager.submit(jid,True)
            assert result['submitted_verified'] is confirmation
            assert fixture.submissions==['/submit']
            assert store.get_job(jid)['status']==('submitted' if confirmation else 'blocked')
            with store.conn() as db:
                import json
                row=db.execute('SELECT * FROM submission_attempts WHERE job_id=?',(jid,)).fetchone()
                evidence=json.loads(row['evidence'])
                assert evidence['resume']['language']=='en' and evidence['resume']['sha256']
                assert evidence['title']=='Fixture role'
                assert evidence['trace'] and evidence['confirmation_text']
            # A new process/browser manager must not repeat an ambiguous or confirmed click.
            manager.close()
            manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
            if confirmation:
                with pytest.raises(ValueError,match='already submitted'):
                    manager.agent_prepare(jid,allow_uploads=True)
            else:
                manager.agent_prepare(jid,allow_uploads=True)
                with pytest.raises(ValueError,match='already attempted'):
                    manager.submit(jid,True)
            assert fixture.submissions==['/submit']
        finally: manager.close()


def test_unexpected_redirect_requires_destination_approval(tmp_path):
    html='<label>Email<input type="email" name="email" required></label><button>Submit application</button>'
    store.save_profile({'email':'fixture@example.org'})
    with FixtureServer(application_html=html) as target, FixtureServer(redirects={'/redirect':target.url+'/apply'}) as source:
        jid,_=store.add_job(title='Fixture redirect',url=source.url+'/redirect')
        manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
        try:
            result=manager.agent_prepare(jid)
            assert result['status']=='needs_destination_approval'
            assert manager.snapshot()['fields'][0]['value']==''
            with pytest.raises(PermissionError): manager.autofill(False,False)
            manager.approve_destination(jid)
            assert manager.agent_prepare(jid)['status']=='ready_for_review'
            assert manager.snapshot()['fields'][0]['value']=='fixture@example.org'
            assert not target.submissions and not source.submissions
        finally: manager.close()


@pytest.mark.parametrize('upload_html',[
    '<input type="file"><input type="file">',
    '<input type="file" name="resume" onchange="this.value=\'\'">',
])
def test_upload_ambiguity_and_rejection_are_recoverable(tmp_path,upload_html):
    cv=tmp_path/'fixture.pdf'; cv.write_bytes(b'%PDF-1.4\nfixture\n%%EOF')
    store.save_profile({'resume_en':str(cv)})
    with FixtureServer(application_html=upload_html+'<button>Submit application</button>') as fixture:
        jid,_=store.add_job(title='Fixture upload',url=fixture.url+'/apply')
        manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
        try:
            result=manager.agent_prepare(jid,allow_uploads=True)
            assert result['status']=='needs_resume'
            assert store.get_job(jid)['status']=='blocked'
            assert store.get_browser_run(jid)['trace']
            assert not fixture.submissions
        finally: manager.close()


def test_validation_stall_does_not_repeat_navigation(tmp_path):
    html='''<label>Email<input name="email" type="email" required></label>
    <button onclick="this.dataset.clicks=Number(this.dataset.clicks||0)+1">Next</button>'''
    store.save_profile({'email':'fixture@example.org'})
    with FixtureServer(application_html=html) as fixture:
        jid,_=store.add_job(title='Fixture stall',url=fixture.url+'/apply')
        manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
        try:
            assert manager.agent_prepare(jid)['status']=='stalled'
            async def clicks(): return await manager._page.locator('button').get_attribute('data-clicks')
            assert manager.call(clicks())=='1'
            assert not fixture.submissions
        finally: manager.close()


def test_closed_browser_recovers_on_explicit_observation(tmp_path,fixture_site):
    manager=BrowserManager(headless=True,user_data_dir=tmp_path/'chromium')
    try:
        manager.navigate(fixture_site[0])
        async def close_context(): await manager._context.close()
        manager.call(close_context())
        state=manager.snapshot()
        assert state['url']=='about:blank'
        assert manager._job_id is None
        manager.navigate(fixture_site[0])
        assert manager.snapshot()['fields']
    finally: manager.close()
