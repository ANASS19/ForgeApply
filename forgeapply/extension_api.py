# SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
# SPDX-License-Identifier: Apache-2.0
"""Narrow authenticated MV3 bridge. No arbitrary local files or managed-browser commands."""
import hashlib
import base64
import re
import secrets
import time
import httpx
from typing import Literal
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field,ConfigDict
from . import store,discovery
from .form_logic import known_answer,SENSITIVE_QUESTION,normalize_label,required_label,matching_choice,bind_records,verified_records,record_question_key,sensitive_field,record_storage,verified_skills,record_data,record_fingerprint
from .application_answers import draft_answer,draft_resume,response_language,needs_exact_fact,evidence_catalog,question_kind,application_specific_question,retrieve_reviewed_answers
from .site_policy import capabilities
from .llm import DecisionModel,LLMError,DEFAULT_LOCAL_MODEL

router=APIRouter(prefix='/api/extension',tags=['extension bridge'])
EXTENSION_ID=re.compile(r'^[a-p]{32}$')
_failed_pairs=[]


def extension_origin(origin:str) -> str|None:
    match=re.fullmatch(r'chrome-extension://([a-p]{32})',origin)
    return match.group(1) if match else None


def dashboard_only(request:Request):
    if extension_origin(request.headers.get('origin','')) or request.headers.get('x-forgeapply-extension'):
        raise HTTPException(403,'Open the local dashboard for pairing and revocation')


def authorized(request:Request) -> str:
    identifier=request.headers.get('x-forgeapply-extension','')
    origin=request.headers.get('origin','')
    if not EXTENSION_ID.fullmatch(identifier) or (origin and extension_origin(origin)!=identifier):
        raise HTTPException(403,'Extension identity/origin mismatch')
    auth=request.headers.get('authorization','')
    if not auth.startswith('Bearer '): raise HTTPException(401,'Pair the extension in the local dashboard')
    digest=hashlib.sha256(auth[7:].encode()).hexdigest()
    with store.conn() as db:
        row=db.execute('SELECT token_hash FROM extension_pairs WHERE extension_id=?',(identifier,)).fetchone()
    if not row or not secrets.compare_digest(row['token_hash'],digest): raise HTTPException(401,'Pairing expired or revoked; pair again')
    return identifier


def event(identifier:str,url:str,action:str,detail:str):
    with store.conn() as db:
        db.execute('INSERT INTO extension_events(extension_id,url,action,detail,at) VALUES(?,?,?,?,?)',
                   (identifier,url,action,detail,store.now()))


class PairIn(BaseModel):
    extension_id:str=Field(pattern=r'^[a-p]{32}$')
    code:str=Field(min_length=16,max_length=100)


@router.post('/pairing-code')
def pairing_code(request:Request):
    dashboard_only(request)
    code=secrets.token_urlsafe(18)
    with store.conn() as db:
        db.execute('DELETE FROM extension_pair_codes WHERE expires_at<?',(time.time(),))
        db.execute('INSERT INTO extension_pair_codes VALUES(?,?)',(hashlib.sha256(code.encode()).hexdigest(),time.time()+300))
    return {'code':code,'expires_in_seconds':300}


@router.post('/pair')
def pair(value:PairIn,request:Request):
    origin=request.headers.get('origin','')
    if origin and extension_origin(origin)!=value.extension_id: raise HTTPException(403,'Origin does not match extension')
    recent=[t for t in _failed_pairs if t>time.time()-60]
    _failed_pairs[:]=recent
    if len(recent)>=10: raise HTTPException(429,'Too many pairing failures; wait one minute')
    digest=hashlib.sha256(value.code.encode()).hexdigest()
    token=secrets.token_urlsafe(32)
    with store.conn() as db:
        row=db.execute('SELECT expires_at FROM extension_pair_codes WHERE code_hash=?',(digest,)).fetchone()
        if not row or row['expires_at']<time.time():
            _failed_pairs.append(time.time())
            raise HTTPException(401,'Invalid or expired pairing code')
        db.execute('DELETE FROM extension_pair_codes WHERE code_hash=?',(digest,))
        db.execute('INSERT INTO extension_pairs VALUES(?,?,?) ON CONFLICT(extension_id) DO UPDATE SET token_hash=excluded.token_hash,created_at=excluded.created_at',
                   (value.extension_id,hashlib.sha256(token.encode()).hexdigest(),store.now()))
    return {'token':token,'extension_id':value.extension_id}


@router.get('/sessions')
def sessions(request:Request):
    dashboard_only(request)
    with store.conn() as db: return [dict(r) for r in db.execute('SELECT extension_id,created_at FROM extension_pairs')]


