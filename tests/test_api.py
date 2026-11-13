from fastapi.testclient import TestClient
from forgeapply.app import app
from forgeapply import store


def test_api_roundtrip():
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        assert client.get('/api/health').json()['ok']
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
