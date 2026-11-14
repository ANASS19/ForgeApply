from fastapi.testclient import TestClient
from forgeapply.app import app
from forgeapply import store
from forgeapply.form_logic import bind_records,known_answer,record_fingerprint,matching_choice
from tests.test_extension import paired


def test_italian_street_alias_national_phone_and_sensitive_fields():
    profile={'street_address':'Synthetic Street 7','phone':'+39 351 000 0000','city':'Milano','country':'Italy'}
    assert known_answer({'label':'Via/Piazza','type':'text'},profile,[])[0]=='Synthetic Street 7'
    assert known_answer({'label':'Numero di telefono*','type':'text','phone_prefix':'+39','value':'+39 351 000 0000','valid':False},profile,[])[0]=='3510000000'
    assert known_answer({'label':'Numero di telefono','type':'text','phone_prefix':'+33','value':'+39 351 000 0000'},profile,[]) is None
    options=[{'label':'Italia (+39)','value':'country-it'},{'label':'Francia (+33)','value':'country-fr'}]
    assert known_answer({'label':'Prefisso*','type':'select','options':options},profile,[])[0]=='Italia (+39)'
    ambiguous=[{'label':'Canada (+1)','value':'ca'},{'label':'United States (+1)','value':'us'}]
    assert known_answer({'label':'Phone prefix','type':'select','options':ambiguous},{'phone':'+1 212 555 1234'},[]) is None
    for label in ['Paese di nascita','Città di nascita']:
        assert known_answer({'label':label,'type':'text'},profile,[]) is None
    for label in ['Nazionalità','Cittadinanza','Sei disponibile al trasferimento?']:
        assert known_answer({'label':label,'type':'text'},profile,[{'pattern':'.*','answer':'Italy'}]) is None


def test_populated_records_bind_by_identity_and_empty_rows_do_not_duplicate_them():
    context={'experience':[{'title':'Developer','employer':'First','start':'2022-06','end':'2023-01'},
                           {'title':'Engineer','employer':'Second','start':'2023-02','end':'2025-04'},
                           {'title':'Unverified','employer':'Other','current_employment_verified':False}]}
    fields=[{'section':'experience','record_index':0,'record_identity':{'employer':'Second'},'label':'Job title','value':'','type':'text'},
            {'section':'experience','record_index':1,'record_identity':{},'label':'Company','value':'','type':'text'}]
    context['_form_bindings']=bind_records(fields,context)
    assert known_answer(fields[0],{},[],context)[0]=='Engineer'
    assert known_answer(fields[1],{},[],context)[0]=='First'
    assert known_answer(fields[1]|{'label':'From Year'}, {},[],context)[0]=='2022'
    assert known_answer(fields[1]|{'label':'From Month'}, {},[],context)[0]=='6'
    assert known_answer(fields[1]|{'label':'Start Date'}, {},[],context)[0]=='2022-06'
    assert known_answer(fields[1]|{'label':'From Month'}, {},[],context|{'experience':[{'start':'2022'}]}) is None
    unknown=[fields[0]|{'record_identity':{'employer':'User supplied other employer'}},fields[1]]
    assert all(v is None for v in bind_records(unknown,context).values())


def test_bounded_expansion_and_exact_company_question_memory():
    store.set_setting('candidate_context',{'experience':[{'title':'Developer','employer':'First'},{'title':'Engineer','employer':'Second'}]})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        field={'index':0,'token':'company','section':'experience','record_index':0,'label':'Company','type':'text','required':True}
        body={'url':'https://example.test/apply','snapshot_id':'s','fields':[field],'site_authorized':True,
              'add_controls':[{'section':'experience','token':'add','existing_count':1}]}
        plan=client.post('/api/extension/plan',headers=headers,json=body).json()
        assert plan['actions'][0]['value']=='First' and plan['structure_actions'][0]['count']==1
        plan=client.post('/api/extension/plan',headers=headers,json=body|{'fields':[field|{'record_identity':{'employer':'Unknown'}}]}).json()
        assert not plan['actions'] and not plan['structure_actions']
        choices=[{'label':'Yes','value':'wd-yes'},{'label':'No','value':'wd-no'}]
        fields=[{'index':i,'token':str(i),'type':'radio','name':'previous','value':o['value'],'label':o['label'],
                 'group_label':'Have you ever worked for Synthetic Employer?','required':True,'options':choices} for i,o in enumerate(choices)]
        body=body|{'fields':fields,'add_controls':[]}
        plan=client.post('/api/extension/plan',headers=headers,json=body).json()
        assert len(plan['drafts'])==1 and plan['drafts'][0]['kind']=='missing_choice'
        reviewed=client.post('/api/extension/reviewed-plan',headers=headers,json=body|{'reviewed':True,'answers':[{'index':0,'token':'0','value':'wd-no','remember':True}]}).json()
        assert reviewed['actions']==[{'index':1,'token':'1','value':'true','source':'user-reviewed-answer'}]
        assert store.list_answers()[0]['answer']=='No' # Persist meaning, not a tenant-specific opaque ID.
        plan=client.post('/api/extension/plan',headers=headers,json=body).json()
        assert plan['actions'][0]['index']==1