@router.delete('/sessions/{identifier}')
def revoke(identifier:str,request:Request):
    dashboard_only(request)
    with store.conn() as db: db.execute('DELETE FROM extension_pairs WHERE extension_id=?',(identifier,))
    return {'ok':True}


@router.delete('/pair')
def disconnect(identifier:str=Depends(authorized)):
    with store.conn() as db: db.execute('DELETE FROM extension_pairs WHERE extension_id=?',(identifier,))
    return {'ok':True}


@router.get('/status')
def status(identifier:str=Depends(authorized)):
    profile=store.get_setting('profile',{})
    settings=store.get_setting('llm',{})
    return {'ok':True,'bridge_version':'0.4.4','extension_id':identifier,'model':settings.get('model',DEFAULT_LOCAL_MODEL),
            'profile_fields':sorted(k for k,v in profile.items() if v and not k.startswith('resume_')),
            'documents':{lang:{'available':bool(profile.get('resume_'+lang)),'filename':__import__('pathlib').Path(profile.get('resume_'+lang,'')).name}
                         for lang in ('en','it')}}


class ChoiceIn(BaseModel):
    label:str=Field(default='',max_length=500)
    value:str=Field(default='',max_length=500)
    disabled:bool=False


class AgentCandidateIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:int=Field(ge=0,le=4)
    tool:Literal['fill','add_record','advance_step','request_input','final_review']
    label:str=Field(max_length=500)


class AgentDecisionIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    url:str=Field(max_length=2000)
    stage:str=Field(default='',max_length=500)
    use_ai:bool=False
    screenshot:str=Field(default='',max_length=3_000_000)
    candidates:list[AgentCandidateIn]=Field(min_length=1,max_length=5)


@router.post('/agent/decision')
def agent_decision(value:AgentDecisionIn,identifier:str=Depends(authorized)):
    if not capabilities(value.url)['form_preparation']:raise HTTPException(403,'This site stays manual')
    if len({c.id for c in value.candidates})!=len(value.candidates):raise HTTPException(400,'Duplicate tool candidates')
    selected={'candidate_id':value.candidates[0].id,'source':'deterministic','reason':'Next permitted action'}
    if value.use_ai:
        try:
            image=None
            if value.screenshot:
                try:image=base64.b64decode(value.screenshot,validate=True)
                except ValueError:raise HTTPException(400,'Invalid screenshot encoding')
                if len(image)>2_000_000 or not image.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff')):raise HTTPException(400,'Invalid or oversized screenshot')
            result=DecisionModel.from_settings(store.get_setting('llm',{})).choose_browser_step([c.model_dump() for c in value.candidates],value.stage,screenshot=image)
            selected=result|{'source':'model'}
        except (LLMError,ValueError):selected['reason']='Model unavailable or invalid; using the next verified action'
    return selected


class AgentEventIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    tool:Literal['inspect','fill','add_record','advance_step','request_input','final_review','pause','stop']
    label:str=Field(default='',max_length=500)
    outcome:Literal['started','verified','human_review','failed','paused','stopped']


class AgentRunIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(pattern=r'^[a-f0-9-]{36}$')
    tab_id:int=Field(ge=0)
    url:str=Field(max_length=2000)
    stage:str=Field(default='',max_length=500)
    status:Literal['running','paused','stopped','interrupted','human_review','failed','review_ready']
    steps:int=Field(ge=0,le=100)
    verified:int=Field(ge=0,le=500)
    model_calls:int=Field(ge=0,le=5)
    elapsed_ms:int=Field(ge=0,le=3600000)
    events:list[AgentEventIn]=Field(default_factory=list,max_length=100)


@router.post('/agent/run')
def save_agent_run(value:AgentRunIn,identifier:str=Depends(authorized)):
    if not capabilities(value.url)['form_preparation']:raise HTTPException(403,'This site stays manual')
    parts=urlsplit(value.url)
    if parts.username or parts.password:raise HTTPException(400,'Credentials in URLs are not permitted')
    record=value.model_dump()|{'url':parts.scheme+'://'+parts.netloc+parts.path,'at':store.now()}
    runs=store.get_setting('extension_agent_runs',{})
    own=[r for r in runs.get(identifier,[]) if r['id']!=record['id']]
    runs[identifier]=(own+[record])[-20:]
    store.set_setting('extension_agent_runs',runs)
    return {'ok':True}


@router.get('/agent/run')
def list_agent_runs(identifier:str=Depends(authorized)):
    return store.get_setting('extension_agent_runs',{}).get(identifier,[])


