"""Human-visible local Playwright browser with deterministic form filling + optional AI fallback.

Never submit silently: final submission requires user click, or an explicit per-job
approved flag, and is disabled for domains where automation is prohibited.
"""
from __future__ import annotations
import asyncio
import json
import re
import threading
import uuid
import hashlib
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Error as PlaywrightError
from .config import ROOT
from .store import get_setting, list_answers, set_status, get_job
from .llm import DecisionModel, LLMError
from .browser_tools import BrowserToolCall, BrowserTarget
from . import store

BROWSER_DIR = ROOT / 'browser_profile'
SCREEN_DIR = ROOT / 'screenshots'
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

FIELD_SCRIPT = '''() => Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]),textarea,select,[contenteditable=true],[role=combobox]:not(input):not(select)'))
 .filter(e => {const r=e.getBoundingClientRect();return !e.disabled && (e.type==='file' || (r.width>0 && r.height>0))})
 .slice(0,100).map((e,i) => {
 if (!e.dataset.forgeapplyField) e.dataset.forgeapplyField=Array.from(crypto.getRandomValues(new Uint32Array(4)),v=>v.toString(16)).join('-');
 const id=e.id||'';
 const labelText=node=>{if(!node)return '';const copy=node.cloneNode(true);copy.querySelectorAll('input,select,textarea,button').forEach(c=>c.remove());return copy.textContent.trim();};
 const labelledBy=(e.getAttribute('aria-labelledby')||'').split(/\\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' ').trim();
 const label=labelText(id && document.querySelector('label[for="'+CSS.escape(id)+'"]')) ||
  labelText(e.closest('label')) || e.getAttribute('aria-label') || labelledBy || e.getAttribute('placeholder') ||
  e.closest('fieldset')?.querySelector('legend')?.innerText || '';
 const custom=e.getAttribute('role')==='combobox' && !['INPUT','SELECT'].includes(e.tagName);
 const customValue=e.getAttribute('aria-valuetext')||e.dataset.value||'';
 return {index:i,token:e.dataset.forgeapplyField,tag:e.tagName.toLowerCase(),type:custom?'combobox':e.getAttribute('type')||'',name:e.name||'',
 id:id,label:(label||'').trim().slice(0,230),value:e.type==='password'?'':(custom?(e.getAttribute('aria-valuetext')||e.dataset.value||''):(e.value||e.isContentEditable&&e.innerText||'')).slice(0,140),
 checked:!!e.checked,valid:custom?(!(e.getAttribute('aria-required')==='true')||!!customValue):(e.validity?e.validity.valid:true),validation_message:e.validationMessage||'',
 required:e.required||e.getAttribute('aria-required')==='true',options:e.tagName==='SELECT'?Array.from(e.options).map(o=>({value:o.value,text:o.text})):[]}
 })'''

# These require deliberate user interaction, including when a broad saved regex matches.
SENSITIVE_QUESTION = re.compile(
    r'visa|sponsor|work.?authori[sz]|right to work|permesso|criminal|disab|convict|'
    r'certif(?:y|ico)|declar|attest|consent|agree|privacy|gender|ethnic|veteran|'
    r'salary|compensation|notice period|availability|start date|immediately', re.I)
CONFIRMATION = re.compile(r'application (has been )?(submitted|received)|thank you for (applying|your application)|candidatura (inviata|ricevuta)|application successfully',re.I)