def test_reviewed_record_answer_is_scoped_to_its_record_and_reused_in_italian():
    store.set_setting('candidate_context',{'education':[{'institution':'First University','degree':'Computer Science','completed':True}]})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        field={'index':0,'token':'month','type':'text','label':'From Month','section':'education','record_index':0,
               'record_identity':{'institution':'First University'},'required':True}
        body={'url':'https://example.test/apply','snapshot_id':'s','fields':[field],'site_authorized':True}
        response=client.post('/api/extension/reviewed-plan',headers=headers,json=body|{'reviewed':True,'answers':[{'index':0,'token':'month','value':'10','remember':True}]})
        assert response.status_code==200 and response.json()['remembered']==1
        assert not store.list_answers()
        plan=client.post('/api/extension/plan',headers=headers,json=body|{'fields':[field|{'label':'Data inizio mese'}]}).json()
        assert plan['actions'][0]['value']=='10'


def test_diagnostics_keep_control_structure_without_entered_answers():
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        body={'url':'https://example.test/apply','snapshot_id':'s','site_authorized':True,
              'fields':[{'index':0,'token':'secret-token','label':'Email','type':'email','value':'private@example.test',
                         'automation_id':'emailAddress','automation_path':['emailAddress','formField-emailAddress']}]}
        client.post('/api/extension/plan',headers=headers,json=body).raise_for_status()
        response=client.get('/api/extension/control-diagnostics')
        assert response.status_code==200 and response.json()[0]['fields'][0]['automation_id']=='emailAddress'
        assert 'private@example.test' not in response.text and 'secret-token' not in response.text
        assert client.get('/api/extension/control-diagnostics',headers=headers).status_code==403


def test_referral_source_is_scoped_to_one_application():
    url='https://example.test/jobs/one/apply'
    store.set_setting('application_specific_answers',{store.normalized_url(url):[
        {'pattern':r'^How Did You Hear About Us\?$','answer':'LinkedIn','enabled':True,'source':'user:verified-this-vacancy'}]})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        body={'url':url,'snapshot_id':'s','site_authorized':True,'fields':[{'index':0,'token':'source','label':'How Did You Hear About Us?','required':True}]}
        assert client.post('/api/extension/plan',headers=headers,json=body).json()['actions'][0]['value']=='LinkedIn'
        assert not client.post('/api/extension/plan',headers=headers,json=body|{'url':'https://example.test/jobs/two/apply'}).json()['actions']


def test_model_understands_new_label_and_reviewed_binding_tracks_profile_updates(monkeypatch):
    from forgeapply.llm import DecisionModel
    store.save_profile({'email':'fixture@example.test'})
    monkeypatch.setattr(DecisionModel,'json',lambda *args,**kwargs:{'answers':[{
        'field_index':0,'fact_id':'profile.email','value':'','evidence_ids':[],'needs_information':False}]})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        field={'index':0,'token':'email','type':'email','label':'Where should the recruiter email you?','required':True}
        body={'url':'https://employer.example.test/apply','snapshot_id':'s','fields':[field],'site_authorized':True,'use_ai':True}
        plan=client.post('/api/extension/plan',headers=headers,json=body).json()
        assert not plan['actions'] # An unfamiliar model mapping is reviewed first.
        assert plan['drafts'][0]['value']=='fixture@example.test' and plan['drafts'][0]['fact_id']=='profile.email'
        reviewed=body|{'reviewed':True,'answers':[{'index':0,'token':'email','value':'fixture@example.test','fact_id':'profile.email','remember':True}]}
        assert client.post('/api/extension/reviewed-plan',headers=headers,json=reviewed).status_code==200
        assert store.list_answers()[0]['fact_path']=='profile.email'
        store.save_profile({'email':'updated@example.test'})
        plan=client.post('/api/extension/plan',headers=headers,json=body|{'use_ai':False}).json()
        assert plan['actions'][0]['value']=='updated@example.test'
        assert not client.post('/api/extension/plan',headers=headers,json=body|{'use_ai':False,'url':'https://different.example.test/apply'}).json()['actions']
        store.save_profile({'email':''})
        assert not client.post('/api/extension/plan',headers=headers,json=body|{'use_ai':False}).json()['actions']
        assert client.post('/api/extension/reviewed-plan',headers=headers,json=reviewed|{'answers':[{'index':0,'token':'email','value':'x','fact_id':'profile.resume_en'}]}).status_code==422