class FieldIn(BaseModel):
    # Observations may gain optional metadata during extension updates. Mutations and model outputs stay strict.
    model_config=ConfigDict(extra='ignore')
    index:int=Field(ge=0,le=99)
    token:str=Field(min_length=1,max_length=100)
    label:str=Field(default='',max_length=500)
    name:str=Field(default='',max_length=200)
    id:str=Field(default='',max_length=200)
    type:str=Field(default='',max_length=50)
    value:str=Field(default='',max_length=8000)
    required:bool=False
    valid:bool=True
    cross_origin:bool=False
    checked:bool|None=None
    group_label:str=Field(default='',max_length=500)
    group_answered:bool=False
    options:list[ChoiceIn]=Field(default_factory=list,max_length=300)
    section:Literal['','experience','education','languages','certifications']=''
    record_index:int|None=Field(default=None,ge=0,le=19)
    record_identity:dict[str,str]=Field(default_factory=dict,max_length=3)
    record_key:str=Field(default='',max_length=100)
    bound_record:int|None=Field(default=None,ge=0,le=99)
    record_fingerprint:str=Field(default='',max_length=64)
    automation_id:str=Field(default='',max_length=300)
    automation_path:list[str]=Field(default_factory=list,max_length=8)
    phone_prefix:str=Field(default='',pattern=r'^(?:\+\d{1,4})?$')
    selection_required:bool=False
    selection_confirmed:bool|None=None
    selected_values:list[str]=Field(default_factory=list,max_length=100)


class AddControlIn(BaseModel):
    section:Literal['experience','education','languages','certifications']
    token:str=Field(min_length=1,max_length=100)
    existing_count:int=Field(ge=0,le=20)


class PlanIn(BaseModel):
    url:str=Field(max_length=2000)
    snapshot_id:str=Field(min_length=1,max_length=100)
    fields:list[FieldIn]=Field(max_length=100)
    site_authorized:bool=False
    use_ai:bool=False
    page_text:str=Field(default='',max_length=6000)
    language:Literal['auto','en','it']='auto'
    page_language:str=Field(default='',max_length=30)
    job_title:str=Field(default='',max_length=500)
    company:str=Field(default='',max_length=300)
    job_description:str=Field(default='',max_length=6000)
    add_controls:list[AddControlIn]=Field(default_factory=list,max_length=4)


