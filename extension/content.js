// Runs only in Chrome's isolated world after an explicit extension action.
(() => {
  if (globalThis.ForgeApplyPage) return;
  const refs = new Map();
  let snapshot = null;
  const visible = e => { const r=e.getBoundingClientRect(); return r.width>0&&r.height>0; };
  function label(e) {
    const clean = node => { if(!node)return ''; const copy=node.cloneNode(true);copy.querySelectorAll('input,select,textarea,button').forEach(x=>x.remove());return copy.textContent.trim(); };
    return (clean(e.labels?.[0])||e.getAttribute('aria-label')||(e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>e.ownerDocument.getElementById(id)?.textContent||'').join(' ').trim()||e.getAttribute('placeholder')||e.closest('fieldset')?.querySelector('legend')?.textContent||'').slice(0,500);
  }
  const value = e => e.type==='password'?'':String(e.isContentEditable?e.innerText:(e.value||'')).slice(0,1000);
  const signature = e => JSON.stringify([label(e),e.name||'',e.id||'',e.type||'',e.tagName]);
  function documents(root=document,result=[]) {
    result.push(root);
    root.querySelectorAll('iframe').forEach(frame=>{try{if(frame.contentDocument)documents(frame.contentDocument,result);}catch{}});
    return result;
  }
  function inspect() {
    refs.clear();const fields=[],navigation=[];let skippedFrames=0;
    for(const doc of documents()) {
      skippedFrames += [...doc.querySelectorAll('iframe')].filter(f=>{try{return !f.contentDocument}catch{return true}}).length;
      for(const e of doc.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]),textarea,select,[contenteditable=true],[role=combobox]:not(input):not(select)')) {
        if(fields.length>=100||e.disabled||e.readOnly||(!visible(e)&&e.type!=='file'))continue;
        const token=crypto.randomUUID();refs.set(token,{element:e,signature:signature(e)});
        fields.push({index:fields.length,token,label:label(e),name:e.name||'',id:e.id||'',type:e.type==='select-one'||e.type==='select-multiple'?'select':(e.type||e.getAttribute('role')||'text'),value:value(e),required:!!e.required||e.getAttribute('aria-required')==='true',valid:e.validity?e.validity.valid:!(e.getAttribute('aria-required')==='true'&&!value(e)),cross_origin:false});
      }
      for(const e of doc.querySelectorAll('button,a[role=button],input[type=submit]')) {
        const name=(e.getAttribute('aria-label')||e.textContent||e.value||'').trim();
        if(visible(e)&&/^(Next|Continue|Review|Avanti|Continua|Rivedi)$/.test(name)) {
          const token=crypto.randomUUID();refs.set(token,{element:e,signature:signature(e),name});navigation.push({token,name});
        }
      }
    }
    let job={title:document.querySelector('h1')?.textContent?.trim().slice(0,500)||document.title,company:'',location:'',description:(document.querySelector('main')?.innerText||'').slice(0,20000)};
    for(const node of document.querySelectorAll('script[type="application/ld+json"]')) {
      try { const parsed=JSON.parse(node.textContent);for(const item of (Array.isArray(parsed)?parsed:parsed['@graph']||[parsed]))if(item['@type']==='JobPosting')job={title:String(item.title||job.title).slice(0,500),company:String(item.hiringOrganization?.name||'').slice(0,300),location:String(item.jobLocation?.address?.addressLocality||'').slice(0,300),description:job.description}; }catch{}
    }
    snapshot={snapshot_id:crypto.randomUUID(),url:location.href,fields,navigation,job,skipped_frames:skippedFrames,page_text:(document.body?.innerText||'').slice(0,6000)};
    return snapshot;
  }
  function resolve(token,id) {
    if(!snapshot||snapshot.snapshot_id!==id||location.href!==snapshot.url)throw Error('Page changed; analyze again.');
    const entry=refs.get(token);
    if(!entry||!entry.element.isConnected||entry.element.disabled||entry.signature!==signature(entry.element))throw Error('Control changed; analyze again.');
    return entry;
  }
  async function fill(plan) {
    if(plan.url!==location.href)throw Error('Destination changed; analyze again.');
    const filled=[],errors=[];
    for(const action of plan.actions) {
      try {
        const {element:e}=resolve(action.token,plan.snapshot_id);
        const old=snapshot.fields.find(f=>f.token===action.token);
        if(!old||value(e)!==old.value)throw Error('User/page modified this field; inspect again.');
        if(e.readOnly||['password','file','hidden','submit','button','checkbox','radio'].includes(e.type)||e.getAttribute('role')==='combobox'&&e.tagName!=='SELECT')throw Error('Control requires manual interaction.');
        if(e.tagName==='SELECT') {
          const options=[...e.options].filter(o=>o.value===action.value||o.text===action.value);
          if(options.length!==1)throw Error('Option missing or ambiguous.');e.value=options[0].value;
        } else if(e.isContentEditable)e.textContent=action.value;
        else { const proto=e.tagName==='TEXTAREA'?e.ownerDocument.defaultView.HTMLTextAreaElement.prototype:e.ownerDocument.defaultView.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,action.value); }
        e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));
        await new Promise(requestAnimationFrame);
        if(e.tagName==='SELECT'?![e.value,...[...e.selectedOptions].map(o=>o.text)].includes(action.value):value(e)!==action.value)throw Error('Value did not persist.');
        filled.push({index:action.index,label:old.label,source:action.source});
      } catch(error){errors.push({index:action.index,error:error.message});}
    }
    return {filled,errors,snapshot:inspect()};
  }
  async function next(token,id) {
    const entry=resolve(token,id);if(!/^(Next|Continue|Review|Avanti|Continua|Rivedi)$/.test(entry.name))throw Error('Final actions stay manual.');
    const before=document.body.innerText;entry.element.click();
    for(let i=0;i<20;i++){await new Promise(r=>setTimeout(r,100));if(location.href!==snapshot.url||document.body.innerText!==before)return {transition_verified:true,snapshot:inspect()};}
    return {transition_verified:false,snapshot:inspect()};
  }
  function chooseFile(token,id) {
    const {element:e}=resolve(token,id);if(e.type!=='file')throw Error('Select a file input.');
    e.scrollIntoView({block:'center'});e.focus();e.click();
    return {message:'Choose the approved CV in the native file picker. Inspect again to verify the selected filename. No local path was assigned.'};
  }
  globalThis.ForgeApplyPage={inspect,fill,next,chooseFile};
})();
