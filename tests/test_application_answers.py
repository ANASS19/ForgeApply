import pytest
from forgeapply.application_answers import draft_answer,draft_resume,response_language,evidence_catalog


def test_retrieval_uses_only_reviewed_relevant_current_facts():
    from forgeapply.application_answers import retrieve_reviewed_answers
    answers=[{'id':1,'pattern':'^Preferred programming stack$','answer':'Python','source':'user:extension-reviewed-exact'},
             {'id':2,'pattern':'^Programming stack$','answer':'unreviewed','source':'model'},
             {'id':3,'pattern':'^Visa programming$','answer':'Yes','source':'user:local-dashboard'},
             {'id':4,'pattern':'^Programming email$','answer':'stale','fact_path':'profile.email','source':'user:local-dashboard'},
             {'id':5,'pattern':'^Programming stack$','answer':'disabled','enabled':False,'source':'user:local-dashboard'},
             {'id':6,'pattern':'^Favourite colour$','answer':'Blue','source':'user:local-dashboard'}]
    found=retrieve_reviewed_answers([{'label':'Your programming stack?'}],answers,{'email':'current@example.test'})
    assert {f['id'] for f in found}=={'reviewed_answer.1','reviewed_answer.4'}
    assert 'stale' not in str(found) and 'current@example.test' in str(found)


def test_resume_emphasizes_current_vacancy_skills_without_inventing():
    first=draft_resume(PROFILE,CONTEXT,job_description='SQL and Python required; Rust helpful')
    second=draft_resume(PROFILE,CONTEXT,job_description='Computer Vision role')
    assert first['value'].index('SQL')<first['value'].index('PyTorch')
    assert second['value'].index('Computer Vision')<second['value'].index('Python')
    assert 'Rust' not in first['value'] and 'Unverified' not in second['value']


PROFILE={'first_name':'Fixture','last_name':'Candidate','years_ai':'2','resume_en':'PRIVATE-PATH'}
CONTEXT={'education':[{'level':'masters','degree':'Computer Science','institution':'Fixture University','completed':True}],
         'experience':[{'title':'Developer','employer':'Synthetic Company'},
                       {'title':'Unverified role','employer':'Unknown','verified':False}],
         'skills':{'programming':['Python','SQL'],'ai':['PyTorch','Computer Vision'],
                   'planned':['FutureSkill'],'independent_learning':['LearningOnly']},'languages':{'Italian':'Beginner'}}


@pytest.mark.parametrize('question,lang,opening',[('Lettera di motivazione*Obbligatorio','it','Gentile team'),
    ('Why are you applying for this position?','en','Dear Hiring'),('Perché ti candidi per questo ruolo?','it','Gentile team')])
def test_grounded_bilingual_letters(question,lang,opening):
    draft=draft_answer(question,PROFILE,CONTEXT,job_title='AI Engineer',company='Example')
    assert draft['language']==lang and draft['value'].startswith(opening)
    assert draft['needs_review'] and draft['source']=='verified_fact_template'
    assert all(s['id'] in ('education.0','experience.0','skills') for s in draft['facts_used'])
    for fact in ('Computer Science','Python','Example','Fixture Candidate'): assert fact in draft['value']
    for unknown in ('Unknown','Unverified','FutureSkill','LearningOnly','PRIVATE-PATH','2 years','fluent'): assert unknown not in draft['value']


def test_language_and_missing_evidence_are_explicit():
    assert response_language('Motivation letter',preferred='it')=='it'
    assert response_language(page_language='it-IT')=='it'
    assert draft_answer('Cover letter',PROFILE,{}) is None
    assert draft_answer('Quanti anni di esperienza Python?',PROFILE,CONTEXT) is None
    assert draft_answer('Expected salary',PROFILE,CONTEXT) is None
    assert draft_answer('Education background',PROFILE,{'education':[{'degree':'Unfinished','completed':False}]}) is None
    letter=draft_answer('Cover letter',PROFILE,CONTEXT,language='en',job_description='Computer Vision')
    assert 'Computer Vision' in letter['value']
    assert 'PRIVATE-PATH' not in str(evidence_catalog(PROFILE,CONTEXT))


def test_cv_uses_verified_facts_and_retains_existing_document_paths():
    context=CONTEXT|{'certifications':[{'name':'Example Certificate','issuer':'Example Institute'}, {'name':'Unverified Certificate','verified':False}]}
    cv=draft_resume(PROFILE,context,'it')
    assert cv['needs_review'] and cv['kind']=='cv'
    for fact in ('FORMAZIONE','ESPERIENZA PROFESSIONALE','Computer Science','Python','Developer - Synthetic Company'):
        assert fact in cv['value']
    for invented in ('Unverified role','FutureSkill','LearningOnly','PRIVATE-PATH'):
        assert invented not in cv['value']
    assert PROFILE['resume_en']=='PRIVATE-PATH'
    assert 'CERTIFICAZIONI' in cv['value'] and 'Example Certificate - Example Institute' in cv['value']
    assert 'Unverified Certificate' not in cv['value']
    assert any(f['id']=='certifications.0' for f in evidence_catalog(PROFILE,context))
    assert draft_resume(PROFILE,{}) is None
