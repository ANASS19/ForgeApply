"""Human-visible local Playwright browser with deterministic form filling + optional AI fallback.

Never submit silently: final submission requires user click, or an explicit per-job
approved flag, and is disabled for domains where automation is prohibited.
"""
from __future__ import annotations
import asyncio
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from .config import ROOT
from .store import get_setting, list_answers, set_status, get_job
from .llm import DecisionModel, LLMError

BROWSER_DIR = ROOT / 'browser_profile'
SCREEN_DIR = ROOT / 'screenshots'
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

FIELD_SCRIPT = '''() => Array.from(document.querySelectorAll('input:not([type=hidden]),textarea,select,[contenteditable=true]'))
 .filter(e => {const r=e.getBoundingClientRect();return r.width>0 && r.height>0 && !e.disabled})
 .slice(0,100).map((e,i) => {
 const id=e.id||'';
 const label=(id && document.querySelector('label[for="'+CSS.escape(id)+'"]')?.innerText) ||
  e.closest('label')?.innerText || e.getAttribute('aria-label') || e.getAttribute('placeholder') ||
  e.closest('fieldset')?.querySelector('legend')?.innerText || '';
 return {index:i,tag:e.tagName.toLowerCase(),type:e.getAttribute('type')||'',name:e.name||'',
 id:id,label:(label||'').trim().slice(0,230),value:e.type==='password'?'':(e.value||'').slice(0,140),
 required:e.required||false,options:e.tagName==='SELECT'?Array.from(e.options).map(o=>({value:o.value,text:o.text})):[]}
 })'''


