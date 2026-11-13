"""Local-only ForgeApply API and dashboard."""
from __future__ import annotations
import csv
import io
import json
import mimetypes
import os
import hashlib
import zipfile
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from . import store, discovery
from .browser import browser, SCREEN_DIR
from .config import CV_DIR, PORT
from .browser_tools import BrowserToolCall
from .llm import DecisionModel,DEFAULT_LOCAL_MODEL
from urllib.parse import urlsplit
from .extension_api import router as extension_router,extension_origin

@asynccontextmanager
async def lifespan(app:FastAPI):
    try: yield
    finally: await asyncio.to_thread(browser.close)

app=FastAPI(title='ForgeApply',version='1.0.0',docs_url='/api/docs',lifespan=lifespan)
store.init_db()
app.include_router(extension_router)

@app.middleware('http')
async def local_request_guard(request,call_next):
    # Block cross-site drive-by POSTs to a local privileged browser controller.
    from fastapi.responses import JSONResponse
    allowed_hosts = {'127.0.0.1', 'localhost', '::1', '[::1]'}
    if request.url.hostname not in allowed_hosts:
        return JSONResponse({'detail':'Local Host header required'},status_code=403)
    origin=request.headers.get('origin','')
    extension_id=extension_origin(origin)
    bridge=request.url.path.startswith('/api/extension/')
    if extension_id and not bridge:
        return JSONResponse({'detail':'Extensions must use the authenticated bridge'},status_code=403)
    if bridge and request.method=='OPTIONS':
        if not extension_id: return JSONResponse({'detail':'Extension origin required'},status_code=403)
        return Response(status_code=204,headers={'Access-Control-Allow-Origin':origin,
            'Access-Control-Allow-Methods':'GET,POST,DELETE,OPTIONS',
            'Access-Control-Allow-Headers':'Content-Type,Authorization,X-ForgeApply-Extension',
            'Vary':'Origin'})
    if request.method not in ('GET','HEAD','OPTIONS'):
        if request.headers.get('sec-fetch-site') == 'cross-site' and not (bridge and extension_id):
            return JSONResponse({'detail':'Cross-origin control is disabled'},status_code=403)
        if origin and not (bridge and extension_id):
            try: parsed=urlsplit(origin)
            except ValueError: return JSONResponse({'detail':'Invalid origin'},status_code=403)
            if parsed.scheme != request.url.scheme or parsed.netloc != request.url.netloc:
                return JSONResponse({'detail':'Same-origin control required'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    if bridge and extension_id:
        response.headers['Access-Control-Allow-Origin']=origin
        response.headers['Vary']='Origin'
    return response
STATIC=Path(__file__).resolve().parent.parent/'static'

class JobIn(BaseModel):
    title:str; url:str; company:str=''; location:str=''; description:str=''; source:str='manual'; posted_at:str|None=None
    origin_url:str=''

class StatusIn(BaseModel):
    status:str; note:str=''; acknowledged:bool=False

class ProfileIn(BaseModel):
    data:dict

class CandidateContextIn(BaseModel):
    education:list[dict]=Field(default_factory=list,max_length=20)
    experience:list[dict]=Field(default_factory=list,max_length=30)
    skills:dict[str,list[str]]=Field(default_factory=dict)
    languages:dict[str,str]=Field(default_factory=dict)
    preferences:dict=Field(default_factory=dict)
    source:str=Field(default='user:local-dashboard',max_length=300)

class AnswerIn(BaseModel):
    pattern:str; answer:str; enabled:bool=True; source:str='user:local-dashboard'

class BoardIn(BaseModel):
    ats:Literal['greenhouse','lever','ashby']; slug:str

class BrowserNavigate(BaseModel):
    url:str

class BrowserFill(BaseModel):
    index:int; value:str; snapshot_id:str|None=None

class BrowserClick(BaseModel):
    kind:Literal['next','easy_apply','other']; text:str=''

class BrowserSubmit(BaseModel):
    job_id:int; approved:bool=False

class JobReference(BaseModel):
    job_id:int

class AgentPrepareIn(BaseModel):
    job_id:int
    use_ai:bool=False
    use_vision:bool=False
    max_steps:int=Field(default=8,ge=1,le=12)
    max_seconds:int=Field(default=120,ge=5,le=300)
    max_model_requests:int=Field(default=2,ge=0,le=5)
    allow_uploads:bool=False

class AutoFillIn(BaseModel):
    use_ai:bool=False; use_vision:bool=False

class LLMSettings(BaseModel):
    provider:Literal['ollama','openai']='ollama'; model:str=DEFAULT_LOCAL_MODEL; base_url:str=''
    allow_remote:bool=False
    think:bool=False
    num_ctx:int=Field(default=8192,ge=1024,le=131072)
    num_predict:int=Field(default=768,ge=64,le=8192)
    temperature:float=Field(default=0,ge=0,le=2)

class OCRIn(BaseModel):
    mode:Literal['local','vision']='local'


def wrap(fn,*args,**kwargs):
    try: return fn(*args,**kwargs)
    except Exception as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc

@app.get('/',response_class=HTMLResponse)
def index(): return (STATIC/'index.html').read_text(encoding='utf-8')

@app.get('/static/{name}')
def static(name:str):
    if name not in {'app.js','style.css'}: raise HTTPException(404)
    return FileResponse(STATIC/name)

@app.get('/api/jobs')
def jobs(status:str='all',search:str='',limit:int=500): return store.list_jobs(status,search,limit)

@app.post('/api/jobs')
def create_job(job:JobIn):
    d=job.model_dump(); d['score']=discovery.score_job(d['title'],d['location'],d['description'])
    d['language']=discovery.detect_language(d['title']+' '+d['description'])
    jid,created=wrap(store.add_job,**d)
    return {'id':jid,'created':created}

@app.put('/api/jobs/{job_id}/status')
def status(job_id:int,value:StatusIn):
    wrap(store.set_status,job_id,value.status,value.note,acknowledged=value.acknowledged)
    return {'ok':True}

@app.get('/api/stats')
def stats(): return store.stats()

@app.get('/api/jobs/{job_id}/browser-run')
def browser_run(job_id:int): return store.get_browser_run(job_id) or {}

@app.get('/api/profile')
def profile(): return store.get_setting('profile',{})

@app.get('/api/profile/provenance')
def profile_provenance(): return store.get_setting('profile_provenance',{})

@app.put('/api/profile')
def save_profile(value:ProfileIn):
    # Resume paths are controlled by the upload endpoint, never arbitrary API paths.
    store.save_profile({k:v for k,v in value.data.items() if not k.startswith('resume_')})
    return {'ok':True}

@app.get('/api/candidate-context')
def candidate_context(): return store.get_setting('candidate_context',{})

@app.put('/api/candidate-context')
def save_candidate_context(value:CandidateContextIn):
    data=value.model_dump()
    data['verified_at']=store.now()
    store.set_setting('candidate_context',data)
    return {'ok':True}

@app.post('/api/resumes/{lang}')
async def resume(lang:Literal['en','it'],file:UploadFile=File(...)):
    safe_name=Path(file.filename or '').name
    ext=Path(safe_name).suffix.lower()
    if ext not in {'.pdf','.docx'}: raise HTTPException(400,'Use PDF or DOCX resumes')
    contents=await file.read(8_000_001)
    if len(contents)>8_000_000: raise HTTPException(413,'Maximum resume size is 8MB')
    if ext=='.pdf' and not contents.startswith(b'%PDF-'):
        raise HTTPException(400,'Invalid PDF content')
    if ext=='.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(contents)) as archive:
                if not {'[Content_Types].xml','word/document.xml'}.issubset(archive.namelist()):
                    raise ValueError('Missing DOCX document')
        except (zipfile.BadZipFile, ValueError):
            raise HTTPException(400,'Invalid DOCX content')
    digest=hashlib.sha256(contents).hexdigest()
    filename=f'CV_{lang}_{digest[:12]}{ext}'
    path=CV_DIR/filename
    path.write_bytes(contents)
    store.save_profile({f'resume_{lang}':str(path)},source='user:resume-upload')
    artifacts=store.get_setting('resume_artifacts',{})
    artifacts[lang]={'path':str(path),'sha256':digest,
                     'language':lang,'uploaded_at':store.now(),'original_name':safe_name}
    store.set_setting('resume_artifacts',artifacts)
    return {'ok':True,'filename':filename}

@app.get('/api/answers')
def answers(): return store.list_answers()

@app.post('/api/answers')
def save_answer(value:AnswerIn):
    wrap(store.upsert_answer,value.pattern,value.answer,value.enabled,value.source)
    return {'ok':True}

@app.get('/api/resumes/{lang}/text')
def resume_text(lang:Literal['en','it']):
    from .document_text import extract_text
    profile=store.get_setting('profile',{})
    return wrap(extract_text,Path(profile.get('resume_'+lang,'')))

@app.delete('/api/answers/{aid}')
def delete_answer(aid:int): store.delete_answer(aid);return {'ok':True}

@app.get('/api/boards')
def boards(): return store.get_setting('boards',{'greenhouse':[],'lever':[],'ashby':[]})

@app.post('/api/boards')
def add_board(b:BoardIn):
    if not b.slug.replace('-','').replace('_','').replace('.','').isalnum(): raise HTTPException(400,'Invalid slug')
    boards=store.get_setting('boards',{}); slugs=boards.setdefault(b.ats,[])
    if b.slug not in slugs: slugs.append(b.slug)
    store.set_setting('boards',boards);return {'ok':True}

@app.delete('/api/boards/{ats}/{slug}')
def remove_board(ats:str,slug:str):
    boards=store.get_setting('boards',{})
    boards[ats]=[x for x in boards.get(ats,[]) if x!=slug]
    store.set_setting('boards',boards);return {'ok':True}

@app.post('/api/discover')
def discover(): return discovery.sync_boards()

@app.post('/api/import')
async def import_jobs(file:UploadFile=File(...)):
    from tempfile import NamedTemporaryFile
    data=await file.read(4_000_001)
    if len(data)>4_000_000: raise HTTPException(413,'Maximum CSV size is 4MB')
    with NamedTemporaryFile(suffix='.csv',delete=False) as f:
        path=Path(f.name); f.write(data)
    try: return wrap(discovery.import_csv,path)
    finally: path.unlink(missing_ok=True)

@app.get('/api/export')
def export():
    jobs=store.list_jobs(limit=2000)
    if not jobs: return Response('id,title,company,url,status\n',media_type='text/csv')
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=list(jobs[0]));writer.writeheader();writer.writerows(jobs)
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="forgeapply-jobs.csv"'})

@app.get('/api/llm')
def llm(): return store.get_setting('llm',LLMSettings().model_dump())

@app.put('/api/llm')
def save_llm(value:LLMSettings):
    if value.base_url and not value.base_url.startswith(('http://','https://')): raise HTTPException(400,'Invalid base URL')
    store.set_setting('llm',value.model_dump());return {'ok':True}

@app.post('/api/llm/health')
def llm_health():
    cfg=store.get_setting('llm',{})
    def check():
        model=DecisionModel.from_settings(cfg)
        return model.health()
    return wrap(check)

@app.post('/api/browser/open')
def browser_open(value:BrowserNavigate): return wrap(browser.navigate,value.url)

@app.get('/api/browser/state')
def browser_state(): return wrap(browser.snapshot)

@app.post('/api/browser/autofill')
def browser_autofill(value:AutoFillIn): return wrap(browser.autofill,value.use_ai,value.use_vision)

@app.post('/api/browser/fill')
def browser_fill(value:BrowserFill): return wrap(browser.fill,value.index,value.value,value.snapshot_id)

@app.post('/api/browser/tool')
def browser_tool(value:BrowserToolCall): return wrap(browser.execute_tool,value)

@app.post('/api/browser/click')
def browser_click(value:BrowserClick): return wrap(browser.click,value.kind,value.text)

@app.post('/api/browser/resume/{lang}')
def browser_resume(lang:Literal['en','it']): return wrap(browser.upload_resume,lang)

@app.post('/api/browser/submit')
def browser_submit(value:BrowserSubmit): return wrap(browser.submit,value.job_id,value.approved)

@app.post('/api/browser/approve-destination')
def approve_destination(value:JobReference): return wrap(browser.approve_destination,value.job_id)

@app.get('/api/browser/screenshot')
def browser_screenshot():
    path=wrap(browser.screenshot)
    return FileResponse(path,media_type='image/png',headers={'Cache-Control':'no-store'})

@app.get('/api/health')
def health(): return {'ok':True,'version':'1.0.0'}


def main():
    import uvicorn
    from .config import PORT
    # Deliberately bind loopback: personal resumes, cookies and candidate data stay local.
    uvicorn.run('forgeapply.app:app',host='127.0.0.1',port=PORT,reload=False)

if __name__=='__main__':main()

@app.post('/api/browser/agent/prepare')
def agent_prepare(value:AgentPrepareIn):
    return wrap(browser.agent_prepare,value.job_id,value.use_ai,value.use_vision,value.max_steps,value.max_seconds,value.max_model_requests,value.allow_uploads)

@app.post('/api/browser/agent/cancel')
def agent_cancel(): return browser.cancel()

@app.post('/api/browser/ocr')
def browser_ocr(value:OCRIn): return wrap(browser.ocr,value.mode)
