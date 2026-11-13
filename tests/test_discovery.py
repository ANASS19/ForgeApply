import httpx
from forgeapply import discovery


def test_scores():
    assert discovery.score_job('AI Engineer','Milan, Italy','Python') > discovery.score_job('Chief Marketing Officer','London, UK','')
    assert discovery.detect_language('Ingegnere informatico con esperienza nello sviluppo')=='it'


def test_greenhouse_mock():
    def handler(req):
        return httpx.Response(200,json={'jobs':[
            {'title':'Junior AI Engineer','absolute_url':'https://boards.greenhouse.io/acme/jobs/123',
             'location':{'name':'Milan, Italy'},'content':'<p>Python and Machine Learning</p>','updated_at':'2026-11-13'},
            {'title':'Finance Manager','absolute_url':'https://boards.greenhouse.io/acme/jobs/124',
             'location':{'name':'Paris, France'},'content':'Finance'}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs=discovery.discover_board('greenhouse','acme',client=client)
    assert len(jobs)==1
    assert jobs[0]['title']=='Junior AI Engineer'
    assert 'Python' in jobs[0]['description']


def test_lever_mock():
    def handler(req):
        return httpx.Response(200,json=[{'text':'AI Scientist','hostedUrl':'https://jobs.lever.co/test/abc',
            'categories':{'location':'Italy - Remote'}, 'description':'<p>LLM research</p>', 'createdAt':1784000000000}])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs=discovery.discover_board('lever','test',client=client)
    assert jobs[0]['source']=='lever'
    assert jobs[0]['posted_at']


def test_ashby_mock():
    def handler(req):
        return httpx.Response(200,json={'jobs':[{'title':'ML Engineer','jobUrl':'https://jobs.ashbyhq.com/a/b',
            'location':'Rome, Italy','descriptionHtml':'<b>MLops</b>','publishedAt':'2026-11-13'}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs=discovery.discover_board('ashby','acme',client=client)
    assert len(jobs)==1 and jobs[0]['title']=='ML Engineer'