@router.post('/plan')
def plan(value:PlanIn,identifier:str=Depends(authorized)):
    policy=capabilities(value.url)
    if not policy['form_preparation'] or not value.site_authorized:
        raise HTTPException(403,'Confirm this site permits assistance; restricted native platforms stay manual')
    if len({f.token for f in value.fields})!=len(value.fields) or len({f.index for f in value.fields})!=len(value.fields):
        raise HTTPException(400,'Duplicate field references')
    if len({c.section for c in value.add_controls})!=len(value.add_controls):raise HTTPException(400,'Duplicate record controls')
    # Keep only recent control structure locally for reproducible adapter debugging; never field values/answers.
    observations=store.get_setting('extension_control_diagnostics',[])
    observations.append({'url':value.url,'at':store.now(),'fields':[f.model_dump(include={'index','label','name','id','type','required','group_label','section','record_index','automation_id','automation_path'}) for f in value.fields]})
    store.set_setting('extension_control_diagnostics',observations[-5:])
    profile=store.get_setting('profile',{})
    context=store.get_setting('candidate_context',{})
    context=context|{'_form_bindings':bind_records([f.model_dump() for f in value.fields],context)}
    answers=store.scoped_answers(value.url)+store.list_answers()
    actions=[];unknown=[];unresolved=[];drafts=[];manual=[]
    choice_groups=set()
    for item in value.fields:
        field=item.model_dump()|{'url':value.url}
        display_label=normalize_label(item.label)
        if item.section and item.record_index is not None:display_label=item.section.capitalize()+' '+str(item.record_index+1)+' - '+display_label
        inferred_required=item.required or required_label(item.label)
        if item.type=='multiselect':
            if not sensitive_field(field) and not item.cross_origin:
                selected={s.casefold() for s in item.selected_values}
                missing=[s for s in verified_skills(context) if s.casefold() not in selected][:20]
                if missing:actions.append({'index':item.index,'token':item.token,'values':missing,'source':'context:verified-skills'})
                elif inferred_required and not selected:manual.append({'index':item.index,'label':normalize_label(item.label),'type':item.type,'reason':'Add a verified skill or select a choice on the page'})
            continue
        answered=(bool(item.value.strip()) and item.selection_confirmed is not False) if item.type not in ('checkbox','radio') else item.checked is True or item.group_answered
        answer=known_answer(field,profile,answers,context)
        saved_draft=answer if answer and question_kind(item.label) and answer[1]=='saved_answer' else None
        if saved_draft:answer=None
        if answer: actions.append({'token':item.token,'index':item.index,'value':answer[0],'source':answer[1]})
        elif inferred_required and (not item.valid or not answered):
            unknown.append(normalize_label(item.label) or item.name or str(item.index))
        sensitive=sensitive_field(field)
        excluded=item.type in ('file','password','checkbox','radio','submit','button') or sensitive or item.cross_origin
        review_choice=False
        if item.type in ('radio','checkbox') and inferred_required and not answered and not answer and not sensitive and not item.cross_origin:
            label=normalize_label(item.group_label if item.type=='radio' else item.label)
            group=(item.type,item.name,label)
            if label and group not in choice_groups:
                choices=[o.model_dump() for o in item.options if not o.disabled] if item.type=='radio' else [{'label':'Yes / Sì','value':'true'},{'label':'No','value':'false'}]
                if choices:
                    choice_label=item.section.capitalize()+' '+str(item.record_index+1)+' - '+label if item.section and item.record_index is not None else label
                    drafts.append({'index':item.index,'token':item.token,'label':choice_label,'value':'','kind':'missing_choice',
                                   'choices':choices,'source':'user_input','needs_review':True,'facts_used':[]})
                    choice_groups.add(group)
            review_choice=group in choice_groups
        if not answer and (not item.value or item.selection_confirmed is False) and not excluded:
            fact=None if saved_draft else known_answer(field|{'options':[],'value':''},profile,answers,context)
            record_unresolved=item.section and context['_form_bindings'].get((item.section,item.record_index)) is None and bool(verified_records(context,item.section))
            draft=draft_answer(item.label,profile,context,language=value.language,page_language=value.page_language,
                               job_title=value.job_title,company=value.company,job_description=value.job_description)
            if saved_draft:draft={'value':saved_draft[0],'kind':'approved_draft','source':'user:approved-answer','needs_review':True,'facts_used':[]}
            if fact or record_unresolved:
                drafts.append({'index':item.index,'token':item.token,'label':display_label,'value':'',
                               'kind':'selection_unresolved' if fact else 'record_unresolved','known_value':fact[0] if fact else '',
                               'optional':not inferred_required,'source':'user_input','needs_review':True,'facts_used':[],
                               **({'choices':[o.model_dump() for o in item.options if o.value and not o.disabled]} if item.options else {})})
            elif draft: drafts.append(draft|{'index':item.index,'token':item.token,'label':display_label})
            elif item.type in ('select','combobox') and item.options:
                drafts.append({'index':item.index,'token':item.token,'label':display_label,'value':'','kind':'missing_choice',
                               'optional':not inferred_required,
                               'choices':[o.model_dump() for o in item.options if o.value and not o.disabled],
                               'source':'user_input','needs_review':True,'facts_used':[]})
            else:
                drafts.append({'index':item.index,'token':item.token,'label':display_label,'value':'','input_type':item.type,
                               'optional':not inferred_required,
                               'kind':'missing_fact','source':'user_input','needs_review':True,'facts_used':[]})
            if not draft and not needs_exact_fact(item.label) and not item.section and item.type not in ('number','date','month'):
                unresolved.append({k:field[k] for k in ('index','label','name','id','type','required','options')})
        if sensitive:
            manual.append({'index':item.index,'label':normalize_label(item.label),'type':item.type,'optional':not inferred_required,
                           'answered':answered and item.valid,
                           'reason':'Review this personal or legal field on the page; existing site defaults are not verified facts'})
        elif re.search(r'birth|nascita',item.label,re.I) and answered:
            manual.append({'index':item.index,'label':normalize_label(item.label),'type':item.type,'optional':not inferred_required,
                           'reason':'Check the existing value on the page; residence does not establish birthplace'})
        elif inferred_required and excluded and not answered and not answer and not review_choice:
            manual.append({'index':item.index,'label':normalize_label(item.label),'type':item.type,
                           'reason':'Choose a document on the page' if item.type=='file' else 'Complete this control or sensitive question on the page'})
        elif item.selection_confirmed is False and item.value and not answer:
            manual.append({'index':item.index,'label':display_label,'type':item.type,'optional':not inferred_required,
                           'reason':'Typed text is not a committed selection. Choose a matching catalog result on the page'})
        elif inferred_required and answered and not item.valid and not answer:
            manual.append({'index':item.index,'label':normalize_label(item.label),'type':item.type,
                           'reason':'Review the validation error or choose the search result on the page'})
    proposals=[];ai_error=None
    model_called=False
    if value.use_ai and unresolved:
        model_called=True
        config=store.get_setting('llm',{})
        try:
            model=DecisionModel.from_settings(config)
            evidence=evidence_catalog(profile,context)+retrieve_reviewed_answers(unresolved,store.list_answers(),profile)
            result=model.propose_grounded_answers(unresolved,evidence,
                language=response_language(page_language=value.page_language,preferred=value.language),page_text=value.page_text,allow_fact_references=True)
            proposals=[{'field_index':a['field_index'],'value':a['value'],'evidence_ids':a['evidence_ids'],'fact_id':a.get('fact_id'),'needs_review':True}
                       for a in result['answers'] if a['value'].strip() and not a['needs_information']]
            for proposal in proposals:
                item=next(f for f in value.fields if f.index==proposal['field_index'])
                existing=next((d for d in drafts if d['index']==item.index),None)
                entry={'index':item.index,'token':item.token,'label':normalize_label(item.label),'value':proposal['value'],
                       'kind':'model_proposal','source':'AI proposal - verify every claim',
                       'fact_id':proposal.get('fact_id'),
                       'facts_used':[e for e in evidence if e['id'] in proposal['evidence_ids']],'needs_review':True}
                if existing: drafts.remove(existing)
                drafts.append(entry)
        except (LLMError,ValueError) as exc: ai_error=str(exc)
    structure_actions=[]
    for control in value.add_controls:
        conflict=any(index is None for (section,row),index in context['_form_bindings'].items() if section==control.section)
        needed=min(10,len(verified_records(context,control.section)))-control.existing_count
        if needed>0 and not conflict:structure_actions.append({'token':control.token,'section':control.section,'count':needed})
    event(identifier,value.url,'prepare',f'{len(actions)} known fields; {len(unknown)} unresolved; AI proposals {len(proposals)}')
    record_bindings=[{'token':f.token,'record_key':f.record_key,'section':f.section,
                      'bound_record':index,'record_fingerprint':record_fingerprint(record_data(context,f.section,index))}
                     for f in value.fields if f.record_key and (index:=context['_form_bindings'].get((f.section,f.record_index))) is not None]
    return {'snapshot_id':value.snapshot_id,'url':value.url,'actions':actions,'unknown':unknown,'record_bindings':record_bindings,
            'proposals':proposals,'drafts':drafts,'manual':manual,'structure_actions':structure_actions,'ai_error':ai_error,'model_called':model_called,'policy':policy,
            'language':response_language(page_language=value.page_language,preferred=value.language),
            'note':'Known facts fill directly. Read and confirm longer answers before they are filled.'}


