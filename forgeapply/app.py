"""Local-only ForgeApply API and dashboard."""
from __future__ import annotations
import csv
import io
import json
import mimetypes
import os
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from . import store, discovery
from .browser import browser, SCREEN_DIR
from .config import CV_DIR

app=FastAPI(title='ForgeApply',version='1.0.0',docs_url='/api/docs')
store.init_db()

@app.middleware('http')
async def local_request_guard(request,call_next):
    # Block cross-site drive-by POSTs to a local privileged browser controller.
    from fastapi.responses import JSONResponse
    origin=request.headers.get('origin','')
    if request.method not in ('GET','HEAD','OPTIONS') and origin:
        from urllib.parse import urlparse
        host=urlparse(origin).hostname
        if host not in ('127.0.0.1','localhost'):
            return JSONResponse({'detail':'Cross-origin control is disabled'},status_code=403)
    return await call_next(request)
STATIC=Path(__file__).resolve().parent.parent/'static'

class JobIn(BaseModel):
    title:str; url:str; company:str=''; location:str=''; description:str=''; source:str='manual'; posted_at:str|None=None

class StatusIn(BaseModel):
    status:str; note:str=''

class ProfileIn(BaseModel):
    data:dict

class AnswerIn(BaseModel):
    pattern:str; answer:str; enabled:bool=True

class BoardIn(BaseModel):
    ats:Literal['greenhouse','lever','ashby']; slug:str

class BrowserNavigate(BaseModel):
    url:str

class BrowserFill(BaseModel):
    index:int; value:str

class BrowserClick(BaseModel):
    kind:Literal['next','easy_apply','other']; text:str=''

class BrowserSubmit(BaseModel):
    job_id:int; approved:bool=False

class AgentPrepareIn(BaseModel):
    job_id:int
    use_ai:bool=True
    use_vision:bool=False
    max_steps:int=Field(default=8,ge=1,le=12)

class AutoFillIn(BaseModel):
    use_ai:bool=True; use_vision:bool=False

class LLMSettings(BaseModel):
    provider:Literal['ollama','openai']='ollama'; model:str='qwen3:4b'; base_url:str=''


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
    wrap(store.set_status,job_id,value.status,value.note)
    return {'ok':True}

@app.get('/api/stats')
def stats(): return store.stats()

@app.get('/api/profile')
def profile(): return store.get_setting('profile',{})

@app.put('/api/profile')
def save_profile(value:ProfileIn):
    existing=store.get_setting('profile',{})
    permitted=set(existing)
    existing.update({k:v for k,v in value.data.items() if k in permitted and isinstance(v,str)})
    store.set_setting('profile',existing)
    return {'ok':True}

@app.post('/api/resumes/{lang}')
async def resume(lang:Literal['en','it'],file:UploadFile=File(...)):
    safe_name=Path(file.filename or '').name
    ext=Path(safe_name).suffix.lower()
    if ext not in {'.pdf','.docx'}: raise HTTPException(400,'Use PDF or DOCX resumes')
    contents=await file.read(8_000_001)
    if len(contents)>8_000_000: raise HTTPException(413,'Maximum resume size is 8MB')
    filename=f'CV_{lang}{ext}'
    path=CV_DIR/filename
    path.write_bytes(contents)
    profile=store.get_setting('profile',{}); profile[f'resume_{lang}']=str(path)
    store.set_setting('profile',profile)
    return {'ok':True,'filename':filename}

@app.get('/api/answers')
def answers(): return store.list_answers()

@app.post('/api/answers')
def save_answer(value:AnswerIn):
    wrap(store.upsert_answer,value.pattern,value.answer,value.enabled)
    return {'ok':True}

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
def llm(): return store.get_setting('llm',{'provider':'ollama','model':'qwen3:4b','base_url':''})

@app.put('/api/llm')
def save_llm(value:LLMSettings):
    if value.base_url and not value.base_url.startswith(('http://','https://')): raise HTTPException(400,'Invalid base URL')
    store.set_setting('llm',value.model_dump());return {'ok':True}

@app.post('/api/browser/open')
def browser_open(value:BrowserNavigate): return wrap(browser.navigate,value.url)

@app.get('/api/browser/state')
def browser_state(): return wrap(browser.snapshot)

@app.post('/api/browser/autofill')
def browser_autofill(value:AutoFillIn): return wrap(browser.autofill,value.use_ai,value.use_vision)

@app.post('/api/browser/fill')
def browser_fill(value:BrowserFill): return wrap(browser.fill,value.index,value.value)

@app.post('/api/browser/click')
def browser_click(value:BrowserClick): return wrap(browser.click,value.kind,value.text)

@app.post('/api/browser/resume/{lang}')
def browser_resume(lang:Literal['en','it']): return wrap(browser.upload_resume,lang)

@app.post('/api/browser/submit')
def browser_submit(value:BrowserSubmit): return wrap(browser.submit,value.job_id,value.approved)

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
    return wrap(browser.agent_prepare,value.job_id,value.use_ai,value.use_vision,value.max_steps)

@app.post('/api/browser/ocr')
def browser_ocr(): return wrap(browser.ocr)