class BrowserManager:
    def __init__(self):
        self._thread=None
        self._loop=None
        self._ready=threading.Event()
        self._playwright=None
        self._context=None
        self._page=None
        self.last_error=None
        self._lock=threading.Lock()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive(): return
            self._ready.clear()
            self._thread=threading.Thread(target=self._run_loop,daemon=True,name='ForgeApply Browser')
            self._thread.start()
        if not self._ready.wait(timeout=45): raise RuntimeError('Browser startup timed out')
        if self.last_error: raise RuntimeError(self.last_error)

    def _run_loop(self):
        self._loop=asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._init())
        except Exception as exc:
            self.last_error=str(exc)
        finally:
            self._ready.set()
        if not self.last_error:
            self._loop.run_forever()

    async def _init(self):
        self._playwright=await async_playwright().start()
        self._context=await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DIR), headless=False, viewport={'width':1440,'height':900},
            accept_downloads=True, args=['--disable-blink-features=AutomationControlled'])
        self._page=self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._page.set_default_timeout(6000)

    def call(self, coroutine, timeout=100):
        self.start()
        f=asyncio.run_coroutine_threadsafe(coroutine,self._loop)
        return f.result(timeout=timeout)

    async def _navigate(self,url):
        if urlparse(url).scheme not in ('http','https'): raise ValueError('Only http(s) URLs permitted')
        await self._page.goto(url,wait_until='domcontentloaded',timeout=35000)
        return await self._snapshot()

    def navigate(self,url): return self.call(self._navigate(url))

    async def _snapshot(self):
        page=self._page
        try: text=(await page.locator('body').inner_text(timeout=7000))[:12000]
        except Exception: text=''
        fields=await page.evaluate(FIELD_SCRIPT)
        return {'url':page.url,'title':await page.title(),'text':text,'fields':fields,
                'buttons':(await page.locator('button,input[type=submit],a[role=button]').all_text_contents())[:50]}

    def snapshot(self): return self.call(self._snapshot())

    async def _screenshot(self):
        path=SCREEN_DIR/'latest.png'
        await self._page.screenshot(path=str(path),full_page=False,animations='disabled')
        return str(path)

    def screenshot(self): return self.call(self._screenshot())

    async def _fill(self, i:int, value:str):
        fields=self._page.locator('input:not([type=hidden]),textarea,select,[contenteditable=true]')
        # DOM index from FIELD_SCRIPT excludes hidden/disabled: map through visible element handles.
        handles=await fields.element_handles()
        visible=[]
        for h in handles:
            try:
                if await h.is_visible() and await h.is_enabled(): visible.append(h)
            except Exception: pass
        if i<0 or i>=len(visible): raise ValueError('Invalid field index')
        element=visible[i]
        tag=await element.evaluate('(e)=>e.tagName.toLowerCase()')
        typ=(await element.get_attribute('type') or '').lower()
        if typ in ('file','password'):
            raise ValueError('Use resume upload for files; password fields require user input')
        if typ in ('checkbox','radio'):
            truth=value.lower() in ('yes','true','1','checked','on')
            if truth: await element.check()
            else: await element.uncheck()
        elif tag=='select':
            try: await element.select_option(label=value)
            except Exception: await element.select_option(value=value)
        else:
            await element.fill(value)
        return {'field_index':i,'value':value,'ok':True}

    def fill(self,i,value): return self.call(self._fill(int(i),str(value)))

    async def _upload_resume(self,lang='en'):
        profile=get_setting('profile',{})
        path=Path(profile.get('resume_it' if lang=='it' else 'resume_en','')).expanduser()
        if not path.is_file(): raise FileNotFoundError('Configure an existing resume file in the Profile tab')
        files=self._page.locator('input[type=file]')
        if await files.count()==0: raise RuntimeError('No file upload input found on this page')
        await files.first.set_input_files(str(path))
        return {'uploaded':path.name,'language':lang}

    def upload_resume(self,lang='en'): return self.call(self._upload_resume(lang))

    async def _click(self,kind, text=''):
        if kind not in ('next','easy_apply','other'): raise ValueError('Unknown click kind')
        if kind=='easy_apply':
            pattern=re.compile(r'Easy Apply|Candidatura semplice|Candidati facilmente',re.I)
        elif kind=='next':
            pattern=re.compile(r'^(Next|Continue|Review|Avanti|Continua|Rivedi)$',re.I)
        else:
            if not text or len(text)>130: raise ValueError('Provide button text')
            pattern=re.compile(re.escape(text),re.I)
            # Never let general action submit accidentally.
            if re.search(r'submit|invia|send application|apply now|finaliz',text,re.I):
                raise ValueError('Final submission requires explicit approved action')
        candidates=self._page.get_by_role('button',name=pattern)
        if await candidates.count()==0:
            candidates=self._page.get_by_role('link',name=pattern)
        if await candidates.count()==0: raise RuntimeError('Button/link not found')
        await candidates.first.click(timeout=6000)
        await self._page.wait_for_timeout(350)
        return await self._snapshot()

    def click(self,kind,text=''): return self.call(self._click(kind,text))

    async def _submit(self,job_id, approved):
        if not approved: raise PermissionError('Final submission requires explicit approval')
        job=get_job(job_id)
        if not job: raise KeyError('Job not found')
        # No automated final clicks on LinkedIn, where third-party automation may violate site rules.
        host=(urlparse(self._page.url).hostname or '').lower()
        if host.endswith('linkedin.com') or host.endswith('indeed.com'):
            raise PermissionError('Click final Submit yourself on LinkedIn/Indeed and confirm in tracker')
        buttons=self._page.get_by_role('button',name=re.compile(r'^(Submit application|Submit|Send application|Invia candidatura|Apply)$',re.I))
        if await buttons.count()==0: raise RuntimeError('No recognized final submission button')
        await buttons.first.click(timeout=8000)
        await self._page.wait_for_timeout(1400)
        snap=await self._snapshot()
        text=snap['text'].lower()
        verified=bool(re.search(r'application (has been )?(submitted|received)|thank you for (applying|your application)|candidatura (inviata|ricevuta)|application successfully',text))
        if verified:
            set_status(job_id,'submitted','Verified post-submission confirmation on ' + self._page.url)
        else:
            set_status(job_id,'blocked','Submission clicked; confirmation not detected. Verify manually.')
        return {'submitted_verified':verified,'snapshot':snap}

    def submit(self,job_id,approved=False): return self.call(self._submit(job_id,approved))

    async def _agent_prepare(self, job_id:int, use_ai:bool=True, use_vision:bool=False, max_steps:int=8):
        """Navigate and prepare one application; never performs final submission."""
        job=get_job(job_id)
        if not job: raise KeyError('Job not found')
        await self._navigate(job['url'])
        set_status(job_id,'opened','Browser opened application URL')
        trace=[]
        previous=''
        for step in range(min(max_steps,12)):
            snap=await self._snapshot()
            text=snap['text'].lower()
            if any(word in text for word in ('verify you are human','captcha','unusual activity')):
                set_status(job_id,'blocked','Manual account verification required')
                return {'status':'blocked','reason':'Verification/CAPTCHA must be completed manually','trace':trace}
            if ('sign in' in text[:700] or 'log in' in text[:700]) and len(snap['fields'])<=3:
                set_status(job_id,'blocked','Please sign in to the site in the visible browser')
                return {'status':'needs_login','trace':trace}
            if not snap['fields']:
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
                lang=job.get('language') if job.get('language') in ('en','it') else 'en'
                try:
                    uploaded=await self._upload_resume(lang)
                    trace.append('Uploaded CV: '+uploaded['uploaded'])
                except Exception as exc:
                    set_status(job_id,'blocked','Resume upload needs review: '+str(exc)[:200])
                    return {'status':'needs_resume','language':lang,'reason':str(exc),'trace':trace}
            result=await self._autofill(use_ai,use_vision)
            trace.append(f"Filled {len(result['filled'])} fields; unknown {len(result['unknown'])}")
            if result['unknown'] or result['errors']:
                set_status(job_id,'blocked','Form questions require review: '+', '.join(result['unknown'])[:500])
                return {'status':'needs_answers','unknown':result['unknown'],'errors':result['errors'],'trace':trace}
            # Stop before ANY final submission action, even if it looks like the Next button.
            next_buttons=self._page.get_by_role('button',name=re.compile(r'^(Next|Continue|Review|Avanti|Continua|Rivedi)$',re.I))
            if await next_buttons.count()==0:
                set_status(job_id,'prepared','Agent filled available fields; please review and submit')
                return {'status':'ready_for_review','trace':trace,'snapshot':await self._snapshot()}
            fingerprint=str([(f['label'],f['value']) for f in (await self._snapshot())['fields']])
            if fingerprint==previous:
                set_status(job_id,'blocked','Form has not progressed; check validation messages')
                return {'status':'stalled','trace':trace}
            previous=fingerprint
            try:
                await self._click('next')
                trace.append('Clicked Next / Review')
            except Exception as exc:
                set_status(job_id,'blocked','Next step requires review: '+str(exc)[:200])
                return {'status':'blocked','reason':str(exc),'trace':trace}
        set_status(job_id,'prepared','Reached maximum navigation steps; please inspect browser')
        return {'status':'max_steps','trace':trace}

    def agent_prepare(self,job_id,use_ai=True,use_vision=False,max_steps=8):
        return self.call(self._agent_prepare(int(job_id),use_ai,use_vision,max_steps),timeout=360)

    def ocr(self):
        """Vision-model OCR without requiring an external OCR executable."""
        cfg=get_setting('llm',{})
        model=DecisionModel(cfg.get('provider','ollama'),cfg.get('model','qwen3:4b'),cfg.get('base_url') or None)
        path=self.screenshot()
        img=Path(path).read_bytes()
        return model.json('You are an OCR assistant. Transcribe all visible on-screen text faithfully. '
                          'Return JSON with text and unclear_segments fields. Do not guess unclear text.',
                          'Transcribe this screenshot to text.',screenshot=img)

    def autofill(self, use_ai=True, use_vision=False):
        return self.call(self._autofill(use_ai,use_vision),timeout=150)

    async def _autofill(self,use_ai,use_vision):
        snap=await self._snapshot()
        profile=get_setting('profile',{})
        answers=[a for a in list_answers() if a['enabled']]
        plan=[]; unresolved=[]; taken=set()
        patterns=[
          (r'first.?name|nome(?!.*cognome)',profile.get('first_name')),
          (r'last.?name|surname|cognome',profile.get('last_name')),
          (r'e.?mail',profile.get('email')),
          (r'phone|mobile|telefono|cellulare',profile.get('phone')),
          (r'linkedin',profile.get('linkedin')),
          (r'github',profile.get('github')),
          (r'portfolio|website|sito web',profile.get('portfolio')),
          (r'city|città|comune|location',profile.get('city')),
          (r'country|paese|nazione',profile.get('country')),
          (r'how many years.*(ai|artificial intelligence)|years.*ai experience',profile.get('years_ai')),
          (r'years.*python|python.*years',profile.get('years_python')),
        ]
        for f in snap['fields']:
            i=f['index']; label=' '.join(str(f.get(k,'')) for k in ('label','name','id'))
            if f['type'] in ('file','password','hidden','submit','checkbox','radio') or f['value']:
                continue
            answer=None
            for saved in answers:
                try:
                    if re.search(saved['pattern'],label,re.I): answer=saved['answer']; break
                except re.error: continue
            if answer is None:
                for pattern,value in patterns:
                    if value and re.search(pattern,label,re.I): answer=str(value);break
            if answer is not None:
                plan.append((i,answer));taken.add(i)
            # Required fields are checked after deterministic and AI fill plans complete.
        if use_ai and any(f['index'] not in taken and not f['value'] and f['type'] not in ('file','password','checkbox','radio','submit') for f in snap['fields']):
            cfg=get_setting('llm',{})
            model=DecisionModel(cfg.get('provider','ollama'),cfg.get('model','qwen3:4b'),cfg.get('base_url') or None)
            picture=await self._page.screenshot() if use_vision else None
            try:
                result=await asyncio.to_thread(model.decide_form_action,snap['text'],snap['fields'],profile,picture)
                for action in result.get('actions',[]):
                    i=action.get('field_index'); value=action.get('value')
                    if isinstance(i,int) and 0<=i<len(snap['fields']) and i not in taken and isinstance(value,str) and value.strip():
                        plan.append((i,value));taken.add(i)
                unresolved.extend(result.get('unknown_questions',[]))
            except (LLMError,Exception) as exc:
                unresolved.append('AI unavailable: '+str(exc)[:120])
        done=[];errors=[]
        successful=set()
        for i,value in plan:
            try:
                done.append(await self._fill(i,value))
                successful.add(i)
            except Exception as exc:
                errors.append({'field':i,'error':str(exc)[:140]})
        # Only report a required question as unanswered if it was not actually filled.
        # This avoids prematurely stopping multi-page applications after a correct AI answer.
        for field in snap['fields']:
            if field['required'] and not field['value'] and field['index'] not in successful:
                if field['type'] not in ('file','submit','hidden'):
                    unresolved.append(field['label'] or field['name'] or f"field {field['index']}")
        return {'filled':done,'unknown':sorted(set(unresolved)),'errors':errors,'url':self._page.url,
                'note':'Review answers and screenshot before proceeding or submitting'}


browser=BrowserManager()