class ReviewedAnswer(BaseModel):
    model_config=ConfigDict(extra='forbid')
    index:int=Field(ge=0,le=99)
    token:str=Field(min_length=1,max_length=100)
    value:str=Field(min_length=1,max_length=8000)
    remember:bool=False
    fact_id:str|None=Field(default=None,max_length=100,pattern=r'^profile\.(?:'+('|'.join(sorted(store.PROFILE_REFERENCE_FIELDS)))+r')$')


class ReviewedPlanIn(PlanIn):
    answers:list[ReviewedAnswer]=Field(min_length=1,max_length=100)
    reviewed:bool=False


@router.post('/reviewed-plan')
def reviewed_plan(value:ReviewedPlanIn,identifier:str=Depends(authorized)):
    if not value.reviewed or not value.site_authorized or not capabilities(value.url)['form_preparation']:
        raise HTTPException(403,'Review the displayed answers before filling')
    actions=[];remembered=0
    reviewed_profile=store.get_setting('profile',{})
    if len({a.token for a in value.answers})!=len(value.answers): raise HTTPException(400,'Duplicate answers')
    if len({f.index for f in value.fields})!=len(value.fields) or len({f.token for f in value.fields})!=len(value.fields): raise HTTPException(400,'Duplicate field references')
    for answer in value.answers:
        item=next((f for f in value.fields if f.index==answer.index and f.token==answer.token),None)
        if item is None: raise HTTPException(400,'Answer does not match the inspected form')
        if answer.fact_id and str(reviewed_profile.get(answer.fact_id.split('.',1)[1],''))!=answer.value:
            raise HTTPException(409,'The profile fact changed. Prepare again and review the current value.')
        if item.type in ('password','file','submit','button') or item.cross_origin or sensitive_field(item.model_dump()):
            raise HTTPException(403,'Sensitive declarations and unsupported controls must be completed manually')
        if item.type in ('checkbox','radio'):
            if item.checked or item.group_answered:raise HTTPException(409,'This choice is already answered; inspect and edit it on the page')
            if item.type=='radio':
                choice=matching_choice(answer.value,[o.model_dump() for o in item.options])
                target=next((f for f in value.fields if f.type=='radio' and f.group_label==item.group_label and f.name==item.name and choice and f.value==choice['value']),None)
                if target is None:raise HTTPException(400,'Choose an option from this inspected group')
                actions.append({'index':target.index,'token':target.token,'value':'true','source':'user-reviewed-answer'})
            elif answer.value in ('true','false'):
                actions.append({'index':item.index,'token':item.token,'value':answer.value,'source':'user-reviewed-answer'})
            else:raise HTTPException(400,'Choose Yes or No explicitly')
        else:
            if item.value: raise HTTPException(409,'Field already contains an answer; inspect and edit it on the page')
            chosen=matching_choice(answer.value,[o.model_dump() for o in item.options]) if item.type in ('select','combobox') and item.options else None
            if item.type in ('select','combobox') and item.options and not chosen:raise HTTPException(400,'Choose an inspected dropdown option')
            actions.append({'index':item.index,'token':item.token,'value':chosen['label'] if chosen else answer.value,'source':'user-reviewed-answer'})
    # Validate the entire request before persisting any explicitly remembered answer.
    context=store.get_setting('candidate_context',{})
    bindings=bind_records([f.model_dump() for f in value.fields],context)
    context_changed=False
    scoped=store.get_setting('application_specific_answers',{});scoped_changed=False
    for answer in value.answers:
        item=next(f for f in value.fields if f.index==answer.index)
        label=normalize_label(item.group_label if item.type=='radio' else item.label)
        semantic_value=answer.value
        if item.type in ('select','combobox','radio') and item.options:
            semantic_value=matching_choice(answer.value,[o.model_dump() for o in item.options])['label']
        profile=store.get_setting('profile',{})
        reference=answer.fact_id if answer.fact_id in {'profile.'+key for key in store.PROFILE_REFERENCE_FIELDS} else None
        if reference and str(profile.get(reference.split('.',1)[1],''))!=answer.value:reference=None
        if answer.remember and reference:
            store.upsert_answer('^'+re.escape(label)+'$',answer.value,True,source='user:reviewed-model-profile-binding',
                                fact_path=reference,scope_host=urlsplit(value.url).hostname or '')
            remembered+=1;continue
        if answer.remember and item.section and (index:=bindings.get((item.section,item.record_index))) is not None:
            record=record_storage(context,item.section,index)
            remembered_value=semantic_value
            record.setdefault('form_answers',{})[record_question_key(label)]={'value':remembered_value,'source':'user:extension-reviewed-record','verified_at':store.now()}
            context_changed=True;remembered+=1
        job_specific=question_kind(label)=='motivation' or application_specific_question(label) or bool(re.search(r'why|perch[eé]|company|azienda|this (?:role|position)|quest[oa] (?:ruolo|posizione)',label,re.I))
        can_remember=bool(label) and not item.section and not job_specific
        if answer.remember and job_specific:
            key=store.normalized_url(value.url);pattern='^'+re.escape(label)+'$'
            rows=[r for r in scoped.get(key,[]) if r['pattern']!=pattern]
            rows.append({'pattern':pattern,'answer':semantic_value,'enabled':True,'source':'user:reviewed-application-answer','verified_at':store.now()})
            scoped[key]=rows;scoped_changed=True
            remembered+=1
        pattern='^'+re.escape(label)+'$'
        # A birth date/place is explicit personal data, never a reusable general screening answer.
        can_remember=can_remember and not re.search(r'birth|nascita',label,re.I)
        if answer.remember and can_remember and len(pattern)<=500:
            remembered_value=semantic_value
            promotion=known_answer({'label':label,'value':'','type':'text'},
                                   {k:semantic_value for k in store.PROFILE_FIELDS if not k.startswith('resume_')},[])
            path=promotion[1].replace('profile:','profile.') if promotion and promotion[1].startswith('profile:') else ''
            if path.removeprefix('profile.') not in store.PROFILE_BINDABLE_FIELDS:path=''
            store.upsert_answer(pattern,remembered_value,True,source='user:extension-reviewed-exact',fact_path=path,
                                scope_host='' if path else urlsplit(value.url).hostname or '');remembered+=1
            if promotion and promotion[1].startswith('profile:'):
                key=promotion[1].split(':',1)[1]
                if key in store.PROFILE_FIELDS:store.save_profile({key:semantic_value},source='user:extension-reviewed-exact')
    if context_changed:store.set_setting('candidate_context',context)
    if scoped_changed:store.set_setting('application_specific_answers',scoped)
    event(identifier,value.url,'reviewed_fill',f'{len(actions)} reviewed answers; {remembered} exact factual answers remembered')
    return {'url':value.url,'snapshot_id':value.snapshot_id,'actions':actions,'remembered':remembered}


