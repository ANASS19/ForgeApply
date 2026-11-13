"""Narrow authenticated MV3 bridge. No arbitrary local files or managed-browser commands."""
import hashlib
import re
import secrets
import time
from typing import Literal
from urllib.parse import urlsplit
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field,ConfigDict
from . import store,discovery
from .form_logic import known_answer,SENSITIVE_QUESTION
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
    return {'ok':True,'extension_id':identifier,'model':settings.get('model',DEFAULT_LOCAL_MODEL),
            'profile_fields':sorted(k for k,v in profile.items() if v and not k.startswith('resume_')),
            'documents':{lang:{'available':bool(profile.get('resume_'+lang)),'filename':__import__('pathlib').Path(profile.get('resume_'+lang,'')).name}
                         for lang in ('en','it')}}


class FieldIn(BaseModel):
    model_config=ConfigDict(extra='forbid')
    index:int=Field(ge=0,le=99)
    token:str=Field(min_length=1,max_length=100)
    label:str=Field(default='',max_length=500)
    name:str=Field(default='',max_length=200)
    id:str=Field(default='',max_length=200)
    type:str=Field(default='',max_length=50)
    value:str=Field(default='',max_length=1000)
    required:bool=False
    valid:bool=True
    cross_origin:bool=False


class PlanIn(BaseModel):
    url:str=Field(max_length=2000)
    snapshot_id:str=Field(min_length=1,max_length=100)
    fields:list[FieldIn]=Field(max_length=100)
    site_authorized:bool=False
    use_ai:bool=False
    page_text:str=Field(default='',max_length=6000)


@router.post('/plan')
def plan(value:PlanIn,identifier:str=Depends(authorized)):
    policy=capabilities(value.url)
    if not policy['form_preparation'] or not value.site_authorized:
        raise HTTPException(403,'Confirm this site permits assistance; restricted native platforms stay manual')
    if len({f.token for f in value.fields})!=len(value.fields): raise HTTPException(400,'Duplicate field references')
    profile=store.get_setting('profile',{})
    answers=store.list_answers()
    actions=[];unknown=[];unresolved=[]
    for item in value.fields:
        field=item.model_dump()
        answer=known_answer(field,profile,answers)
        if answer: actions.append({'token':item.token,'index':item.index,'value':answer[0],'source':answer[1]})
        elif item.required and not item.valid:
            unknown.append(item.label or item.name or str(item.index))
        if not answer and not item.value and item.type not in ('file','password','checkbox','radio','submit','button') and not SENSITIVE_QUESTION.search(item.label):
            unresolved.append(field)
    proposals=[];ai_error=None
    if value.use_ai and unresolved:
        config=store.get_setting('llm',{})
        try:
            model=DecisionModel.from_settings(config)
            facts={k:v for k,v in profile.items() if v and not k.startswith('resume_')}
            facts['candidate_context']=store.get_setting('candidate_context',{})
            result=model.decide_form_action(value.page_text,unresolved,facts)
            proposals=[a|{'needs_review':True} for a in result['actions']]
        except (LLMError,ValueError) as exc: ai_error=str(exc)
    event(identifier,value.url,'prepare',f'{len(actions)} known fields; {len(unknown)} unresolved; AI proposals {len(proposals)}')
    return {'snapshot_id':value.snapshot_id,'url':value.url,'actions':actions,'unknown':unknown,
            'proposals':proposals,'ai_error':ai_error,'policy':policy,'note':'AI proposals are never part of the automatic fill plan'}


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
    skills={skill.casefold() for group in context.get('skills',{}).values() for skill in group}
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