def test_language_component_and_certification_facts_are_not_inferred():
    context={'languages':{'English':'Advanced / C1'},'certifications':[{'name':'Verified Cert','issuer':'Example','issued_at':'2025-02'},{'name':'Learning badge','verified':False}]}
    fields=[{'section':'languages','record_index':0,'label':'Speaking','value':'','type':'text'},
            {'section':'certifications','record_index':0,'label':'Certification','value':'','type':'text'}]
    context['_form_bindings']=bind_records(fields,context)
    assert known_answer(fields[0],{},[],context) is None
    assert known_answer(fields[1],{},[],context)[0]=='Verified Cert'


def test_workday_overall_and_gpa_keep_distinct_scales():
    context={'languages':{'English':'Advanced / C1'},'education':[{'institution':'Example University','completed':True,'grade':'97/110','start':'2022-10','graduated_at':'2025-11'}]}
    fields=[{'section':'languages','record_index':0,'label':'Overall*','value':'','type':'combobox'},
            {'section':'education','record_index':0,'label':'Overall Result (GPA)','value':'','type':'text'}]
    context['_form_bindings']=bind_records(fields,context)
    assert known_answer(fields[0],{},[],context)[0]=='Advanced / C1'
    assert known_answer(fields[1],{},[],context) is None
    year=fields[1]|{'label':'From Year','automation_id':'dateSectionYear-input'}
    assert known_answer(year,{},[],context)[0]=='2022'
    assert known_answer(year|{'label':'To (Actual or Expected)'},{},[],context)[0]=='2025'


def test_partial_education_dates_recover_unique_binding_without_guessing():
    context={'education':[{'institution':'First University','completed':True,'start_year':2022,'end_year':2025},
                          {'institution':'Second University','completed':True,'start_year':2019,'end_year':2022}]}
    school={'section':'education','record_index':0,'label':'School or University','type':'combobox','value':''}
    year=school|{'label':'To Year','type':'text','value':'2025'}
    bindings=bind_records([school,year],context)
    assert bindings[('education',0)]==0
    assert known_answer(school,{},[],context|{'_form_bindings':bindings})[0]=='First University'
    assert bind_records([school,year|{'value':'1998'}],context)[('education',0)] is None
    ambiguous=context|{'education':[context['education'][0],context['education'][1]|{'end_year':2025}]}
    assert bind_records([school,year],ambiguous)[('education',0)] is None
    assert bind_records([school,year,school|{'label':'Unrecognized detail','value':'Manual text'}],context)[('education',0)] is None


def test_isolated_record_binding_survives_partial_selection_but_rejects_changed_source_or_identity():
    record={'institution':'First University','completed':True,'end_year':2025}
    field={'section':'education','record_index':0,'bound_record':0,'record_fingerprint':record_fingerprint(record),
           'label':'To Year','value':'2025','type':'text'}
    assert bind_records([field],{'education':[record]})[('education',0)]==0
    assert bind_records([field|{'record_identity':{'institution':'Other University'}}],{'education':[record]})[('education',0)] is None
    assert bind_records([field],{'education':[record|{'institution':'Updated University'}]})[('education',0)] is None
    reviewed=record|{'form_answers':{'università':{'value':'Other'}}}
    assert record_fingerprint(reviewed)==record_fingerprint(record)
    assert bind_records([field|{'record_identity':{'institution':'Other'}}],{'education':[reviewed]})[('education',0)]==0
    context={'education':[reviewed],'_form_bindings':{('education',0):0}}
    assert known_answer(field|{'value':'','label':'School or University'}, {},[],context)[0]=='Other'


def test_known_catalog_fact_is_not_reported_as_missing_information():
    store.set_setting('candidate_context',{'education':[{'institution':'First University','level':'masters','completed':True}]})
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        headers,_=paired(client)
        field={'index':0,'token':'degree','record_key':'education-88','section':'education','record_index':0,
               'label':'Degree','type':'combobox','required':True,'options':[{'value':'diploma','label':'Technical Diploma'}]}
        body={'url':'https://example.test/apply','snapshot_id':'s','fields':[field],'site_authorized':True}
        plan=client.post('/api/extension/plan',headers=headers,json=body).json()
        assert not plan['actions'] and plan['drafts'][0]['kind']=='selection_unresolved'
        assert plan['drafts'][0]['known_value']=="Master's degree"
        assert plan['record_bindings'][0]['bound_record']==0
        assert 'institution' not in plan['record_bindings'][0]
        conflict=client.post('/api/extension/plan',headers=headers,json=body|{'fields':[field|{'record_identity':{'institution':'Unrelated University'}}]}).json()
        assert conflict['drafts'][0]['kind']=='record_unresolved' and not conflict['record_bindings']
    assert matching_choice('Beginner',[{'label':'1 - Beginner','value':'basic'}])['value']=='basic'
    assert matching_choice('C1',[{'label':'1 - Beginner','value':'basic'}]) is None