@router.get('/control-diagnostics')
def control_diagnostics(request:Request):
    dashboard_only(request)
    return store.get_setting('extension_control_diagnostics',[])


class LetterIn(BaseModel):
    language:Literal['en','it']='en'
    job_title:str=Field(default='',max_length=500)
    company:str=Field(default='',max_length=300)
    description:str=Field(default='',max_length=6000)
    use_ai:bool=False


def refine_document(draft:dict,value:LetterIn,kind:str) -> dict:
    """Optional model wording/tailoring stays an editable proposal with an intact deterministic fallback."""
    if not value.use_ai:return draft
    evidence=evidence_catalog(store.get_setting('profile',{}),store.get_setting('candidate_context',{}))
    question={'index':0,'label':f'Prepare a complete {kind} in {value.language}. Preserve the exact verified facts in this baseline. '
              'Translate prose naturally and emphasize relevant verified skills. Never add claims, dates, qualifications or employer praise. '
              'For a CV retain contact details, section headings and readable plain-text layout.',
              'baseline_document':draft['value']}
    try:
        model=DecisionModel.from_settings(store.get_setting('llm',{}))
        model.ollama_options['num_predict']=model.document_num_predict
        result=model.propose_grounded_answers([question],evidence,
            language=value.language,page_text=' '.join((value.job_title,value.company,value.description)))
        answer=next((a for a in result['answers'] if a['field_index']==0 and a['value'].strip() and not a['needs_information']),None)
        if answer:
            return draft|{'value':answer['value'],'source':'model_proposal','facts_used':[e for e in evidence if e['id'] in answer['evidence_ids']],
                          'note':'AI wording requires review; evidence citations do not prove every claim.'}
    except (LLMError,ValueError) as exc:
        return draft|{'ai_error':str(exc),'ai_error_code':getattr(exc,'code','model_error'),'note':'AI could not refine this draft; using verified facts.'}
    return draft


