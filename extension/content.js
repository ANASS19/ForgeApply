// Runs only in Chrome's isolated world after an explicit extension action.
(() => {
  const VERSION='bilingual-forms-4';
  if (globalThis.ForgeApplyPage?.version===VERSION) return;
  const refs = new Map();
  let snapshot = null;
  const visible = e => { const r=e.getBoundingClientRect(); return r.width>0&&r.height>0; };
  // Yield to controlled-input handlers without waiting for background-tab animation frames.
  const settleDOM=()=>new Promise(resolve=>{const channel=new MessageChannel();channel.port1.onmessage=()=>{channel.port1.close();channel.port2.close();resolve();};channel.port2.postMessage(null);});
  function label(e) {
    const clean = node => { if(!node)return ''; const copy=node.cloneNode(true);copy.querySelectorAll('input,select,textarea,button,[role=alert],[data-automation-id=errorMessage],.field-error,.error-message').forEach(x=>x.remove());return copy.textContent.trim(); };
    return (clean(e.labels?.[0])||e.getAttribute('aria-label')||(e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>e.ownerDocument.getElementById(id)?.textContent||'').join(' ').trim()||e.getAttribute('placeholder')||e.closest('fieldset')?.querySelector('legend')?.textContent||'').slice(0,500);
  }
  const markedRequired = text => /(?:[*＊]+\s*(?:(?:campo\s+)?(?:obbligatori[oa]|required|mandatory|obligatoire))?|[\[(]\s*(?:campo\s+)?(?:obbligatori[oa]|required|mandatory|obligatoire)\s*[\])])\s*[:.]*\s*$/i.test(text);
  const customCombo = e => (e.getAttribute('role')==='combobox'||e.getAttribute('aria-haspopup')==='listbox')&&e.tagName!=='INPUT'&&e.tagName!=='SELECT';
  const searchableCombo = e => e.tagName==='INPUT'&&(e.getAttribute('role')==='combobox'||!!e.closest('[data-automation-id=multiSelectContainer]'));
  const skillPicker=e=>searchableCombo(e)&&(e.id==='skills--skills'||!!e.closest('[data-automation-id=formField-skills]'));
  function selectedValues(e){
    const root=e.closest('[data-automation-id^=formField-]')||e.closest('[data-automation-id=multiSelectContainer]');
    if(!root)return [];
    let nodes=[...root.querySelectorAll('[data-automation-id=selectedItem]')];if(!nodes.length)nodes=[...root.querySelectorAll('[data-automation-id=selectedItemLabel],[data-automation-id=selectedItemText]')];
    return [...new Set(nodes.map(node=>{const copy=node.cloneNode(true);copy.querySelectorAll('button,svg,[aria-hidden=true]').forEach(n=>n.remove());return copy.textContent.trim();}).filter(Boolean))];
  }
  const navigationName = name => /^(Next|Continue|Review|Save (?:and|&) Continue|Avanti|Continua|Rivedi|Salva e (?:continua|prosegui))$/i.test(name.trim());
  const choiceKey = text => {const clean=text.trim().toLowerCase(),cefr=clean.match(/\b([abc][12])\b/);return cefr?'cefr:'+cefr[1]:({italy:'italia',it:'italia',milan:'milano',mi:'milano'})[clean]||clean;};
  const value = e => {
    if(e.type==='password')return '';
    if(e.tagName==='SELECT'&&/^(?:choose|select(?: one)?|scegli|seleziona)(?:\s*\.\.\.)?$/i.test(e.selectedOptions[0]?.text.trim()||''))return '';
    if(searchableCombo(e)){const selected=selectedValues(e);if(selected.length)return selected.join(' | ');}
    if(customCombo(e)){const selected=e.getAttribute('aria-valuetext')||e.dataset.value;if(selected)return selected;const text=e.textContent.trim();return /^(choose|select|scegli|seleziona)/i.test(text)?'':text;}
    return String(e.isContentEditable?e.innerText:(e.value||'')).slice(0,8000);
  };
  const signature = e => JSON.stringify([label(e),groupLabel(e),recordInfo(e).section,recordInfo(e).record_index,e.name||'',e.id||'',e.type||'',e.tagName,
    e.type==='radio'||e.type==='checkbox'?e.value:'',e.tagName==='SELECT'?[...e.options].map(o=>[o.value,o.text,o.disabled]):null]);
  function groupLabel(e) {
    const group=e.closest('fieldset,[role=radiogroup],[role=group],[data-automation-id^=formField-]');
    if(!group)return '';
    return (group.querySelector('legend')?.textContent||group.getAttribute('aria-label')||(group.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>e.ownerDocument.getElementById(id)?.textContent||'').join(' ').trim()||group.querySelector('[data-automation-id=formLabel]')?.textContent||group.querySelector(':scope > label')?.textContent||'').trim().slice(0,500);
  }
  const radios=e=>[...e.ownerDocument.querySelectorAll('input[type=radio]')].filter(other=>other.name===e.name&&(e.name||other===e)&&other.form===e.form);
  function automationPath(e){const ids=[];for(let n=e;n&&ids.length<8;n=n.parentElement){const id=n.getAttribute('data-automation-id');if(id)ids.push(id.slice(0,300));}return ids;}
  function phonePrefix(input){
    const doc=input.ownerDocument;
    const controls=[...doc.querySelectorAll('select,input,[role=combobox],[data-automation-id*=countryPhoneCode]')].filter(e=>
      /countryPhoneCode/i.test(e.id||e.getAttribute('data-automation-id')||'')||/^(?:country.*phone code|phone country code|prefisso(?: telefonico)?)[*\s:]*$/i.test(label(e)));
    const group=input.closest('[role=group],fieldset');
    const scoped=group?controls.filter(e=>group.contains(e)):controls;
    // Read the selected prefix, never every country's options or an unrelated phone group.
    const codes=scoped.flatMap(e=>{
      const text=e.tagName==='SELECT'?e.selectedOptions[0]?.text||'':searchableCombo(e)?selectedValues(e).join(' '):e.value||e.getAttribute('aria-valuetext')||e.textContent;
      return [...text.matchAll(/\+\d{1,4}\b/g)].map(m=>m[0]);
    }),unique=[...new Set(codes)];return unique.length===1?unique[0]:'';
  }
  const recordType=prefix=>({workexperience:'experience',education:'education',language:'languages',languages:'languages',certification:'certifications',certifications:'certifications'})[prefix.toLowerCase()]||'';
  function recordRows(doc,section){
    const groups=new Map();
    for(const root of doc.querySelectorAll('[data-automation-id]')){
      const match=(root.getAttribute('data-automation-id')||'').match(/^(workExperience|education|languages?|certifications?)[-_]\d+$/i);
      if(match&&recordType(match[1])===section)groups.set(match[0],{key:match[0],root,nodes:[...root.querySelectorAll('input,select,textarea,[role=combobox],button[aria-haspopup=listbox]')]});
    }
    for(const node of doc.querySelectorAll('input[id],select[id],textarea[id],[role=combobox][id],button[aria-haspopup=listbox][id]')){
      const match=node.id.match(/^((workExperience|education|languages?|certifications?)[-_]\d+)--/i);
      if(!match||recordType(match[2])!==section||[...groups.values()].some(g=>g.root?.contains(node)))continue;
      if(!groups.has(match[1]))groups.set(match[1],{key:match[1],root:null,nodes:[]});
      groups.get(match[1]).nodes.push(node);
    }
    return [...groups.values()];
  }
  function recordInfo(e) {
    for(const section of ['experience','education','languages','certifications']){
      const rows=recordRows(e.ownerDocument,section),record_index=rows.findIndex(row=>row.nodes.includes(e)||row.root?.contains(e));
      if(record_index<0)continue;
      const identity={};
      for(const input of rows[record_index].nodes){
        const name=label(input).replace(/\s*\*.*$/,'').trim();
        const key=/^(Company|Employer|Azienda|Datore di lavoro)$/i.test(name)?'employer':/^(Job title|Role|Ruolo|Qualifica)$/i.test(name)?'title':/^(School or University|School|University|Università|Istituto)$/i.test(name)?'institution':/^(Language|Lingua|Certification|Certification name|Certificazione)$/i.test(name)?'name':'';
        const identityValue=input.tagName==='SELECT'&&input.value?input.selectedOptions[0]?.text.trim():value(input);
        if(key&&identityValue)identity[key]=identityValue;
      }
      return {section,record_index,record_identity:identity};
    }
    return {};
  }
  function contextualLabel(e){
    const date=e.id.match(/--(startDate|endDate|issueDate|expirationDate)-dateSection(Month|Year)-input$/);
    return date?({startDate:'From',endDate:'To',issueDate:'Issue',expirationDate:'Expiry'})[date[1]]+' '+date[2]:label(e);
  }
  function headingSection(text){
    const name=text.trim().replace(/\s+\d+$/,'');
    return /^(?:Work Experience|Employment History|Esperienz[ae](?: professional[ei]| lavorativ[ae])?)$/i.test(name)?'experience':/^(Education|Formazione|Istruzione)$/i.test(name)?'education':/^(Languages?|Lingue)$/i.test(name)?'languages':/^(Certifications?|Certificazioni)$/i.test(name)?'certifications':'';
  }
  function addButtons(doc) {
    return [...doc.querySelectorAll('button')].filter(visible).flatMap(button=>{
      if(!/^Add(?: Another)?(?: Work Experience| Education| Language| Certification)?$|^Aggiungi(?: un.altra)?(?: esperienza| formazione| lingua| certificazione)?$/i.test(button.textContent.trim()))return [];
      const known=button.closest('[data-automation-id=workExperienceSection],[data-automation-id=educationSection],[data-automation-id=languagesSection],[data-automation-id=certificationsSection]');
      let section=known?({workExperienceSection:'experience',educationSection:'education',languagesSection:'languages',certificationsSection:'certifications'})[known.getAttribute('data-automation-id')]:'';
      if(!section)for(let parent=button.parentElement;parent&&parent!==doc.body;parent=parent.parentElement){
        const types=[...new Set([...parent.querySelectorAll('h2,h3,h4,[role=heading]')].map(h=>headingSection(h.textContent)).filter(Boolean))];
        if(types.length===1){section=types[0];break;}if(types.length>1)break;
      }
      if(!section){const preceding=[...doc.querySelectorAll('h2,h3,h4,[role=heading]')].filter(h=>h.compareDocumentPosition(button)&Node.DOCUMENT_POSITION_FOLLOWING);section=headingSection(preceding.at(-1)?.textContent||'');}
      if(!section)return [];
      return [{button,section,existing_count:recordRows(doc,section).length}];
    });
  }
  function documents(root=document,result=[]) {
    if(result.length>=21)return result;
    result.push(root);
    root.querySelectorAll('iframe').forEach(frame=>{try{if(frame.contentDocument)documents(frame.contentDocument,result);}catch{}});
    return result;
  }
  function inspect() {
    refs.clear();const fields=[],navigation=[],add_controls=[];let skippedFrames=0,truncated_controls=0;
    for(const doc of documents()) {
      skippedFrames += [...doc.querySelectorAll('iframe')].filter(f=>{try{return !f.contentDocument}catch{return true}}).length;
      for(const e of doc.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]),textarea,select,[contenteditable=true],[role=combobox]:not(input):not(select),button[aria-haspopup=listbox]')) {
        if(e.closest('[data-automation-id=utilityButtonBar]')||e.closest('header,nav')&&!e.closest('form'))continue;
        if(e.disabled||e.readOnly&&!searchableCombo(e)||(!visible(e)&&e.type!=='file'))continue;
        if(fields.length>=100){truncated_controls++;continue;}
        const token=crypto.randomUUID();refs.set(token,{element:e,signature:signature(e)});
        const required=!!e.required||e.getAttribute('aria-required')==='true'||markedRequired(label(e))||markedRequired(groupLabel(e));
        const checked=!!e.checked,group_answered=e.type==='radio'&&radios(e).some(other=>other.checked);
        const answered=e.type==='radio'?group_answered:e.type==='checkbox'?checked:e.type==='file'?e.files.length>0:!!value(e).trim();
        const options=e.tagName==='SELECT'?[...e.options].slice(0,300).map(o=>({label:o.text,value:o.value,disabled:o.disabled})):e.type==='radio'?radios(e).slice(0,300).map(o=>({label:label(o),value:o.value,disabled:o.disabled})):[];
        fields.push({index:fields.length,token,label:contextualLabel(e),group_label:groupLabel(e),group_answered,options,...recordInfo(e),automation_id:(e.getAttribute('data-automation-id')||'').slice(0,300),automation_path:automationPath(e),phone_prefix:phonePrefix(e),selection_required:searchableCombo(e),selected_values:skillPicker(e)?selectedValues(e):[],name:e.name||'',id:e.id||'',type:skillPicker(e)?'multiselect':customCombo(e)?'combobox':e.type==='select-one'||e.type==='select-multiple'?'select':(e.type||e.getAttribute('role')||'text'),value:value(e),required,checked,valid:(e.validity?e.validity.valid:true)&&e.getAttribute('aria-invalid')!=='true'&&(!required||answered),cross_origin:false});
      }
      for(const control of addButtons(doc)){
        if(add_controls.some(c=>c.section===control.section))continue;
        const token=crypto.randomUUID();refs.set(token,{element:control.button,signature:signature(control.button),kind:'add_record',section:control.section});
        add_controls.push({token,section:control.section,existing_count:control.existing_count});
      }
      for(const e of doc.querySelectorAll('button,a[role=button],input[type=submit]')) {
        const name=(e.getAttribute('aria-label')||e.textContent||e.value||'').trim();
        if(visible(e)&&navigationName(name)) {
          const token=crypto.randomUUID();refs.set(token,{element:e,signature:signature(e),name});navigation.push({token,name});
        }
      }
    }
    let job={title:document.querySelector('h1')?.textContent?.trim().slice(0,500)||document.title,company:'',location:'',description:(document.querySelector('main')?.innerText||'').slice(0,20000)};
    for(const node of document.querySelectorAll('script[type="application/ld+json"]')) {
      try { const parsed=JSON.parse(node.textContent);for(const item of (Array.isArray(parsed)?parsed:parsed['@graph']||[parsed]))if(item['@type']==='JobPosting')job={title:String(item.title||job.title).slice(0,500),company:String(item.hiringOrganization?.name||'').slice(0,300),location:String(item.jobLocation?.address?.addressLocality||'').slice(0,300),description:job.description}; }catch{}
    }
    const stage=document.querySelector('[aria-current=step],[data-automation-id=progressBarActiveStep]')?.textContent.trim()||'';
    const needs_login=[...document.querySelectorAll('input[type=password]')].some(visible);
    if(/^(Review|Riepilogo|Revisione)$/i.test(stage))navigation.length=0;
    snapshot={snapshot_id:crypto.randomUUID(),url:location.href,page_language:document.documentElement.lang||'',stage,needs_login,fields,navigation,add_controls,truncated_controls,job,skipped_frames:skippedFrames,page_text:(document.body?.innerText||'').slice(0,6000)};
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
    if(plan.structure_actions?.length){
      let added=0;
      for(const action of plan.structure_actions){
        try{
          const entry=resolve(action.token,plan.snapshot_id);
          if(entry.kind!=='add_record'||entry.section!==action.section||!Number.isInteger(action.count)||action.count<1||action.count>10)throw Error('Invalid record expansion');
          const doc=entry.element.ownerDocument;
          for(let i=0;i<action.count;i++){
            const controls=addButtons(doc).filter(c=>c.section===action.section);
            if(controls.length!==1)throw Error('Add-record control changed or is ambiguous.');
            const before=recordRows(doc,action.section).length;controls[0].button.click();
            for(let attempt=0;attempt<15&&recordRows(doc,action.section).length===before;attempt++)await new Promise(resolve=>setTimeout(resolve,100));
            if(recordRows(doc,action.section).length!==before+1)throw Error('New record was not verified. No click was repeated.');
            added++;
          }
        }catch(error){errors.push({index:action.section,error:error.message});break;}
      }
      return {filled,errors,structure_changed:added>0,snapshot:inspect()};
    }
    for(const action of plan.actions) {
      try {
        const {element:e}=resolve(action.token,plan.snapshot_id);
        const old=snapshot.fields.find(f=>f.token===action.token);
        if(!old||value(e)!==old.value||['checkbox','radio'].includes(e.type)&&e.checked!==old.checked)throw Error('User/page modified this field; inspect again.');
        if(e.readOnly&&!searchableCombo(e)||['password','file','hidden','submit'].includes(e.type)||e.type==='button'&&!customCombo(e))throw Error('Control requires manual interaction.');
        if(action.values){
          if(!skillPicker(e)||!Array.isArray(action.values)||action.values.length>20||action.values.some(v=>typeof v!=='string'))throw Error('Invalid multi-select action.');
          for(const skill of action.values){
            if(selectedValues(e).some(v=>choiceKey(v)===choiceKey(skill)))continue;
            await pickOption(e,skill);
            if(!selectedValues(e).some(v=>choiceKey(v)===choiceKey(skill)))throw Error('Skill selection did not persist.');
          }
          filled.push({index:action.index,label:old.label,source:action.source});continue;
        }
        if(['checkbox','radio'].includes(e.type)){
          if(e.type==='radio'&&radios(e).some(other=>other.checked)!==old.group_answered)throw Error('Radio selection changed; inspect again.');
          if(!['true','false'].includes(action.value)||e.type==='radio'&&action.value!=='true')throw Error('Expected an explicit factual choice.');
          if(e.checked!==(action.value==='true'))e.click();
        }else if(customCombo(e)||searchableCombo(e)){
          await pickOption(e,action.value);
        }else if(e.tagName==='SELECT') {
          const options=[...e.options].filter(o=>o.value===action.value||o.text===action.value);
          if(options.length!==1)throw Error('Option missing or ambiguous.');e.value=options[0].value;
        } else if(e.isContentEditable)e.textContent=action.value;
        else { const proto=e.tagName==='TEXTAREA'?e.ownerDocument.defaultView.HTMLTextAreaElement.prototype:e.ownerDocument.defaultView.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,action.value); }
        e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));
        e.dispatchEvent(new FocusEvent('focusout',{bubbles:true}));
        await settleDOM();
        const persisted=['checkbox','radio'].includes(e.type)?e.checked===(action.value==='true'):e.tagName==='SELECT'?[e.value,...[...e.selectedOptions].map(o=>o.text)].includes(action.value):customCombo(e)||searchableCombo(e)?choiceKey(value(e))===choiceKey(action.value):value(e)===action.value;
        if(!persisted)throw Error('Value did not persist.');
        filled.push({index:action.index,label:old.label,source:action.source});
      } catch(error){errors.push({index:action.index,error:error.message});}
    }
    return {filled,errors,snapshot:inspect()};
  }
  async function pickOption(e,wanted){
    if(!e.isConnected)throw Error('Control changed; analyze again.');
    if(searchableCombo(e)&&!e.readOnly){Object.getOwnPropertyDescriptor(e.ownerDocument.defaultView.HTMLInputElement.prototype,'value').set.call(e,wanted);e.dispatchEvent(new Event('input',{bubbles:true}));}
    e.click();
    const container=e.closest('[data-automation-id=multiSelectContainer]');
    const popupId=(e.getAttribute('aria-controls')||e.getAttribute('aria-owns')||container?.getAttribute('aria-controls')||'').split(/\s+/)[0],popup=e.ownerDocument.getElementById(popupId);
    const filter=popup&&[...popup.querySelectorAll('input')].find(input=>input!==e&&!input.readOnly&&visible(input)&&(input.type==='search'||/search|cerca/i.test(label(input)||input.placeholder)));
    if(filter){Object.getOwnPropertyDescriptor(filter.ownerDocument.defaultView.HTMLInputElement.prototype,'value').set.call(filter,wanted);filter.dispatchEvent(new Event('input',{bubbles:true}));}
    let options=[];
    for(let attempt=0;attempt<15;attempt++){
      const candidates=[...e.ownerDocument.querySelectorAll('[role=listbox],[role=tree]')].filter(visible);
      const root=e.ownerDocument.getElementById(popupId)||(candidates.length===1?candidates[0]:null);
      if(!root){await new Promise(resolve=>setTimeout(resolve,100));continue;}
      options=[...root.querySelectorAll('[role=option]')].filter(o=>visible(o)&&o.getAttribute('aria-disabled')!=='true'&&choiceKey(o.getAttribute('aria-label')||o.textContent)===choiceKey(wanted));
      if(options.length)break;await new Promise(resolve=>setTimeout(resolve,100));
    }
    if(options.length!==1)throw Error('Choose this search/dropdown option on the page; no unique verified match was found.');
    options[0].click();await settleDOM();
  }
  async function next(token,id) {
    const entry=resolve(token,id);if(!navigationName(entry.name))throw Error('Final actions stay manual.');
    const current=inspect();
    if(current.truncated_controls)throw Error('This page exceeds the inspection limit. Collapse completed records or continue manually.');
    const missing=current.fields.some(f=>f.required&&(f.type==='radio'?!f.group_answered:f.type==='checkbox'?!f.checked:!f.value.trim()));
    if(missing)return {transition_verified:false,snapshot:current};
    if(entry.element.form&&!entry.element.form.checkValidity()){entry.element.form.reportValidity();return {transition_verified:false,snapshot:inspect()};}
    const before=document.body.innerText;entry.element.click();
    for(let i=0;i<20;i++){await new Promise(r=>setTimeout(r,100));if(location.href!==snapshot.url||document.body.innerText!==before){
      const rejected=[...document.querySelectorAll('[role=alert],.field-error,.error-message,[data-automation-id=errorMessage]')].some(e=>visible(e)&&/error|invalid|missing|required|errore|obbligatori|non valid|rifiutat/i.test(e.textContent));
      return {transition_verified:!rejected,snapshot:inspect()};
    }}
    return {transition_verified:false,snapshot:inspect()};
  }
  async function chooseFile(token,id) {
    const {element:e}=resolve(token,id);if(e.type!=='file')throw Error('Select a file input.');
    return new Promise(resolve=>{
      let timer;
      const finish=()=>{clearTimeout(timer);e.removeEventListener('change',finish);e.removeEventListener('cancel',finish);resolve({attached:!!e.files.length,filename:e.files[0]?.name||'',snapshot:inspect(),message:e.files.length?'CV selected: '+e.files[0].name:'No new file selected.'});};
      e.addEventListener('change',finish,{once:true});e.addEventListener('cancel',finish,{once:true});timer=setTimeout(finish,90000);
      e.scrollIntoView({block:'center'});e.focus();e.click();
    });
  }
  globalThis.ForgeApplyPage={version:VERSION,inspect,fill,next,chooseFile};
})();
