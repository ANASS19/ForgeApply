// SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
// SPDX-License-Identifier: Apache-2.0
const $=id=>document.getElementById(id);
let tabId=null,tab=null,snapshot=null,plan=null,busy=false,paired=false,targetWindowId=null,pendingTab=null;
let documentKind='letter',documentURL='',documentJobKey='';
const edits=new Map();
async function send(type,data={}) {
  const result=await chrome.runtime.sendMessage({type,...data});
  if(type==='status'&&result?.ok&&result.worker_version!=='0.4.4')throw Object.assign(Error('Click Reload assistant below, then reopen ForgeApply. Your pairing will stay saved.'),{code:'extension_update_required'});
  if(!result?.ok){
    const detail=result?.error==='Unknown extension request'?'Reload ForgeApply at chrome://extensions, then reopen this panel. The background worker is an older version.':result?.error||'Reopen the extension to reconnect.';
    throw Object.assign(Error(detail),{code:result?.error_code});
  }
  return result.data;
}
function actions() {
  document.querySelectorAll('button').forEach(b=>b.disabled=busy);
  if(globalThis.ForgeApplyAgent?.running)for(const id of ['agentPause','agentStop'])$(id).disabled=false;
  if(busy)return;
  for(const id of ['fill','analyze','runAgent','showScreenshot'])$(id).disabled=!paired||!tab||tab.restricted;
  for(const id of ['letter','cv','saveJob','match','manualAnswer','useModel'])$(id).disabled=!paired;
  $('applyReviewed').disabled=!paired||!plan?.drafts?.length;
  $('chooseFile').disabled=!snapshot?.fields.some(f=>f.type==='file');
  $('next').disabled=snapshot?.navigation.length!==1;
  $('attachPDF').disabled=!paired||!snapshot?.fields.some(f=>f.type==='file')||documentURL!==tab?.url;
}
function button(id,handler) {
  $(id).addEventListener('click',()=>perform(handler));
}
async function perform(handler){
    if(busy)return;busy=true;actions();$('error').textContent='';
    try{await handler();}catch(error){$('summary').textContent='Action stopped. Your page entries were preserved.';$('error').textContent=error.message;if(error.code==='pair_required'){paired=false;$('pairSetup').hidden=false;}if(error.code==='extension_update_required')$('reloadAssistant').hidden=false;}
    finally{busy=false;actions();if(pendingTab!==null){const id=pendingTab;pendingTab=null;await current(id);}}
}
function reset() {
  snapshot=null;plan=null;edits.clear();$('fields').textContent='';
  $('agentScreenshot').hidden=true;$('agentScreenshot').removeAttribute('src');
  for(const key of ['title','company','location','description','originUrl'])$(key).value='';
  for(const id of ['reviewArea','manualTasks','uploadArea','next','letterArea'])$(id).hidden=true;
  $('summary').textContent='Ready when you are.';actions();
}
function dashboard(port) {
  for(const id of ['dashboardLink','pairDashboard'])$(id).href='http://127.0.0.1:'+Number(port);
}
async function status() {
  const {pairToken}=await chrome.storage.local.get('pairToken');$('pairSetup').hidden=!!pairToken;
  try {
    const state=await send('status');paired=true;$('pairSetup').hidden=true;
    if(state.bridge_version!=='0.4.4')throw Object.assign(Error('Restart the local ForgeApply backend to load the matching version. Your pairing stays saved.'),{code:'backend_update_required'});
    $('connection').textContent='Connected locally | '+state.model;
    $('documents').textContent=Object.entries(state.documents).map(([lang,d])=>lang.toUpperCase()+': '+(d.available?d.filename:'not configured')).join(' | ');
    $('pairCode').value='';
    if($('advanced').open)await models();
  } catch(error) {
    paired=false;$('connection').textContent=error.code==='offline'?'Backend offline - connection saved':error.code?.endsWith('update_required')?'Update required':'Connect ForgeApply';
    if(error.code==='pair_required')$('pairSetup').hidden=false;
    $('reloadAssistant').hidden=error.code!=='extension_update_required';
    if(pairToken)$('error').textContent=error.message;
  }
  actions();
}
async function current(id) {
  reset();tabId=id;
  try {
    tab=await send('tab',{tabId});targetWindowId=tab.window_id;$('site').textContent=tab.url;
    if(!tab.restricted)await chrome.storage.session.set({lastAuthorizedTab:tabId});
    $('policy').textContent=tab.restricted?'This platform stays manual. Paste job details under More options for answers and a letter.':'';
  }catch(error){tab=null;$('site').textContent=error.message;}
  actions();
}
function job() {
  return {url:tab?.url||'',title:$('title').value.trim(),company:$('company').value.trim(),location:$('location').value.trim(),description:$('description').value,origin_url:$('originUrl').value};
}
function adopt(state,importJob=false) {
  snapshot=state;plan=null;
  if(state.stage)$('policy').textContent='Step: '+state.stage;
  if(state.truncated_controls)$('policy').textContent+=' | Page inspection limit reached. Collapse completed records or continue manually.';
  $('fields').textContent=state.fields.map(f=>`${f.index}: ${f.label||f.name} [${f.type}]${f.required?' required':''}${!f.valid?' - needs attention':''}`).join('\n');
  if(importJob)for(const key of ['title','company','location','description'])$(key).value=state.job[key]||'';
  const files=state.fields.filter(f=>f.type==='file');$('uploadArea').hidden=!files.length;
  $('fileTarget').replaceChildren(...files.map(f=>{const option=document.createElement('option');option.value=f.token;option.textContent=f.label||f.name||'Document';return option;}));
  $('fileTarget').hidden=files.length<2;
  $('attachmentStatus').textContent=files.filter(f=>f.value).map(f=>f.value.replace(/^.*[\\/]/,'')).join(', ');
  $('next').hidden=state.navigation.length!==1||!!state.truncated_controls;
  $('reviewArea').hidden=true;$('manualTasks').hidden=true;actions();
}
const questionKey=d=>[d.index,d.label].join('|');
function captureEdits() {
  for(const area of $('draftAnswers').querySelectorAll('textarea,select,input'))
    if(edits.has(area.dataset.key)||area.value!==area.dataset.initialValue)edits.set(area.dataset.key,area.value);
}
function renderPlan() {
  const cards=(plan.drafts||[]).map(d=>{
    const card=document.createElement('div');card.className='answerCard';
    const label=document.createElement('label');label.textContent=d.label||'Answer';
    const typed=['number','date','month'].includes(d.input_type);
    const area=document.createElement(d.choices?'select':typed?'input':'textarea');if(typed)area.type=d.input_type;
    if(d.choices){const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Choose / Seleziona';area.append(placeholder);for(const choice of d.choices){const option=document.createElement('option');option.value=choice.value;option.textContent=choice.label;area.append(option);}}
    else{area.rows=d.value?6:2;area.maxLength=8000;}
    area.dataset.index=d.index;area.dataset.key=questionKey(d);
    area.setAttribute('aria-label',d.label||'Answer');
    area.value=edits.has(area.dataset.key)?edits.get(area.dataset.key):d.value;
    area.dataset.initialValue=area.value;
    area.placeholder='Enter your verified answer / Inserisci una risposta verificata';
    area.addEventListener('input',()=>edits.set(area.dataset.key,area.value));label.append(area);card.append(label);
    const hint=document.createElement('small');hint.textContent=d.kind==='selection_unresolved'?'Saved fact: '+d.known_value+'. Choose the corresponding website option; no equivalence was assumed.':d.kind==='record_unresolved'?'This populated row could not be safely matched to a saved record. Check its identity on the page.':d.source==='user_input'?'Missing fact: your answer is needed.':d.source==='user:approved-answer'?'Previously approved answer for review.':d.source==='verified_fact_template'?'Draft from verified profile facts - review before filling.':'AI draft - verify every claim.';card.append(hint);
    if(d.facts_used?.length){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Supporting facts';details.append(summary);for(const fact of d.facts_used){const p=document.createElement('p');p.textContent=fact.text||JSON.stringify(fact.value);details.append(p);}card.append(details);}
    const controls=document.createElement('div');controls.className='answerActions';
    const approve=document.createElement('button');approve.textContent='Approve & fill';approve.disabled=busy;
    approve.addEventListener('click',()=>perform(()=>fillReviewed([d])));
    const edit=document.createElement('button');edit.className='secondary';edit.textContent='Reject & edit';edit.disabled=busy;
    edit.addEventListener('click',()=>{area.value='';edits.set(area.dataset.key,'');area.focus();});
    controls.append(approve,edit);card.append(controls);
    return {card,optional:d.optional};
  });
  const required=cards.filter(c=>!c.optional).map(c=>c.card),optional=cards.filter(c=>c.optional).map(c=>c.card);
  if(optional.length){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`${optional.length} optional answers / risposte facoltative`;details.append(summary,...optional);required.push(details);}
  $('draftAnswers').replaceChildren(...required);$('reviewArea').hidden=!cards.length;
  $('manualTasks').replaceChildren();
  const optionalTasks=[];
  for(const task of (plan.manual||[]).filter(t=>t.type!=='file')){const p=document.createElement('p');p.textContent=task.label+': '+task.reason+'.';if(task.optional)optionalTasks.push(p);else $('manualTasks').append(p);}
  if(optionalTasks.length){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`Review ${optionalTasks.length} optional personal fields / dati personali`;details.append(summary,...optionalTasks);$('manualTasks').append(details);}
  $('manualTasks').hidden=!$('manualTasks').childElementCount;
  if(plan.ai_error)$('error').textContent='AI could not prepare additional answers: '+plan.ai_error;
  actions();
}
async function prepare(useAI=false) {
  plan=await send('plan',{tabId,snapshot,site_authorized:true,use_ai:useAI,language:$('language').value,job:job()});
  renderPlan();return plan;
}
async function fillPlan(prepared,depth=0,verified=0) {
  const previous=plan;
  const before=JSON.stringify(snapshot.fields.map(f=>[f.label,f.id,f.section,f.record_index,f.value,f.checked]));
  const result=await send('fill',{tabId,plan:prepared,site_authorized:true});
  adopt(result.snapshot);await prepare(false);
  const progressed=before!==JSON.stringify(snapshot.fields.map(f=>[f.label,f.id,f.section,f.record_index,f.value,f.checked]));
  const retryable=result.errors.length&&result.errors.every(e=>e.code==='CONTROL_CHANGED'||/^Control changed/.test(e.error));
  verified+=result.filled.length;
  if(depth<4&&((retryable&&depth<1)||(result.structure_changed&&!result.errors.length)||(progressed&&result.filled.length&&(!result.errors.length||retryable)&&(plan.actions.length||retryable))))return fillPlan(plan,depth+1,verified);
  for(const d of plan.drafts){const old=previous?.drafts?.find(o=>questionKey(o)===questionKey(d));if(old?.kind==='model_proposal'&&d.kind==='missing_fact')Object.assign(d,old,{index:d.index,token:d.token});}
  renderPlan();
  $('summary').textContent=`${verified} ${verified===1?'field':'fields'} verified. ${snapshot.fields.length} controls detected; ${plan.drafts.length} ${plan.drafts.length===1?'answer':'answers'} to review.`;
  if(result.errors.length)$('error').textContent=result.errors.map(e=>`${e.label||'Application page'}: ${e.error}`).join('\n');
  return result;
}
button('pair',async()=>{await send('pair',{code:$('pairCode').value,port:Number($('backendPort').value)});dashboard($('backendPort').value);await status();});
button('disconnect',async()=>{try{await send('disconnect');}finally{paired=false;reset();$('connection').textContent='Disconnected';$('pairSetup').hidden=false;}});
button('analyze',async()=>{captureEdits();adopt(await send('inspect',{tabId}),true);await prepare(false);$('summary').textContent=`${snapshot.fields.length} controls inspected. No fields changed.`;});
button('fill',async()=>{
  $('summary').textContent='Preparing your answers...';captureEdits();adopt(await send('inspect',{tabId}),true);
  if(snapshot.needs_login){$('summary').textContent='Sign in on the page first, then use Prepare & Fill. Passwords stay manual.';return;}
  await fillPlan(await prepare(false));
  if($('aiMode').checked)await prepare(true);
});
async function fillReviewed(drafts=plan?.drafts||[]){
  captureEdits();const answers=drafts.map(d=>{
    const value=(edits.has(questionKey(d))?edits.get(questionKey(d)):d.value)?.trim()||'';
    return {index:d.index,token:d.token,value,fact_id:d.fact_id&&value===d.value.trim()?d.fact_id:null,
            remember:$('rememberAnswers').checked};
  }).filter(a=>a.value);
  if(!answers.length)throw Error('Enter at least one verified answer first.');
  const prepared=await send('reviewed',{tabId,snapshot,answers});
  await fillPlan(prepared);
  if(prepared.remembered)$('summary').textContent+=` ${prepared.remembered} approved ${prepared.remembered===1?'answer':'answers'} saved locally.`;
}
button('applyReviewed',()=>fillReviewed());
button('chooseFile',async()=>{
  captureEdits();const result=await send('choose_file',{tabId,token:$('fileTarget').value,snapshot_id:snapshot.snapshot_id,site_authorized:true});
  adopt(result.snapshot);await prepare(false);$('summary').textContent=result.message;
});
button('next',async()=>{
  const result=await send('next',{tabId,token:snapshot.navigation[0].token,snapshot_id:snapshot.snapshot_id,site_authorized:true});
  edits.clear();adopt(result.snapshot,true);await prepare(false);
  $('summary').textContent=result.transition_verified?'Next step opened. Use Prepare & Fill to continue.':'Check the page for validation errors, then try again.';
});
async function createDocument(kind) {
  const context=job(),requestURL=tab.url;
  const lang=$('language').value==='auto'?(snapshot?.page_language?.toLowerCase().startsWith('it')?'it':'en'):$('language').value;
  $('summary').textContent='Preparing your document...';
  const draft=await send(kind,{letter:{language:lang,job_title:context.title,company:context.company,description:context.description.slice(0,6000),use_ai:$('aiMode').checked}});
  if(tab.url!==requestURL)throw Error('The vacancy changed while drafting. Prepare the document for the current role.');
  documentKind=kind==='cv'?'cv':'letter';$('letterText').maxLength=30000;
  documentURL=requestURL;documentJobKey=JSON.stringify([requestURL,context.title,context.company,context.description]);
  $('documentRole').textContent=[context.title,context.company].filter(Boolean).join(' · ')||'Current application';
  $('letterArea').hidden=false;$('letterHeading').textContent=kind==='cv'?'Curriculum Vitae':draft.language==='it'?'Lettera di motivazione':'Motivation letter';$('letterText').value=draft.value;
  $('summary').textContent=draft.source==='model_proposal'?'AI draft ready. Review every claim before exporting.':'Verified-fact draft ready for review.';
  if(draft.ai_error)$('error').textContent='AI refinement failed: '+draft.ai_error+' The factual draft is still ready.';
  actions();
}
button('letter',()=>createDocument('letter'));
button('cv',()=>createDocument('cv'));
function download(blob,filename) {
  const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
button('downloadLetter',async()=>{
  download(new Blob([$('letterText').value],{type:'text/plain;charset=utf-8'}),'forgeapply-'+documentKind+'.txt');
});
button('downloadPDF',async()=>{
  const result=await send('document_pdf',{document:{text:$('letterText').value,kind:documentKind,reviewed:true}});
  download(new Blob([Uint8Array.from(atob(result.base64),c=>c.charCodeAt(0))],{type:'application/pdf'}),result.filename);
});
button('attachPDF',async()=>{
  const context=job();
  if(tab?.url!==documentURL||documentJobKey!==JSON.stringify([tab?.url,context.title,context.company,context.description]))throw Error('The application changed. Generate and review a document for the current role.');
  const result=await send('attach_document',{tabId,url:documentURL,token:$('fileTarget').value,snapshot_id:snapshot.snapshot_id,reviewed:true,
    document:{text:$('letterText').value,kind:documentKind,reviewed:true}});
  adopt(result.snapshot);await prepare(false);$('summary').textContent=result.message;
});
button('saveJob',async()=>{const result=await send('save_job',{job:job()});$('summary').textContent=`Job ${result.id}: ${result.created?'saved':'already tracked'}`;});
button('match',async()=>{$('matchResult').textContent=JSON.stringify(await send('match',{job:job()}),null,2);});
button('manualAnswer',async()=>{$('manualAnswerResult').textContent=JSON.stringify(await send('manual_answer',{question:$('manualQuestion').value}),null,2);});
async function models() {
  try{const inventory=await send('models');$('localModel').replaceChildren(...[...new Set([inventory.selected,...inventory.models])].map(name=>{const option=document.createElement('option');option.value=name;option.textContent=name+(inventory.models.includes(name)?'':' (not installed)');option.disabled=!inventory.models.includes(name);return option;}));$('localModel').value=inventory.selected;$('modelResult').textContent=inventory.available?'Choose a model, then Use selected model. Test current model checks JSON without personal data.':'Ollama is unavailable. Start Ollama, then refresh models.';}catch(error){$('error').textContent=error.message;}
}
button('useModel',async()=>{const selected=await send('choose_model',{model:$('localModel').value});await status();$('modelResult').textContent='Selected '+selected.model+'. Context and output settings were preserved. Use Test current model to verify inference.';});
button('refreshModels',models);
button('testModel',async()=>{$('modelResult').textContent='Testing the current model with synthetic data...';const result=await send('test_model');$('modelResult').textContent=(result.ok?'Passed: ':'Failed: ')+(result.model||'')+' — '+result.detail;});
$('settingsToggle').addEventListener('click',()=>{$('advanced').open=!$('advanced').open;});
$('advanced').addEventListener('toggle',async()=>{if($('advanced').open&&paired){await models();try{$('activity').textContent=(await send('activity')).map(e=>e.action+': '+e.detail).join('\n');}catch(error){$('error').textContent=error.message;}}});
$('language').addEventListener('change',async()=>{edits.clear();await chrome.storage.local.set({answerLanguage:$('language').value});if(snapshot&&!busy){busy=true;actions();try{await prepare(false);}catch(error){$('error').textContent=error.message;}finally{busy=false;actions();}}});
$('sidepanel').addEventListener('click',()=>{if(tabId){chrome.storage.session.set({requestedTab:tabId});chrome.sidePanel.open({tabId}).catch(error=>$('error').textContent=error.message);}});
$('reloadAssistant').addEventListener('click',()=>chrome.runtime.reload());
chrome.tabs.onActivated.addListener(async info=>{
  if(new URLSearchParams(location.search).has('tab')||targetWindowId!==null&&info.windowId!==targetWindowId)return;
  if(info.tabId===tabId)return;
  const candidate=await chrome.tabs.get(info.tabId).catch(()=>null);
  if(!candidate||candidate.url?.startsWith(chrome.runtime.getURL('')))return;
  if(busy){pendingTab=info.tabId;return;}
  await current(info.tabId);
});
chrome.tabs.onUpdated.addListener((id,change)=>{
  if(id===tabId&&change.url){
    if(busy){if(tab)tab.url=change.url;$('site').textContent=change.url;}
    else current(id);
  }
});
window.addEventListener('focus',()=>{if(!busy&&!paired)status();});
chrome.storage.onChanged.addListener((changes,area)=>{if(area==='session'&&changes.pendingInspection?.newValue){const result=changes.pendingInspection.newValue;if(result.tabId===tabId){if(result.snapshot)adopt(result.snapshot,true);else $('error').textContent=result.error;chrome.storage.session.remove('pendingInspection');}}});
(async()=>{
  const {backendPort=8765,answerLanguage='auto',aiMode=true}=await chrome.storage.local.get(['backendPort','answerLanguage','aiMode']);
  $('backendPort').value=backendPort;$('language').value=answerLanguage;$('aiMode').checked=aiMode;dashboard(backendPort);
  const explicit=new URLSearchParams(location.search).get('tab');
  const {requestedTab,pendingInspection,lastAuthorizedTab}=await chrome.storage.session.get(['requestedTab','pendingInspection','lastAuthorizedTab']);
  const active=(await chrome.tabs.query({active:true,currentWindow:true}))[0];
  await current(explicit?Number(explicit):requestedTab||(active?.url?.startsWith(chrome.runtime.getURL(''))?lastAuthorizedTab:active?.id));
  if(pendingInspection?.tabId===tabId){if(pendingInspection.snapshot)adopt(pendingInspection.snapshot,true);else $('error').textContent=pendingInspection.error;}
  await chrome.storage.session.remove(['requestedTab','pendingInspection']);await status();
  if(paired&&tab&&!tab.restricted){
    busy=true;actions();
    try{
      adopt(await send('inspect',{tabId}),true);
      if(snapshot.needs_login)$('summary').textContent='Sign in on the page first. Passwords stay manual.';
      else{await prepare(false);$('summary').textContent=`${snapshot.fields.length} controls detected. Ready to prepare and fill.`;}
    }catch(error){$('error').textContent=error.message;}
    finally{busy=false;actions();}
  }
})();
$('aiMode').addEventListener('change',()=>chrome.storage.local.set({aiMode:$('aiMode').checked}));