@router.post('/motivation-letter')
def motivation_letter(value:LetterIn,identifier:str=Depends(authorized)):
    draft=draft_answer('Motivation letter',store.get_setting('profile',{}),store.get_setting('candidate_context',{}),
                       language=value.language,job_title=value.job_title,company=value.company,job_description=value.description)
    if not draft: raise HTTPException(400,'Add verified education, experience or skills to your profile before drafting a letter')
    return refine_document(draft,value,'motivation letter')


@router.post('/cv-draft')
def cv_draft(value:LetterIn,identifier:str=Depends(authorized)):
    draft=draft_resume(store.get_setting('profile',{}),store.get_setting('candidate_context',{}),value.language,
                       job_description=value.job_title+' '+value.description)
    if not draft:raise HTTPException(400,'Add verified education, experience or skills before drafting a CV')
    return refine_document(draft,value,'CV')


class DocumentPDFIn(BaseModel):
    text:str=Field(min_length=1,max_length=30000)
    kind:Literal['cv','letter']='cv'
    reviewed:bool=False


@router.post('/document-pdf')
def document_pdf(value:DocumentPDFIn,identifier:str=Depends(authorized)):
    if not value.reviewed:raise HTTPException(403,'Review the document text before exporting')
    import base64
    from .document_text import render_reviewed_pdf
    try:content=render_reviewed_pdf(value.text,value.kind)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    return {'base64':base64.b64encode(content).decode('ascii'),'filename':'forgeapply-'+value.kind+'.pdf'}


def local_ollama_endpoint() -> str:
    config=store.get_setting('llm',{})
    url=config.get('base_url') if config.get('provider')=='ollama' else ''
    if url:
        parsed=urlsplit(url)
        if parsed.scheme in ('http','https') and not parsed.username and not parsed.password and parsed.hostname in ('localhost','127.0.0.1','::1'):
            return url.rstrip('/')
    return 'http://127.0.0.1:11434'


