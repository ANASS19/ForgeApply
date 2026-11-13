import pytest
from forgeapply.application_answers import draft_answer,draft_resume,response_language,evidence_catalog


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