class BrowserManager:
    def __init__(self, *, headless:bool=False, user_data_dir:Path|None=None):
        self.headless=headless
        self.user_data_dir=user_data_dir or BROWSER_DIR
        self._thread=None
        self._loop=None
        self._ready=threading.Event()
        self._playwright=None
        self._context=None
        self._page=None
        self.last_error=None
        self._lock=threading.Lock()
        self._fields=[]
        self._snapshot_id=None
        self._snapshot_url=None
        self._job_id=None
        self._operation_lock=None
        self._field_frames={}
        self._allowed_origin=None
        self._review_context=None
        self._trace=[]
        self._cancel=threading.Event()
        self._resume_uploaded=None
        self._approved_origins=set()

    def start(self):
        with self._lock:
            if not (self._thread and self._thread.is_alive()):
                self.last_error=None
                self._ready.clear()
                self._thread=threading.Thread(target=self._run_loop,daemon=True,name='ForgeApply Browser')
                self._thread.start()
        if not self._ready.wait(timeout=45): raise RuntimeError('Browser startup timed out')
        if self.last_error: raise RuntimeError(self.last_error)

    def _run_loop(self):
        self._loop=asyncio.new_event_loop()
        self._operation_lock=asyncio.Lock()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._init())
        except Exception as exc:
            self.last_error=str(exc)
            if self._playwright:
                self._loop.run_until_complete(self._playwright.stop())
        finally:
            self._ready.set()
        if not self.last_error:
            self._loop.run_forever()
        self._loop.close()

    async def _init(self):
        self._playwright=await async_playwright().start()
        self._context=await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir), headless=self.headless, viewport={'width':1440,'height':900},
            accept_downloads=True)
        self._page=self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._page.set_default_timeout(6000)

    def call(self, coroutine, timeout=100):
        try:
            self.start()
        except Exception:
            coroutine.close()
            raise
        async def serialized():
            async with self._operation_lock:
                return await coroutine
        f=asyncio.run_coroutine_threadsafe(serialized(),self._loop)
        try:
            return f.result(timeout=timeout)
        except FutureTimeoutError:
            f.cancel()
            raise TimeoutError('Browser operation timed out; inspect current state before retrying')

    async def _shutdown(self):
        if self._context: await self._context.close()
        if self._playwright: await self._playwright.stop()

    async def _ensure_page(self):
        """Recover only on a new observation/navigation request, never replay a mutation."""
        if self._page is not None and not self._page.is_closed(): return
        self._job_id=None
        self._review_context=None
        self._fields=[]
        try:
            pages=self._context.pages
            self._page=pages[0] if pages else await self._context.new_page()
        except Exception:
            if self._playwright: await self._playwright.stop()
            await self._init()

    def close(self):
        if self._loop and self._loop.is_running():
            self.call(self._shutdown())
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)
        self._context=None
        self._fields=[]
        self._job_id=None
        self._review_context=None
        self._allowed_origin=None

    async def _navigate(self,url):
        await self._ensure_page()
        parsed=urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Only http(s) URLs without embedded credentials are permitted')
        self._job_id=None
        self._review_context=None
        self._allowed_origin=(parsed.scheme,parsed.netloc)
        self._approved_origins={self._allowed_origin}
        self._resume_uploaded=None
        for attempt in range(2):
            try:
                await self._page.goto(url,wait_until='domcontentloaded',timeout=35000)
                break
            except PlaywrightError:
                # Only retry initial read-only navigation, never a form click or submission.
                if attempt: raise
                await self._ensure_page()
        return await self._snapshot()

    def navigate(self,url): return self.call(self._navigate(url))

    def _destination_allowed(self):
        parsed=urlparse(self._page.url)
        return (parsed.scheme,parsed.netloc) in self._approved_origins

    def approve_destination(self,job_id:int):
        async def approve():
            if self._job_id!=job_id: raise ValueError('Prepare the selected job before approving its destination')
            parsed=urlparse(self._page.url)
            if parsed.scheme not in ('http','https') or not parsed.hostname: raise ValueError('Invalid destination')
            self._approved_origins.add((parsed.scheme,parsed.netloc))
            self._allowed_origin=(parsed.scheme,parsed.netloc)
            self._progress(job_id,'approved_destination','user_approval',parsed.netloc)
            return {'approved_origin':f'{parsed.scheme}://{parsed.netloc}','job_id':job_id}
        return self.call(approve())

    async def _snapshot(self):
        await self._ensure_page()
        page=self._page
        try: text=(await page.locator('body').inner_text(timeout=7000))[:12000]
        except Exception: text=''
        fields=[]
        frames=[]
        self._field_frames={}
        for frame_index,frame in enumerate(page.frames[:21]):
            frames.append({'index':frame_index,'url':frame.url,'name':frame.name})
            if frame_index:
                try: text+='\n'+(await frame.locator('body').inner_text(timeout=1000))[:3000]
                except Exception: continue
            try: frame_fields=await frame.evaluate(FIELD_SCRIPT)
            except Exception:
                if frame_index==0: raise
                continue
            for field in frame_fields:
                if len(fields)>=100: break
                field['index']=len(fields)
                field['frame_index']=frame_index
                field['cross_origin']=bool(frame_index and frame.url not in ('about:blank','about:srcdoc') and urlparse(frame.url).netloc!=urlparse(page.url).netloc)
                fields.append(field)
                self._field_frames[field['token']]=frame
        self._fields=fields
        self._snapshot_id=uuid.uuid4().hex
        self._snapshot_url=page.url
        form_actions=await page.locator('form').evaluate_all('(forms)=>forms.map(f=>({action:f.action,method:f.method}))')
        alerts=await page.locator('[role=alert]:visible,[aria-live=assertive]:visible,.field-error:visible').all_text_contents()
        page_errors=[text.strip()[:500] for text in alerts if re.search(r'error|invalid|required|reject|fail|cannot|errore|obbligatori|non valid|rifiutat',text,re.I)]
        return {'url':page.url,'title':await page.title(),'text':text[:12000],'fields':fields,'snapshot_id':self._snapshot_id,'frames':frames,'form_actions':form_actions,
                'tabs':[{'index':i,'url':p.url,'active':p==page} for i,p in enumerate(self._context.pages)] if self._context else [],
                'validation_errors':[{'index':f['index'],'label':f['label'],'message':f['validation_message']} for f in fields if not f['valid']],
                'page_errors':page_errors,
                'buttons':(await page.locator('button,input[type=submit],a[role=button]').all_text_contents())[:50]}

    def snapshot(self): return self.call(self._snapshot())

    async def _screenshot(self):
        path=SCREEN_DIR/'latest.png'
        await self._page.screenshot(path=str(path),full_page=False,animations='disabled')
        return str(path)

    def screenshot(self): return self.call(self._screenshot())

    async def _fill(self, i:int, value:str, snapshot_id:str|None=None):
        if snapshot_id is not None and snapshot_id != self._snapshot_id:
            raise ValueError('Stale form snapshot; inspect the page again')
        if self._page.url != self._snapshot_url or i<0 or i>=len(self._fields):
            raise ValueError('Stale or invalid field index; inspect the page again')
        field=self._fields[i]
        frame=self._field_frames.get(field['token'])
        if frame is None or frame.is_detached(): raise ValueError('Form frame changed; inspect again')
        element=frame.locator(f'[data-forgeapply-field="{field["token"]}"]')
        if await element.count()!=1 or not await element.is_enabled():
            raise ValueError('Form changed; inspect the page again')
        live=next((f for f in await frame.evaluate(FIELD_SCRIPT) if f['token']==field['token']),None)
        if live is None or any(live.get(k)!=field.get(k) for k in ('label','name','id','type','tag')):
            raise ValueError('Field meaning changed; inspect the page again')
        tag=await element.evaluate('(e)=>e.tagName.toLowerCase()')
        typ=(await element.get_attribute('type') or '').lower()
        role=await element.get_attribute('role')
        if typ in ('file','password'):
            raise ValueError('Use resume upload for files; password fields require user input')
        if role=='combobox' and tag not in ('input','select'):
            await element.click()
            options=frame.get_by_role('option',name=value,exact=True)
            if await options.count()!=1: raise ValueError('Dropdown option missing or ambiguous; select manually')
            await options.click()
            selected=await element.evaluate("e=>e.getAttribute('aria-valuetext')||e.dataset.value||e.innerText")
            if value.casefold() not in selected.casefold(): raise RuntimeError('Custom dropdown did not retain the selected value')
        elif typ in ('checkbox','radio'):
            if value.lower() not in ('yes','true','1','checked','on','no','false','0','unchecked','off'):
                raise ValueError('Checkbox/radio response must be an explicit boolean')
            truth=value.lower() in ('yes','true','1','checked','on')
            if truth: await element.check()
            elif typ=='checkbox': await element.uncheck()
            else: raise ValueError('Choose a different radio option instead of unchecking it')
        elif tag=='select':
            try: await element.select_option(label=value)
            except Exception: await element.select_option(value=value)
        else:
            await element.fill(value)
        if typ not in ('checkbox','radio') and role!='combobox':
            actual=await element.evaluate("e=>e.isContentEditable?e.innerText:e.value")
            if tag=='select':
                labels=await element.evaluate("e=>Array.from(e.selectedOptions).map(o=>o.textContent)")
                if actual!=value and value not in labels: raise RuntimeError('Selection did not retain the requested option')
            elif actual!=value: raise RuntimeError('Field did not retain the filled value')
        return {'field_index':i,'value':value,'ok':True}

    def fill(self,i,value,snapshot_id=None): return self.call(self._fill(int(i),str(value),snapshot_id))

    def _target_locator(self,target:BrowserTarget):
        if target.field_index is not None:
            if target.field_index>=len(self._fields): raise ValueError('Inspect fields before acting')
            field=self._fields[target.field_index]
            frame=self._field_frames.get(field['token'])
            if frame is None or frame.is_detached(): raise ValueError('Form frame changed; inspect again')
            return frame.locator(f'[data-forgeapply-field="{field["token"]}"]')
        frames=self._page.frames
        if target.frame_index>=len(frames): raise ValueError('Frame no longer exists; inspect again')
        frame=frames[target.frame_index]
        return frame.get_by_label(target.label,exact=True) if target.label is not None else frame.get_by_role(target.role,name=target.name,exact=True)

    async def _tool(self,call:BrowserToolCall):
        """One explicit bounded tool action, shared by UI/API and deterministic execution."""
        if call.snapshot_id is not None and call.snapshot_id!=self._snapshot_id:
            raise ValueError('Stale form snapshot; inspect again')
        if call.action=='inspect': return await self._snapshot()
        if call.action in ('extract_text','validation'):
            snap=await self._snapshot()
            return {'text':snap['text']} if call.action=='extract_text' else {'validation_errors':snap['validation_errors']}
        if call.action=='wait_navigation':
            await self._page.wait_for_url(call.url,timeout=call.timeout_ms,wait_until='domcontentloaded')
            return await self._snapshot()
        if call.action=='switch_tab':
            pages=self._context.pages
            if call.tab_index>=len(pages): raise ValueError('Tab no longer exists')
            page=pages[call.tab_index]
            parsed=urlparse(page.url)
            if (parsed.scheme,parsed.netloc)!=self._allowed_origin:
                raise PermissionError('Open this destination explicitly before switching to it')
            self._page=page
            self._job_id=None
            self._review_context=None
            await page.bring_to_front()
            return await self._snapshot()
        if call.action=='screenshot': return {'path':await self._screenshot()}
        if call.action=='accessibility':
            # aria_snapshot is a semantic accessibility representation, not raw HTML.
            return {'frames':[{'index':i,'tree':(await frame.locator('body').aria_snapshot())[:16000]}
                              for i,frame in enumerate(self._page.frames[:21])]}
        if call.action=='navigate':
            parsed=urlparse(call.url)
            if (parsed.scheme,parsed.netloc)!=self._allowed_origin:
                raise PermissionError('Tool navigation is limited to the opened origin; open a new URL explicitly')
            return await self._navigate(call.url)
        if call.action=='upload': return await self._upload_resume(call.language)
        if call.action=='scroll':
            await self._page.mouse.wheel(0,call.distance*(1 if call.direction=='down' else -1))
            return await self._snapshot()
        locator=self._target_locator(call.target)
        if await locator.count()!=1: raise ValueError('Target is missing or ambiguous; inspect again')
        if call.action=='wait':
            await locator.wait_for(state='visible',timeout=call.timeout_ms)
            return await self._snapshot()
        if call.action=='hover':
            await locator.hover(timeout=call.timeout_ms)
        elif call.action in ('fill','select','check','type_text','clear','press_key','double_click'):
            typ=(await locator.get_attribute('type') or '').lower()
            if typ in ('password','file','submit','button','hidden'):
                raise PermissionError('Use the dedicated file control; passwords and action controls require manual input')
            if call.action=='fill':
                await locator.fill(call.value,timeout=call.timeout_ms)
                actual=await locator.evaluate('e=>e.isContentEditable?e.innerText:e.value')
                if actual!=call.value: raise RuntimeError('Field did not retain the requested value')
            elif call.action=='clear': await locator.clear(timeout=call.timeout_ms)
            elif call.action=='type_text': await locator.press_sequentially(call.value,timeout=call.timeout_ms)
            elif call.action=='double_click':
                if await locator.get_attribute('role') in ('button','link') or await locator.evaluate('e=>e.tagName') not in ('INPUT','TEXTAREA'):
                    raise PermissionError('Double click is limited to text inputs')
                await locator.dblclick(timeout=call.timeout_ms)
            elif call.action=='press_key':
                if call.value not in ('Tab','Escape','ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Home','End','Control+A','Backspace'):
                    raise PermissionError('Key is not allowed; form submission requires the approval control')
                await locator.press(call.value,timeout=call.timeout_ms)
            elif call.action=='select':
                try: await locator.select_option(label=call.value,timeout=call.timeout_ms)
                except Exception: await locator.select_option(value=call.value,timeout=call.timeout_ms)
                selected=await locator.evaluate('e=>Array.from(e.selectedOptions).flatMap(o=>[o.value,o.textContent])')
                if call.value not in selected: raise RuntimeError('Option selection was not retained')
            elif call.action=='check':
                if call.value.lower() not in ('true','false'): raise ValueError('Check value must be true or false')
                await locator.set_checked(call.value.lower()=='true',timeout=call.timeout_ms)
                if await locator.is_checked()!=(call.value.lower()=='true'): raise RuntimeError('Checked state was not retained')
        elif call.action=='click':
            role=call.target.role
            if role not in ('combobox','option'):
                # Inspect actual semantics even when selected by label or field index.
                text=(await locator.inner_text()).strip()
                if text.lower() not in ('next','continue','review','avanti','continua','rivedi','back','previous','cancel','close','indietro','annulla'):
                    raise PermissionError('Only known navigation and dropdown controls may be clicked by general tools')
            await locator.click(timeout=call.timeout_ms)
        return await self._snapshot()

    def execute_tool(self,call:BrowserToolCall):
        async def run():
            started=time.monotonic()
            result=await self._tool(call)
            if self._job_id:
                self._progress(self._job_id,'tool',call.action,f'{time.monotonic()-started:.3f}s')
            return result
        return self.call(run())

    def cancel(self):
        self._cancel.set()
        return {'requested':True,'note':'Preparation stops at the next observation boundary; no automatic submission'}

    async def _upload_resume(self,lang='en'):
        if self._job_id and not self._destination_allowed(): raise PermissionError('Review and approve this application destination before uploading documents')
        profile=get_setting('profile',{})
        path=Path(profile.get('resume_it' if lang=='it' else 'resume_en','')).expanduser()
        if not path.is_file(): raise FileNotFoundError('Configure an existing resume file in the Profile tab')
        candidates=[]
        for frame in self._page.frames:
            if frame.url not in ('about:blank','about:srcdoc') and urlparse(frame.url).netloc!=urlparse(self._page.url).netloc: continue
            for element in await frame.locator('input[type=file]').element_handles():
                if await element.is_enabled(): candidates.append(element)
        if not candidates: raise RuntimeError('No enabled file upload input found on this page')
        if len(candidates)>1:
            labelled=[]
            for element in candidates:
                label=await element.evaluate("e => [e.name,e.id,e.getAttribute('aria-label'),e.labels && Array.from(e.labels).map(l=>l.innerText).join(' ')].join(' ')")
                if re.search(r'\b(cv|resume|curriculum)\b',label,re.I): labelled.append(element)
            if len(labelled)!=1: raise RuntimeError('Multiple upload controls; select the CV control manually')
            candidates=labelled
        await candidates[0].set_input_files(str(path))
        attached=await candidates[0].evaluate('e=>Array.from(e.files).map(f=>({name:f.name,size:f.size}))')
        if not any(f['name']==path.name and f['size']==path.stat().st_size for f in attached):
            raise RuntimeError('Browser did not retain the resume attachment')
        self._resume_uploaded={'language':lang,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'filename':path.name}
        return {'uploaded':path.name,'language':lang,'verified_input_attachment':True}

    def upload_resume(self,lang='en'): return self.call(self._upload_resume(lang))

    async def _click(self,kind, text=''):
        if kind not in ('next','easy_apply','other'): raise ValueError('Unknown click kind')
        if kind=='easy_apply':
            pattern=re.compile(r'Easy Apply|Candidatura semplice|Candidati facilmente',re.I)
        elif kind=='next':
            pattern=re.compile(r'^(Next|Continue|Review|Avanti|Continua|Rivedi)$',re.I)
        else:
            if not text or len(text)>130: raise ValueError('Provide button text')
            if text.lower() not in ('back','previous','cancel','close','indietro','annulla'):
                raise ValueError('Only navigation controls are allowed; final submission requires explicit approval')
            pattern=re.compile('^'+re.escape(text)+'$',re.I)
        candidates=self._page.get_by_role('button',name=pattern)
        if await candidates.count()==0:
            candidates=self._page.get_by_role('link',name=pattern)
        count=await candidates.count()
        if count==0: raise RuntimeError('Button/link not found')
        if count!=1: raise ValueError('Navigation control is ambiguous; choose it manually')
        before=self._fingerprint(await self._snapshot())
        await candidates.first.click(timeout=6000)
        # Observe bounded state changes rather than assuming every click progressed.
        for _ in range(30):
            await self._page.wait_for_timeout(100)
            snap=await self._snapshot()
            if self._fingerprint(snap)!=before:
                snap['transition_verified']=True
                return snap
        snap['transition_verified']=False
        return snap

    def click(self,kind,text=''): return self.call(self._click(kind,text))

    @staticmethod
    def _fingerprint(snap:dict) -> str:
        data={'url':snap['url'],'text':snap.get('text',''),
              'form_actions':snap.get('form_actions',[]),'buttons':snap.get('buttons',[]),
              'fields':[(f.get('label'),f.get('value'),f.get('checked'),f.get('valid')) for f in snap['fields']]}
        return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

    def _progress(self,job_id:int,phase:str,action:str,detail:str='') -> None:
        self._trace.append({'at':store.now(),'phase':phase,'action':action,'detail':detail})
        store.save_browser_run(job_id,phase,self._page.url,self._trace)

    async def _ready_for_review(self,job_id:int,trace:list):
        snap=await self._snapshot()
        self._review_context={'job_id':job_id,'url':snap['url'],'fingerprint':self._fingerprint(snap)}
        self._progress(job_id,'human_review','stop','Final review; no submission performed')
        set_status(job_id,'prepared','Reached final review; no submission performed')
        return {'status':'ready_for_review','trace':trace,'snapshot':snap}

    async def _submit(self,job_id, approved):
        if not approved: raise PermissionError('Final submission requires explicit approval')
        job=get_job(job_id)
        if not job: raise KeyError('Job not found')
        if job['status']=='submitted': raise ValueError('Application already submitted; will not repeat')
        if self._job_id!=job_id: raise ValueError('Prepare this job in the browser before approving submission')
        if not self._destination_allowed(): raise PermissionError('Application destination has not been approved')
        snap=await self._snapshot()
        review=self._review_context
        if not review or review['job_id']!=job_id or review['url']!=snap['url'] or review['fingerprint']!=self._fingerprint(snap):
            raise PermissionError('Application page changed or has not reached review; prepare and review again')
        if CONFIRMATION.search(snap['text']):
            raise PermissionError('A confirmation already appears on this page; verify manually before attempting any submission')
        # No automated final clicks on LinkedIn, where third-party automation may violate site rules.
        host=(urlparse(self._page.url).hostname or '').lower()
        if host.endswith('linkedin.com') or host.endswith('indeed.com'):
            raise PermissionError('Click final Submit yourself on LinkedIn/Indeed and confirm in tracker')
        buttons=self._page.get_by_role('button',name=re.compile(r'^(Submit application|Submit|Send application|Invia candidatura|Apply)$',re.I))
        if await buttons.count()!=1: raise RuntimeError('Final submission control is missing or ambiguous')
        store.begin_submission(job_id,self._page.url)
        await buttons.first.click(timeout=8000)
        await self._page.wait_for_timeout(1400)
        snap=await self._snapshot()
        text=snap['text'].lower()
        verified=bool(CONFIRMATION.search(text))
        store.finish_submission(job_id,verified,{'url':snap['url'],'confirmation_text':snap['text'][:2000],
                                'company':job['company'],'title':job['title'],
                                'resume':self._resume_uploaded or {},
                                'trace':self._trace,'at':store.now()})
        if verified:
            set_status(job_id,'submitted','Verified post-submission confirmation on ' + self._page.url,acknowledged=True)
        else:
            set_status(job_id,'blocked','Submission clicked; confirmation not detected. Verify manually.')
        return {'submitted_verified':verified,'snapshot':snap}

    def submit(self,job_id,approved=False): return self.call(self._submit(job_id,approved))

    async def _agent_prepare(self, job_id:int, use_ai:bool=False, use_vision:bool=False, max_steps:int=8,
                             max_seconds:int=120,max_model_requests:int=2,allow_uploads:bool=False):
        """Navigate and prepare one application; never performs final submission."""
        job=get_job(job_id)
        if not job: raise KeyError('Job not found')
        if job['status']=='submitted': raise ValueError('Application already submitted; will not repeat')
        if self._job_id!=job_id:
            await self._navigate(job['url'])
            self._job_id=job_id
            set_status(job_id,'opened','Browser opened application URL')
        previous_run=store.get_browser_run(job_id)
        self._trace=(previous_run or {}).get('trace',[])
        self._review_context=None
        self._cancel.clear()
        started=time.monotonic()
        model_requests=0
        trace=[]
        previous=''
        for step in range(min(max_steps,12)):
            if self._cancel.is_set() or time.monotonic()-started>=max_seconds:
                set_status(job_id,'blocked','Preparation paused or time limit reached; inspect and resume')
                return {'status':'paused','trace':trace}
            snap=await self._snapshot()
            self._progress(job_id,'observe','inspect',f"Step {step+1}; {len(snap['fields'])} fields")
            if not self._destination_allowed():
                set_status(job_id,'blocked','Unexpected destination; review the URL and approve it before sending candidate information')
                return {'status':'needs_destination_approval','reason':'Application moved to a new origin; review and approve the destination','trace':trace,'snapshot':snap}
            text=snap['text'].lower()
            if any(word in text for word in ('verify you are human','captcha','unusual activity')):
                set_status(job_id,'blocked','Manual account verification required')
                return {'status':'blocked','reason':'Verification/CAPTCHA must be completed manually','trace':trace}
            if ('sign in' in text[:700] or 'log in' in text[:700]) and len(snap['fields'])<=3:
                set_status(job_id,'blocked','Please sign in to the site in the visible browser')
                return {'status':'needs_login','trace':trace}
            if not snap['fields']:
                final_buttons=self._page.get_by_role('button',name=re.compile(r'^(Submit application|Submit|Send application|Invia candidatura|Apply)$',re.I))
                if await final_buttons.count():
                    return await self._ready_for_review(job_id,trace)
                # Common Easy Apply start: do not click unrelated Apply links blindly.
                try:
                    await self._click('easy_apply')
                    trace.append('Clicked Easy Apply')
                    continue
                except Exception:
                    set_status(job_id,'blocked','No supported form or Easy Apply button found')
                    return {'status':'blocked','reason':'No supported form detected','trace':trace}
            # Attach the correct CV when this application exposes a file upload.
            upload_fields=[f for f in snap['fields'] if f['type']=='file']
            if upload_fields:
                if not allow_uploads:
                    set_status(job_id,'blocked','Review and explicitly allow CV upload for this job')
                    return {'status':'needs_document_approval','reason':'CV upload requires approval for this job','trace':trace}
                lang=job.get('language') if job.get('language') in ('en','it') else 'en'
                try:
                    uploaded=await self._upload_resume(lang)
                    trace.append('Uploaded CV: '+uploaded['uploaded'])
                    self._progress(job_id,'act','upload_resume',lang)
                except Exception as exc:
                    set_status(job_id,'blocked','Resume upload needs review: '+str(exc)[:200])
                    return {'status':'needs_resume','language':lang,'reason':str(exc),'trace':trace}
            use_model=use_ai and model_requests<max_model_requests
            self._progress(job_id,'plan','prepare_fields','Verified profile/saved answers first; model proposals require review')
            result=await self._autofill(use_model,use_vision)
            if use_model: model_requests+=1
            self._progress(job_id,'verify','autofill',f"Filled {len(result['filled'])}; unknown {len(result['unknown'])}; errors {len(result['errors'])}")
            trace.append(f"Filled {len(result['filled'])} fields; unknown {len(result['unknown'])}")
            if self._cancel.is_set():
                set_status(job_id,'blocked','Preparation paused by user; inspect and resume')
                return {'status':'paused','trace':trace}
            observed=await self._snapshot()
            if not result['errors'] and not result.get('suggestions') and any(f.get('token') not in {old.get('token') for old in snap['fields']} for f in observed['fields']):
                self._progress(job_id,'observe','dynamic_fields','New controls appeared; inspect again before navigation')
                continue
            if result['unknown'] or result['errors'] or result.get('suggestions'):
                set_status(job_id,'blocked','Form questions require review: '+', '.join(result['unknown'])[:500])
                return {'status':'needs_answers','unknown':result['unknown'],'errors':result['errors'],'trace':trace}
            # Stop before ANY final submission action, even if it looks like the Next button.
            next_buttons=self._page.get_by_role('button',name=re.compile(r'^(Next|Continue|Review|Avanti|Continua|Rivedi)$',re.I))
            if await next_buttons.count()==0:
                return await self._ready_for_review(job_id,trace)
            fingerprint=str([(f['label'],f['value']) for f in (await self._snapshot())['fields']])
            if fingerprint==previous:
                set_status(job_id,'blocked','Form has not progressed; check validation messages')
                return {'status':'stalled','trace':trace}
            previous=fingerprint
            try:
                self._progress(job_id,'act','next','Known Next / Review control')
                transition=await self._click('next')
                trace.append('Clicked Next / Review')
                if not transition.get('transition_verified'):
                    set_status(job_id,'blocked','No verified page transition; inspect validation messages')
                    return {'status':'stalled','reason':'No verified state change after navigation','trace':trace,'snapshot':transition}
            except Exception as exc:
                set_status(job_id,'blocked','Next step requires review: '+str(exc)[:200])
                return {'status':'blocked','reason':str(exc),'trace':trace}
        set_status(job_id,'blocked','Reached maximum navigation steps; please inspect browser')
        return {'status':'max_steps','trace':trace}

    def agent_prepare(self,job_id,use_ai=False,use_vision=False,max_steps=8,max_seconds=120,max_model_requests=2,allow_uploads=False):
        async def run():
            try:
                result=await asyncio.wait_for(self._agent_prepare(int(job_id),use_ai,use_vision,max_steps,max_seconds,max_model_requests,allow_uploads),timeout=max_seconds)
                self._progress(int(job_id),result['status'],'stop',result.get('reason',''))
                result['journal']=self._trace
                return result
            except Exception as exc:
                job=get_job(job_id)
                if job and job['status']!='submitted':
                    set_status(job_id,'blocked',f'Browser preparation failed ({type(exc).__name__}); inspect and resume')
                    self._progress(int(job_id),'failed','stop',type(exc).__name__)
                raise
        return self.call(run(),timeout=360)

    def ocr(self,mode='local'):
        """Vision-model OCR without requiring an external OCR executable."""
        path=self.screenshot()
        if mode=='local':
            from .ocr import local_ocr
            return local_ocr(Path(path))
        if mode!='vision': raise ValueError('Choose local or vision OCR')
        cfg=get_setting('llm',{})
        model=DecisionModel(cfg.get('provider','ollama'),cfg.get('model','qwen3:4b'),cfg.get('base_url') or None,
                            allow_remote=cfg.get('allow_remote',False))
        img=Path(path).read_bytes()
        return model.json('You are an OCR assistant. Transcribe all visible on-screen text faithfully. '
                          'Return JSON with text and unclear_segments fields. Do not guess unclear text.',
                          'Transcribe this screenshot to text.',screenshot=img)

    def autofill(self, use_ai=False, use_vision=False):
        return self.call(self._autofill(use_ai,use_vision),timeout=150)

    async def _autofill(self,use_ai,use_vision):
        if self._job_id and not self._destination_allowed(): raise PermissionError('Review and approve this destination before filling candidate information')
        snap=await self._snapshot()
        profile=get_setting('profile',{})
        answers=[a for a in list_answers() if a['enabled']]
        plan=[]; unresolved=[]; taken=set(); suggestions=[]
        patterns=[
          (r'first[ _-]?name|given name|nome',profile.get('first_name')),
          (r'last[ _-]?name|surname|cognome',profile.get('last_name')),
          (r'e[ _-]?mail(?: address)?|indirizzo email',profile.get('email')),
          (r'(?:phone|mobile|telefono|cellulare)(?: number)?',profile.get('phone')),
          (r'linkedin(?: (?:url|profile))?',profile.get('linkedin')),
          (r'github(?: (?:url|profile))?',profile.get('github')),
          (r'portfolio|website|sito web',profile.get('portfolio')),
          (r'(?:current )?(?:city|città|comune|location)',profile.get('city')),
          (r'(?:current )?(?:country|paese|nazione)(?: of residence)?',profile.get('country')),
          (r'(?:years(?: of)? (?:ai|artificial intelligence) experience|ai experience(?: \(years\))?)',profile.get('years_ai')),
          (r'(?:years(?: of)? python experience|python experience(?: \(years\))?)',profile.get('years_python')),
        ]
        for f in snap['fields']:
            i=f['index']; label=f.get('label') or f.get('name') or f.get('id') or ''
            if f.get('cross_origin'): continue
            if f['type'] in ('file','password','hidden','submit','button','checkbox','radio') or f['value']:
                continue
            if SENSITIVE_QUESTION.search(label):
                continue
            answer=None
            for saved in answers:
                try:
                    if re.search(saved['pattern'],label,re.I): answer=saved['answer']; break
                except re.error: continue
            if answer is None:
                for pattern,value in patterns:
                    if value and re.fullmatch(pattern,label.strip().rstrip(':* ').strip(),re.I): answer=str(value);break
            if answer is not None:
                plan.append(BrowserToolCall(action='fill',target=BrowserTarget(field_index=i),value=answer));taken.add(i)
            # Required fields are checked after deterministic and AI fill plans complete.
        ai_fields=[f for f in snap['fields'] if f['index'] not in taken and not f['value']
                   and not f.get('cross_origin')
                   and f['type'] not in ('file','password','checkbox','radio','submit','button')
                   and not SENSITIVE_QUESTION.search(f.get('label','')+' '+f.get('name',''))]
        if use_ai and ai_fields:
            cfg=get_setting('llm',{})
            try:
                model=DecisionModel(cfg.get('provider','ollama'),cfg.get('model','qwen3:4b'),cfg.get('base_url') or None,
                                    allow_remote=cfg.get('allow_remote',False))
                picture=await self._page.screenshot() if use_vision else None
                facts={k:v for k,v in profile.items() if v and not k.startswith('resume_')}
                context=get_setting('candidate_context',{})
                facts['candidate_context']={k:context[k] for k in ('education','experience','skills','languages','preferences') if k in context}
                result=await asyncio.to_thread(model.decide_form_action,snap['text'],ai_fields,facts,picture)
                if not isinstance(result,dict): raise LLMError('Expected a JSON object')
                for action in result.get('actions',[]):
                    if not isinstance(action,dict): continue
                    i=action.get('field_index'); value=action.get('value')
                    if isinstance(i,int) and any(f['index']==i for f in ai_fields) and isinstance(value,str) and value.strip():
                        # Model output is a proposal, never a newly verified applicant fact.
                        suggestions.append({'field_index':i,'value':value,'needs_review':True})
                unresolved.extend(q for q in result.get('unknown_questions',[]) if isinstance(q,str))
            except Exception as exc:
                unresolved.append('AI unavailable: '+str(exc)[:120])
        done=[];errors=[]
        successful=set()
        for action in plan:
            i=action.target.field_index
            value=action.value
            try:
                done.append(await self._fill(i,value))
                successful.add(i)
            except Exception as exc:
                errors.append({'field':i,'error':str(exc)[:140]})
        # Only report a required question as unanswered if it was not actually filled.
        # This avoids prematurely stopping multi-page applications after a correct AI answer.
        fresh=await self._snapshot()
        errors.extend({'field':None,'error':message} for message in fresh.get('page_errors',[]))
        for field in fresh['fields']:
            unanswered=not field.get('valid', bool(field['value']) or field['index'] in successful)
            if field['required'] and unanswered and field['type'] not in ('submit','hidden'):
                unresolved.append(field['label'] or field['name'] or f"field {field['index']}")
        return {'filled':done,'unknown':sorted(set(unresolved)),'errors':errors,'suggestions':suggestions,'url':self._page.url,
                'note':'Review answers and screenshot before proceeding or submitting'}


browser=BrowserManager()
