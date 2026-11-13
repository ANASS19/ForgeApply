from fastapi.testclient import TestClient
from forgeapply.app import app


def test_api_roundtrip():
    with TestClient(app) as client:
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
    with TestClient(app) as client:
        assert client.put('/api/profile',json={'data':{'first_name':'Test','email':'test@example.org'}}).status_code==200
        assert client.get('/api/profile').json()['first_name']=='Test'
        assert client.post('/api/answers',json={'pattern':'years.*AI','answer':'2'}).status_code==200
        assert any(a['answer']=='2' for a in client.get('/api/answers').json())
