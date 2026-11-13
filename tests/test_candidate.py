import re
from forgeapply.candidate import screening_answers
from forgeapply.form_logic import known_answer,normalize_label,required_label


def test_answers_are_narrow_and_unknowns_absent():
    rows=screening_answers({'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.org',
                           'years_ai':'2','years_python':'','city':'Milano','country':'Italy'},
                          {'education':[{'level':'masters','completed':True}],
                           'languages':{'Italian':'Beginner','English':'Advanced / C1'}})
    def answers(question):
        return [r['answer'] for r in rows if re.search(r['pattern'],question,re.I)]
    assert answers('Full name')==['Fixture Candidate']
    assert answers('How many years of AI experience?')==['2']
    assert answers('Highest completed education')==["Master's degree"]
    assert answers('Italian language proficiency')==['Beginner']
    for question in ('Years of Python experience','Visa sponsorship','Country of citizenship',
                     'Country you are authorized to work in','I certify my full name is correct',
                     'Expected salary','Disability status','Criminal history',
                     'Years of AI experience with TensorFlow','Professional Italian required: do you qualify?'):
        assert answers(question)==[]


def test_no_degree_answer_without_completed_degree():
    assert screening_answers({}, {'education':[{'level':'masters','completed':False}]})==[]


def test_bilingual_required_markers_match_without_broadening_material_facts():
    profile={'first_name':'Fixture','last_name':'Candidate','email':'fixture@example.test','phone':'+39 351 000 0000','city':'Milano','years_ai':'2'}
    for label,key in [('Nome*Obbligatorio','first_name'),('Cognome*Obbligatorio','last_name'),
                      ('E-mail*Obbligatorio','email'),('Telefono*Obbligatorio','phone'),
                      ('First name (required)','first_name'),('Città di residenza *','city')]:
        answer=known_answer({'label':label,'type':'text','value':''},profile,[])
        assert answer and answer[0]==profile[key]
        assert required_label(label)
    assert normalize_label('Italian fluency required')=='Italian fluency required'
    for label in ('Indirizzo*Obbligatorio','Quanti anni di esperienza con Python?',
                  'Autorizzazione al lavoro','Retribuzione annua desiderata','Dichiaro di accettare la privacy'):
        assert known_answer({'label':label,'type':'text','value':''},profile,[]) is None


def test_factual_choices_use_exact_evidence_and_preserve_existing_answers():
    context={'languages':{'English':'Advanced / C1'},'skills':{'programming':['Python'],'learning':['LearningOnly']}}
    options=[{'label':'Full professional working (C1)','value':'C1'},{'label':'Professional working (B2)','value':'B2'}]
    radio={'type':'radio','label':options[0]['label'],'value':'C1','options':options,'group_label':'Livello di conoscenza della lingua inglese*'}
    assert known_answer(radio,{},[],context)==('true','context:languages.English')
    assert known_answer(radio|{'group_answered':True},{},[],context) is None
    assert known_answer(radio|{'value':'B2'},{},[],context) is None
    assert known_answer(radio,{},[],{'languages':{'English':'Advanced'}}) is None
    checkbox={'type':'checkbox','value':'on','label':'Python','group_label':'Competenze tecniche'}
    assert known_answer(checkbox,{},[],context)==('true','context:skills')
    assert known_answer(checkbox|{'label':'LearningOnly'},{},[],context) is None
    assert known_answer(checkbox|{'group_label':'I certify my skills'},{},[{'pattern':'.*','answer':'true'}],context) is None
    select={'type':'select','label':'Paese di residenza*','value':'','options':[{'label':'Italia','value':'it'}]}
    assert known_answer(select,{'country':'Italy'},[])==('Italia','profile:country')
    for label in ('Are you legally authorized to work in Italy?','Eligible to work in Italy','Work permit',
                  'Autorizzazione al lavoro','Dichiaro di accettare la privacy'):
        assert known_answer({'label':label,'type':'text','value':''},{},[{'pattern':'.*','answer':'Yes'}]) is None


def test_repair_only_invalid_values_that_match_verified_profile_facts():
    profile={'phone':'+39 351 000 0000','city':'Milano'}
    phone={'label':'Phone Number','type':'tel','value':profile['phone'],'valid':False,'phone_prefix':'+39'}
    assert known_answer(phone,profile,[])==('3510000000','profile:phone')
    assert known_answer(phone|{'value':'+39 351 999 9999'},profile,[]) is None
    assert known_answer(phone|{'valid':True},profile,[]) is None
    city={'label':'City','type':'text','value':'Milano','valid':False,'selection_required':True}
    assert known_answer(city,profile,[])==('Milano','profile:city')
    assert known_answer(city|{'value':'Roma'},profile,[]) is None
    assert known_answer({'label':'Email','group_label':'I certify this declaration','type':'text','value':''},{'email':'fixture@example.test'},[]) is None