@router.get('/local-models')
def local_models(identifier:str=Depends(authorized)):
    try:
        response=httpx.get(local_ollama_endpoint()+'/api/tags',timeout=3)
        response.raise_for_status()
        models=[m['name'] for m in response.json().get('models',[])]
    except (httpx.HTTPError,ValueError,KeyError):
        return {'models':[],'selected':store.get_setting('llm',{}).get('model',DEFAULT_LOCAL_MODEL),'available':False}
    return {'models':models,'selected':store.get_setting('llm',{}).get('model',DEFAULT_LOCAL_MODEL),'available':True}


@router.post('/model-test')
def test_selected_model(identifier:str=Depends(authorized)):
    try:return DecisionModel.from_settings(store.get_setting('llm',{})).test_response()
    except (LLMError,ValueError) as exc:return {'ok':False,'detail':str(exc),'code':getattr(exc,'code','configuration')}


class LocalModelIn(BaseModel):
    model:str=Field(min_length=1,max_length=200)


@router.post('/local-model')
def choose_local_model(value:LocalModelIn,identifier:str=Depends(authorized)):
    available=local_models(identifier)
    if value.model not in available['models']: raise HTTPException(400,'Choose an installed Ollama model; no model will be downloaded automatically')
    previous=store.get_setting('llm',{})
    history=store.get_setting('llm_selection_history',[])
    history.append({'settings':previous,'at':store.now(),'source':'extension-user-selection'})
    store.set_setting('llm_selection_history',history[-20:])
    store.set_setting('llm',previous|{'provider':'ollama','model':value.model,'base_url':local_ollama_endpoint(),'api_key_env':'',
                                     'allow_remote':False})
    return {'model':value.model,'source':'explicit-user-selection'}


class JobImport(BaseModel):
    url:str=Field(max_length=2000)
    title:str=Field(min_length=1,max_length=500)
    company:str=Field(default='',max_length=300)
    location:str=Field(default='',max_length=300)
    description:str=Field(default='',max_length=20000)
    origin_url:str=Field(default='',max_length=2000)


@router.post('/jobs')
def save_job(value:JobImport,identifier:str=Depends(authorized)):
    policy=capabilities(value.url)
    if not policy['url_import']: raise HTTPException(400,'Use an http(s) job URL without credentials')
    try:
        jid,created=store.add_job(title=value.title,url=value.url,company=value.company,location=value.location,
            description=value.description,source='extension:'+policy['platform'],
            origin_url=value.origin_url,
            language=discovery.detect_language(value.title+' '+value.description),
            score=discovery.score_job(value.title,value.location,value.description))
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    event(identifier,value.url,'import','created' if created else 'deduplicated')
    return {'id':jid,'created':created,'policy':policy}


@router.post('/match')
def match(value:JobImport,identifier:str=Depends(authorized)):
    context=store.get_setting('candidate_context',{})
    profile=store.get_setting('profile',{})
    skills={skill.casefold() for skill in verified_skills(context)}
    text=value.description.casefold()
    matched=sorted(skill for skill in skills if re.search(r'(?<!\w)'+re.escape(skill)+r'(?!\w)',text))
    warnings=[]
    if not discovery.ITALY_KEYWORDS.search(value.location): warnings.append('Italy eligibility is not verified from this location, including remote listings')
    italian=context.get('languages',{}).get('Italian','')
    if re.search(r'(italian|italiano).{0,35}(b2|c1|fluent|fluente|mandatory|obbligatori)',text) and 'beginner' in italian.casefold():
        warnings.append('Italian proficiency requirement may exceed the verified beginner level')
    if re.search(r'visa|sponsor|work authorization',text) and not profile.get('work_authorized'):
        warnings.append('Work authorization/sponsorship must be verified; residence is insufficient')
    return {'heuristic_score':discovery.score_job(value.title,value.location,value.description),'matched_verified_skills':matched,
            'warnings':warnings,'eligibility':'requires_review','note':'Text matching is prioritization, not proof of eligibility'}


@router.get('/activity')
def activity(identifier:str=Depends(authorized)):
    with store.conn() as db:
        return [dict(r) for r in db.execute('SELECT url,action,detail,at FROM extension_events WHERE extension_id=? ORDER BY id DESC LIMIT 20',(identifier,))]


class ManualQuestion(BaseModel):
    question:str=Field(min_length=1,max_length=2000)


@router.post('/answer')
def manual_answer(value:ManualQuestion,identifier:str=Depends(authorized)):
    answer=known_answer({'label':value.question,'value':'','type':'text'},store.get_setting('profile',{}),store.list_answers())
    return {'answer':answer[0] if answer else '', 'source':answer[1] if answer else None,
            'needs_information':answer is None,'needs_review':True,
            'note':'Copy a verified answer manually. Unknown or sensitive declarations require your confirmed response; no site interaction occurs.'}
