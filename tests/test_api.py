from fastapi.testclient import TestClient
from forgeapply.app import app
from forgeapply import store
from forgeapply import __version__


def test_api_roundtrip():
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        health=client.get('/api/health').json()
        assert health['ok'] and health['version']==__version__
        assert app.version==__version__
        r=client.post('/api/jobs',json={'title':'AI Engineer','url':'https://example.org/job/17','company':'Acme','location':'Rome, Italy'})
        assert r.status_code==200
        jid=r.json()['id']
        jobs=client.get('/api/jobs').json()
        assert any(j['id']==jid for j in jobs)
        assert client.put(f'/api/jobs/{jid}/status',json={'status':'queued'}).status_code==200
        assert client.get('/api/stats').json()['queued']>=1
        assert client.get('/').status_code==200
        assert client.get('/static/app.js').status_code==200
        assert client.get('/api/export').status_code==200


def test_profile_update_and_answers():
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        assert client.put('/api/profile',json={'data':{'first_name':'Test','email':'test@example.org'}}).status_code==200
        assert client.get('/api/profile').json()['first_name']=='Test'
        assert client.post('/api/answers',json={'pattern':'years.*AI','answer':'2'}).status_code==200
        assert any(a['answer']=='2' for a in client.get('/api/answers').json())


def test_openrouter_catalog_configuration_consent_and_key_stay_separate(monkeypatch):
    import httpx
    from forgeapply import app as api_module,llm
    details=[{'id':'google/gemma-4-31b-it:free','name':'Synthetic catalog entry','input_modalities':['text','image'],
              'output_modalities':['text'],'supported_parameters':['response_format']}]
    monkeypatch.setattr(api_module,'openrouter_models',lambda **kwargs:details)
    monkeypatch.setattr(llm,'openrouter_models',lambda *args,**kwargs:details)
    monkeypatch.setenv('OPENROUTER_API_KEY','synthetic-key-not-for-storage')
    store.save_profile({'first_name':'Fixture'})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        previous=client.get('/api/llm').json()
        catalog=client.get('/api/llm/openrouter-models').json()
        assert catalog['models']==[details[0]['id']] and not catalog['inference_verified']
        assert client.get('/api/llm').json()==previous
        body={'provider':'openrouter','model':details[0]['id'],'api_key_env':'OPENROUTER_API_KEY'}
        assert client.put('/api/llm',json=body).status_code==200
        assert client.post('/api/llm/test').status_code==400 # Remote consent still required.
        assert client.put('/api/llm',json=body|{'allow_remote':True}).status_code==200
        original=httpx.Client
        monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(
            lambda request:httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})),**kwargs))
        assert client.post('/api/llm/test').json()['ok']
        saved=client.get('/api/llm')
        assert saved.json()['model']==details[0]['id'] and 'synthetic-key-not-for-storage' not in saved.text
        assert store.get_setting('profile')['first_name']=='Fixture'


def test_provider_session_key_is_private_temporary_origin_and_configuration_bound(monkeypatch):
    import os,httpx
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    secret='synthetic-session-secret-not-for-storage'
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        settings={'provider':'openrouter','model':'vendor/model','allow_remote':False}
        client.put('/api/llm',json=settings).raise_for_status()
        body={'provider':'openrouter','key':secret}
        assert client.post('/api/llm/session-key',json=body,headers={'Origin':'https://evil.example'}).status_code==403
        assert 'OPENROUTER_API_KEY' not in os.environ
        assert client.post('/api/llm/session-key',json=body|{'provider':'openai'}).status_code==409
        assert client.post('/api/llm/session-key',json=body|{'api_key_env':'OTHER_API_KEY'}).status_code==409
        response=client.post('/api/llm/session-key',json=body)
        assert response.status_code==200 and response.json()['storage']=='backend_session'
        assert os.environ['OPENROUTER_API_KEY']==secret and secret not in response.text
        saved=client.get('/api/llm');assert secret not in saved.text and not saved.json()['allow_remote']
        assert client.post('/api/llm/test').status_code==400 # Key setup alone cannot enable remote inference.
        for bad in (['PRIVATE_INPUT'],{'nested':'PRIVATE_INPUT'},'PRIVATE_INPUT\nline','PRIVATE_INPUT'*400):
            rejected=client.post('/api/llm/session-key',json=body|{'key':bad})
            assert rejected.status_code==400 and 'PRIVATE_INPUT' not in rejected.text
        assert secret not in str(store.get_setting('llm')) and os.environ['OPENROUTER_API_KEY']==secret
        client.put('/api/llm',json=settings|{'allow_remote':True}).raise_for_status()
        from forgeapply import llm
        monkeypatch.setattr(llm,'openrouter_models',lambda *a,**k:[])
        original=httpx.Client
        def handler(request):
            assert request.headers['authorization']=='Bearer '+secret
            return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})
        monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
        assert client.post('/api/llm/test').json()['ok'] # No restart or persistent secret file required.


def test_profile_context_provenance_and_unknown_values_persist():
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        client.put('/api/profile',json={'data':{'first_name':'Fixture','years_ai':'2','resume_en':'C:/private.txt'}}).raise_for_status()
        client.put('/api/candidate-context',json={'education':[{'degree':'Master','completed':True}],
                   'languages':{'Italian':'Beginner'},'source':'user:verified-setup'}).raise_for_status()
        store.init_db()  # Idempotent schema upgrade/restart.
        profile=client.get('/api/profile').json()
        assert profile['first_name']=='Fixture' and profile['years_ai']=='2'
        for key in ('years_python','work_authorized','needs_sponsorship','notice_period','salary_expectation','resume_en'):
            assert profile[key]==''
        assert client.get('/api/profile/provenance').json()['first_name']['verified']
        assert client.get('/api/candidate-context').json()['languages']['Italian']=='Beginner'
        assert client.post('/api/answers',json={'pattern':'[','answer':'invalid'}).status_code==400


def test_local_origin_host_and_submission_guards():
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        for headers in ({'Origin':'http://evil.example'}, {'Origin':'http://127.0.0.1:9999'},
                        {'Origin':'null'}, {'Sec-Fetch-Site':'cross-site'}):
            assert client.put('/api/profile',json={'data':{}},headers=headers).status_code==403
        assert client.get('/api/profile',headers={'Host':'evil.example'}).status_code==403
        assert client.put('/api/profile',json={'data':{}},headers={'Origin':'http://127.0.0.1:8765'}).status_code==200
        jid=client.post('/api/jobs',json={'title':'Fixture','url':'https://example.org/confirmation-test'}).json()['id']
        assert client.put(f'/api/jobs/{jid}/status',json={'status':'submitted'}).status_code==400
        assert client.put(f'/api/jobs/{jid}/status',json={'status':'submitted','acknowledged':True,'note':'User saw confirmation'}).status_code==200
        assert client.post('/api/resumes/en',files={'file':('fake.pdf',b'not a pdf')}).status_code==400
        assert client.post('/api/resumes/it',files={'file':('fake.docx',b'not a docx')}).status_code==400
