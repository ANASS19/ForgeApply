// SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
// SPDX-License-Identifier: Apache-2.0
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let allJobs=[]; let browserSnapshotId=null;
const subtitles={dashboard:'Grounded memory. Reviewed answers. Verified browser actions.',jobs:'Prioritized jobs with duplicate protection and auditable statuses.',browser:'Real local browser, deterministic filling, optional LLM/vision fallback.',profile:'The facts and documents used for applications.',answers:'Reusable, verified answers to screening questions.',sources:'Bulk discovery without clicking each job.',settings:'Configure your model provider and inference settings.'};
function alertMsg(message, bad=false){const e=$('notice');e.hidden=false;e.textContent=message;e.className=bad?'error':'success';clearTimeout(window._toast);window._toast=setTimeout(()=>e.hidden=true,9000)}
async function api(path,options={}){try{const r=await fetch('/api'+path,options);const data=await r.json().catch(()=>({detail:'Unexpected response'}));if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data}catch(e){alertMsg(e.message,true);throw e}}
function post(path,body){return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
function put(path,body){return api(path,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
function formData(form){return Object.fromEntries(new FormData(form).entries())}
function showTab(tab){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab===tab));document.querySelectorAll('.panel').forEach(x=>x.classList.toggle('active',x.id===tab));$('pageTitle').textContent={dashboard:'Application dashboard',jobs:'Job queue',browser:'Browser agent',profile:'Candidate and CVs',answers:'Screening answers',sources:'Job discovery',settings:'AI settings'}[tab];$('pageSub').textContent=subtitles[tab];({dashboard:loadDashboard,jobs:loadJobs,profile:loadProfile,answers:loadAnswers,sources:loadBoards,settings:loadSettings}[tab]||(()=>{}))()}
document.querySelectorAll('.tab').forEach(x=>x.addEventListener('click',()=>showTab(x.dataset.tab)));
async function loadDashboard(){loadSetup();const stats=await api('/stats');$('stats').innerHTML=['total','discovered','queued','prepared','submitted','blocked'].map(x=>`<div class="stat"><small>${esc(x)}</small><strong>${stats[x]||0}</strong></div>`).join('');const jobs=await api('/jobs?limit=8');$('recentJobs').innerHTML=jobs.map(j=>`<div class="miniJob"><div><strong>${esc(j.title)}</strong><small>${esc(j.company)} · ${esc(j.location)}</small></div><span class="status ${esc(j.status)}">${esc(j.status)}</span></div>`).join('')||'<p class="muted">No jobs imported yet.</p>'}
async function loadJobs(){const s=encodeURIComponent($('jobStatus').value),q=encodeURIComponent($('jobSearch').value);allJobs=await api(`/jobs?status=${s}&search=${q}`);$('jobRows').innerHTML=allJobs.map(j=>`<tr><td><strong>${esc(j.title)}</strong><small><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">Original listing</a>${j.origin_url?` | <a href="${esc(j.origin_url)}" target="_blank" rel="noopener noreferrer">Source opportunity</a>`:''} · ${esc(j.language.toUpperCase())}</small></td><td>${esc(j.company)}<small>${esc(j.location)}</small></td><td>${j.score}</td><td><span class="status ${esc(j.status)}">${esc(j.status)}</span></td><td><div class="buttons compact"><button class="small" onclick="openJob(${j.id})">Open</button><select onchange="changeStatus(${j.id},this.value)"><option value="">Set status</option>${['queued','prepared','submitted','blocked','skipped','rejected'].map(s=>`<option>${s}</option>`).join('')}</select></div></td></tr>`).join('')||'<tr><td colspan="5">No jobs found. Import CSV or add ATS sources.</td></tr>'}
async function openJob(id){const j=allJobs.find(x=>x.id===id);if(!j)return;showTab('browser');$('browserUrl').value=j.url;$('submitJobId').value=id;$('allowResumeUpload').checked=false;await navigateBrowser();if(j.status==='discovered')await put(`/jobs/${id}/status`,{status:'opened'}).catch(()=>{})}
async function changeStatus(id,status){if(!status)return;if(status==='submitted'&&!confirm('Only mark Submitted if you personally saw a submission confirmation. Confirm?')){loadJobs();return}await put(`/jobs/${id}/status`,{status,note:status==='submitted'?'Manually confirmed by candidate':'',acknowledged:status==='submitted'});alertMsg('Status saved');loadJobs()}
$('addJob').onsubmit=async e=>{e.preventDefault();await post('/jobs',formData(e.target));e.target.reset();loadJobs();alertMsg('Job added')};
function downloadJobs(){window.location='/api/export'}
async function loadProfile(){const p=await api('/profile');for(const [k,v] of Object.entries(p)){const el=$('profileForm').elements.namedItem(k);if(el)el.value=v} $('cvEn').textContent=p.resume_en||'No English CV yet';$('cvIt').textContent=p.resume_it||'No Italian CV yet';$('candidateContext').textContent=JSON.stringify(await api('/candidate-context'),null,2);await loadBackgroundEditor()}
$('profileForm').onsubmit=async e=>{e.preventDefault();await put('/profile',{data:formData(e.target)});alertMsg('Profile saved')};
async function uploadCV(lang){const input=$(lang==='en'?'uploadEn':'uploadIt');if(!input.files?.length){alertMsg('Choose a file first',true);return}const fd=new FormData();fd.append('file',input.files[0]);await api(`/resumes/${lang}`,{method:'POST',body:fd});alertMsg('CV saved');loadProfile()}
async function loadAnswers(){const [answers,profile]=await Promise.all([api('/answers'),api('/profile')]);$('answersList').innerHTML=answers.map(a=>{const key=a.fact_path?.replace(/^profile\./,'');const answer=key?(profile[key]||'Profile value is empty — answer paused'):a.answer;return `<div class="miniJob"><div><strong><code>${esc(a.pattern)}</code></strong><small>${esc(answer)}</small><small>${key?'Uses current profile: '+esc(key):'Verified saved answer'}${a.scope_host?' · '+esc(a.scope_host):''}</small></div><button class="secondary small" onclick="deleteAnswer(${a.id})">Remove</button></div>`}).join('')||'<p class="muted">No reusable answers yet.</p>'}
$('answerForm').onsubmit=async e=>{e.preventDefault();await post('/answers',formData(e.target));e.target.reset();loadAnswers();alertMsg('Answer saved')};
async function deleteAnswer(id){await api(`/answers/${id}`,{method:'DELETE'});loadAnswers()}
async function loadBoards(){const boards=await api('/boards');$('boardsList').innerHTML=Object.entries(boards).flatMap(([ats,items])=>items.map(slug=>`<div class="miniJob"><div><strong>${esc(slug)}</strong><small>${esc(ats)}</small></div><button class="secondary small" onclick="removeBoard('${esc(ats)}','${esc(slug)}')">Remove</button></div>`)).join('')||'<p class="muted">No boards configured yet.</p>'}
$('boardForm').onsubmit=async e=>{e.preventDefault();await post('/boards',formData(e.target));e.target.reset();loadBoards();alertMsg('Board saved')};
async function removeBoard(ats,slug){await api(`/boards/${encodeURIComponent(ats)}/${encodeURIComponent(slug)}`,{method:'DELETE'});loadBoards()}
async function syncBoards(){alertMsg('Reading public boards...');const r=await post('/discover',{});alertMsg(`Discovery complete: ${r.added} added, ${r.updated} updated, ${r.errors.length} errors. ${r.errors.slice(0,2).join(' ')}`)}
async function importCSV(){const f=$('csvFile').files?.[0];if(!f){alertMsg('Choose a CSV file',true);return}const fd=new FormData();fd.append('file',f);const r=await api('/import',{method:'POST',body:fd});alertMsg(`Imported ${r.added} new jobs and matched ${r.updated} existing.`)}
async function loadSettings(){const d=await api('/llm');for(const [k,v]of Object.entries(d)){const el=$('llmForm').elements.namedItem(k);if(el){if(el.type==='checkbox')el.checked=!!v;else el.value=v}}providerHint();await loadProviderModels(d.provider).catch(()=>{});}
function inferenceSettings(){const f=$('llmForm');return {...formData(f),allow_remote:f.elements.allow_remote.checked,think:f.elements.think.checked};}
$('llmForm').onsubmit=async e=>{e.preventDefault();await put('/llm',inferenceSettings());alertMsg('Model settings saved')};
async function navigateBrowser(){alertMsg('Opening visible Chromium browser...');const r=await post('/browser/open',{url:$('browserUrl').value});renderBrowser(r);alertMsg('Browser opened')}
async function snapshotBrowser(){renderBrowser(await api('/browser/state'))}
function renderBrowser(state){browserSnapshotId=state.snapshot_id;$('browserUrl').value=state.url||$('browserUrl').value;$('browserMeta').textContent=state.title||'';$('browserText').textContent=(state.text||'').slice(0,4500);$('browserFields').innerHTML=(state.fields||[]).map(f=>`<div class="fieldrow"><small>#${f.index} · ${esc(f.tag)} / ${esc(f.type)}</small><strong>${esc(f.label||f.name||f.id||'Unlabelled field')}</strong><div class="buttons compact"><input id="field_${f.index}" value="${esc(['checkbox','radio'].includes(f.type)?String(f.checked):f.value)}" placeholder="Enter response"/><button class="small" onclick="manualFill(${f.index})">Fill</button></div></div>`).join('')||'<p class="muted">No visible fields found</p>'}
async function prepareAgent(){const id=Number($('submitJobId').value);if(!id){alertMsg('Choose a job from the queue first',true);return}alertMsg('Agent is preparing the application; inspect the visible browser...');const r=await post('/browser/agent/prepare',{job_id:id,use_ai:$('useAI').checked,use_vision:false,max_steps:8,allow_uploads:$('allowResumeUpload').checked});alertMsg('Agent: '+r.status+(r.reason?' · '+r.reason:''));if(r.unknown?.length)$('unknownQuestions').innerHTML=r.unknown.map(esc).join('<hr>');if(r.suggestions?.length)$('unknownQuestions').innerHTML+='<p>AI proposals require review:</p>'+r.suggestions.map(s=>`<div class="unknown">#${s.field_index}: ${esc(s.value)}</div>`).join('');if(r.journal)$('agentTrace').textContent=r.journal.map(e=>`${e.phase} | ${e.action} ${e.detail}`).join('\n');snapshotBrowser()}
async function ocrScreen(){alertMsg('Reading screenshot with the selected OCR engine...');const r=await post('/browser/ocr',{mode:$('ocrMode').value});$('unknownQuestions').textContent=r.text||JSON.stringify(r);alertMsg('Screenshot text extracted')}
async function manualFill(i){await post('/browser/fill',{index:i,value:$(`field_${i}`).value,snapshot_id:browserSnapshotId});alertMsg('Field filled')}
async function autoFill(vision=false){alertMsg(vision?'Asking multimodal AI to inspect the form...':'Filling saved and known answers...');const r=await post('/browser/autofill',{use_ai:vision||$('useAI').checked,use_vision:vision});$('unknownQuestions').innerHTML=(r.unknown||[]).map(x=>`<div class="unknown">${esc(x)}</div>`).join('')||'No unanswered required fields identified.';if(r.suggestions?.length)$('unknownQuestions').innerHTML+='<p>AI proposals require your review:</p>'+r.suggestions.map(s=>`<div class="unknown">#${s.field_index}: ${esc(s.value)}</div>`).join('');alertMsg(`${r.filled.length} fields filled; ${r.unknown.length} questions need review.`);snapshotBrowser()}
async function browserClick(kind){const s=await post('/browser/click',{kind});renderBrowser(s)}
async function uploadResume(lang){const r=await post(`/browser/resume/${lang}`,{});alertMsg('Uploaded '+r.uploaded)}
async function getScreenshot(){await fetch('/api/browser/screenshot');$('screen').src='/api/browser/screenshot?t='+Date.now();$('screen').hidden=false}
async function submitBrowser(){const id=Number($('submitJobId').value);if(!id){alertMsg('Select a job from your queue first',true);return}if($('submissionMode').value==='manual'){alertMsg('Click Submit in your browser, then use “I submitted it manually” after seeing confirmation.');return}if(!confirm('You are approving the FINAL submission of this job application. Proceed?'))return;const r=await post('/browser/submit',{job_id:id,approved:true});alertMsg(r.submitted_verified?'Application confirmed submitted!':'Submission not confirmed; verify manually.',!r.submitted_verified)}
async function manualSubmitted(){const id=Number($('submitJobId').value);if(!id){alertMsg('Select a job first',true);return}if(!confirm('Did you see a successful application submission confirmation in the live browser?'))return;await put(`/jobs/${id}/status`,{status:'submitted',note:'Candidate visually confirmed successful submission',acknowledged:true});alertMsg('Marked submitted')}
loadDashboard();

async function cancelAgent(){await post('/browser/agent/cancel',{});alertMsg('Pause requested; inspect the browser before resuming.')}
async function checkProvider(){const r=await post('/llm/health',{});$('providerHealth').textContent=JSON.stringify(r,null,2);modelOptions(r.models||[]);if(r.model_details&&!providerModels.some(m=>m.id===r.model_details.id))providerModels.push(r.model_details);modelHint();}
async function testProvider(){$('providerHealth').textContent='Testing saved model with synthetic data...';const r=await post('/llm/test',{});$('providerHealth').textContent=JSON.stringify(r,null,2)}
function modelOptions(names){$('availableModels').replaceChildren(...names.map(name=>{const option=document.createElement('option');option.value=name;return option;}));}
let providerModels=[];
const providerDefaults={ollama:{base:'http://127.0.0.1:11434',key:''},openai:{base:'https://api.openai.com/v1',key:'OPENAI_API_KEY'},anthropic:{base:'https://api.anthropic.com/v1',key:'ANTHROPIC_API_KEY'},deepseek:{base:'https://api.deepseek.com',key:'DEEPSEEK_API_KEY'},openrouter:{base:'https://openrouter.ai/api/v1',key:'OPENROUTER_API_KEY'}};
function providerHint(){const provider=$('llmForm').elements.provider.value,defaults=providerDefaults[provider];$('sessionApiKey').value='';$('sessionKeyStatus').textContent='Keys entered here stay only in backend process memory. Re-enter after restarting ForgeApply.';$('providerKeySetup').hidden=provider==='ollama';$('providerSetup').textContent=provider==='ollama'?'Choose any installed model. No API key is needed.':provider==='openrouter'?'Choose or paste an exact OpenRouter model ID (including :free where applicable). Enter your key below, or set OPENROUTER_API_KEY before startup. Enable remote inference, Save, then Test. Enabled inference sends data through OpenRouter to the routed model provider. Loading the public catalog sends no candidate data.':'Enter your key below or set '+defaults.key+' before startup. Enter your model ID, enable remote inference, then Save and Test. Custom compatible endpoints can use their own *_API_KEY variable.';}
function modelHint(){const model=$('llmForm').elements.model.value,details=providerModels.find(m=>m.id===model);$('modelCapabilities').textContent=!details?'':(details.input_modalities.includes('image')?'Image input advertised. ':'Text input; use an image-capable model for screenshots. ')+(details.supported_parameters.includes('structured_outputs')?'JSON schema advertised.':details.supported_parameters.includes('response_format')?'JSON mode advertised.':'JSON validated by ForgeApply; native JSON mode is not advertised.')+' Use Test saved model to verify inference.';}
async function loadProviderModels(provider=$('llmForm').elements.provider.value){
  if(!['ollama','openrouter'].includes(provider))return;
  const inventory=await api(provider==='openrouter'?'/llm/openrouter-models':'/llm/local-models');
  if($('llmForm').elements.provider.value!==provider)return;
  providerModels=inventory.model_details||[];modelOptions(inventory.models||[]);modelHint();
}
$('llmForm').elements.model.addEventListener('input',modelHint);
$('refreshProviderModels').addEventListener('click',()=>loadProviderModels().catch(()=>{}));
$('useSessionKey').addEventListener('click',async()=>{
  const form=$('llmForm'),input=$('sessionApiKey'),button=$('useSessionKey');
  if(!form.reportValidity())return;
  if(!input.value.trim()){$('sessionKeyStatus').textContent='Enter the key in the masked field first.';return;}
  const settings=inferenceSettings();button.disabled=true;
  try{await put('/llm',settings);const result=await post('/llm/session-key',{provider:settings.provider,base_url:settings.base_url,api_key_env:settings.api_key_env,key:input.value});input.value='';$('sessionKeyStatus').textContent='Key configured in '+result.api_key_env+' for this backend session. Run Test saved model. Re-enter after a backend restart.';alertMsg('Provider saved; session key configured');}
  catch{$('sessionKeyStatus').textContent='The key could not be configured. Check the provider settings and try again.';}
  finally{button.disabled=false;}
});
$('llmForm').elements.provider.addEventListener('change',()=>{const f=$('llmForm'),provider=f.elements.provider.value,defaults=providerDefaults[provider];f.elements.base_url.value=defaults.base;f.elements.api_key_env.value=defaults.key;f.elements.model.value='';f.elements.allow_remote.checked=false;$('inferencePreset').value='';providerModels=[];modelOptions([]);modelHint();providerHint();loadProviderModels(provider).catch(()=>{});});
async function inspectAccessibility(){const r=await post('/browser/tool',{action:'accessibility'});$('agentTrace').textContent=r.frames.map(f=>`Frame ${f.index}\n${f.tree}`).join('\n')}
async function scrollBrowser(){renderBrowser(await post('/browser/tool',{action:'scroll',direction:'down'}))}

async function approveDestination(){const id=Number($('submitJobId').value);if(!id)return;const url=$('browserUrl').value;if(!confirm('Allow candidate data and CV upload to this destination for the selected job? '+url))return;await post('/browser/approve-destination',{job_id:id});alertMsg('Destination approved for this job; resume preparation.')}

async function extensionPairCode(){const r=await post('/extension/pairing-code',{});$('extensionPairCode').textContent=r.code+' (expires in 5 minutes)';await extensionSessions()}
async function extensionSessions(){const rows=await api('/extension/sessions');$('extensionSessions').replaceChildren(...rows.map(row=>{const e=document.createElement('div');e.className='miniJob';const label=document.createElement('small');label.textContent=row.extension_id;const b=document.createElement('button');b.textContent='Revoke';b.onclick=async()=>{await api('/extension/sessions/'+row.extension_id,{method:'DELETE'});extensionSessions()};e.append(label,b);return e}))}

$('inferencePreset').onchange=e=>{if(!e.target.value)return;const f=$('llmForm');f.elements.provider.value='ollama';f.elements.base_url.value=providerDefaults.ollama.base;f.elements.api_key_env.value='';f.elements.allow_remote.checked=false;f.elements.model.value=e.target.value;f.elements.num_ctx.value=8192;f.elements.num_predict.value=768;f.elements.temperature.value=0;f.elements.think.checked=false;providerModels=[];modelHint();providerHint();loadProviderModels('ollama').catch(()=>{});alertMsg('Preset selected. Save model settings to apply; human review remains required.')}

async function previewDocument(lang){const r=await api('/resumes/'+lang+'/text');$('documentPreview').textContent=r.filename+'\n'+r.note+'\n\n'+r.text}

async function loadSetup(){
  try{
    const [profile,sessions]=await Promise.all([api('/profile'),api('/extension/sessions')]);
    const ready=['first_name','last_name','email'].every(k=>profile[k]);
    $('setupSummary').textContent=[ready?'Profile ready':'Add your contact details',profile.resume_en||profile.resume_it?'CV saved':'Add a CV',sessions.length?'Extension connected':'Connect your Chrome extension'].join(' | ');
  }catch{$('setupSummary').textContent='Check the local backend connection.';}
}
async function openExtensionSetup(){showTab('settings');await extensionSessions();$('extensionSetup').scrollIntoView({behavior:'smooth'});}
loadSetup();

let background=null,languageRows=[];
async function loadBackgroundEditor(){
  background=await api('/candidate-context');
  for(const key of ['education','experience','certifications'])background[key]??=[];
  languageRows=Object.entries(background.languages||{}).map(([name,level])=>({name,level}));
  renderBackgroundEditor();
}
function renderBackgroundEditor(){
  const root=$('backgroundEditor'),previousSkills=$('verifiedSkills')?.value,opened=new Set([...root.querySelectorAll('details[open][data-section]')].map(e=>e.dataset.section));root.replaceChildren();
  const definitions={
    experience:{title:'Work experience',fields:[['title','Job title'],['employer','Company'],['start','From (YYYY-MM, if known)'],['end','To (YYYY-MM, if known)'],['summary','Description','textarea'],['currently_work_here','I currently work here - verified','checkbox']]},
    education:{title:'Education',fields:[['institution','School / university'],['degree','Degree / field of study'],['level','Qualification level','level'],['start_year','Start year'],['graduated_at','Graduation date (YYYY-MM or YYYY-MM-DD)'],['grade','Final grade (original scale)'],['gpa','GPA (only if explicitly known)'],['completed','Qualification completed','checkbox']]},
    certifications:{title:'Certifications',fields:[['name','Certification'],['issuer','Issuing organization'],['issued_at','Issued (YYYY-MM, if known)'],['expires_at','Expires (if applicable)'],['credential_id','Credential ID (optional)'],['url','Credential URL (optional)']]},
    languages:{title:'Languages',fields:[['name','Language'],['level','Verified proficiency (e.g. Advanced / C1)']]}
  };
  for(const [key,definition] of Object.entries(definitions)){
    const rows=key==='languages'?languageRows:background[key],section=document.createElement('details');section.dataset.section=key;section.open=opened.has(key);
    const summary=document.createElement('summary');summary.textContent=definition.title+' ('+rows.length+')';section.append(summary);
    rows.forEach((record,index)=>{
      const card=document.createElement('div');card.className='backgroundRecord';card.dataset.record=index;
      const heading=document.createElement('h3');heading.textContent=definition.title+' '+(index+1);card.append(heading);
      if(record.verified===false||record.current_employment_verified===false){const warning=document.createElement('p');warning.className='muted';warning.textContent='This record has an unverified flag. It will not be used automatically until the relevant information is verified.';card.append(warning);}
      const fields=document.createElement('div');fields.className='formgrid';
      for(const [name,text,type] of definition.fields){
        const label=document.createElement('label');label.textContent=text;
        const input=document.createElement(type==='textarea'?'textarea':type==='level'?'select':'input');input.dataset.field=name;input.setAttribute('aria-label',definition.title+' '+(index+1)+' - '+text);
        if(type==='checkbox'){input.type='checkbox';input.checked=record[name]===true;}
        else if(type==='level')for(const [value,text] of [['','Choose'],['bachelors',"Bachelor's degree"],['masters',"Master's degree"],['doctorate','Doctorate'],['other','Other']]){const option=document.createElement('option');option.value=value;option.textContent=text;input.append(option);}
        if(type!=='checkbox')input.value=record[name]??'';
        input.addEventListener(type==='checkbox'?'change':'input',()=>{record[name]=type==='checkbox'?input.checked:input.value;record.source='user:profile-editor';if(name==='currently_work_here')record.current_employment_verified=true;});
        label.append(input);fields.append(label);
      }
      card.append(fields);
      const remove=document.createElement('button');remove.type='button';remove.className='secondary small';remove.textContent='Remove';remove.onclick=()=>{rows.splice(index,1);renderBackgroundEditor();const reopened=root.querySelector('[data-section='+key+']');reopened.open=true;};card.append(remove);section.append(card);
    });
    const add=document.createElement('button');add.type='button';add.className='secondary small';add.textContent='Add '+({experience:'experience',education:'education',languages:'language',certifications:'certification'})[key];
    add.onclick=()=>{rows.push(key==='education'?{completed:false,source:'user:profile-editor'}:{source:'user:profile-editor'});renderBackgroundEditor();const reopened=root.querySelector('[data-section='+key+']');reopened.open=true;reopened.querySelector('.backgroundRecord:last-of-type input')?.focus();};
    section.append(add);root.append(section);
  }
  const skills=document.createElement('details'),summary=document.createElement('summary');skills.dataset.section='skills';skills.open=opened.has('skills');summary.textContent='Verified skills';skills.append(summary);
  const label=document.createElement('label');label.textContent='One skill per line. Planned or learning-only skills remain excluded.';
  const area=document.createElement('textarea');area.id='verifiedSkills';area.rows=6;
  area.value=previousSkills??[...new Set(Object.entries(background.skills||{}).filter(([k])=>!['learning','planned','independent_learning'].includes(k)).flatMap(([,v])=>v))].join('\n');label.append(area);skills.append(label);root.append(skills);
}
$('backgroundForm').onsubmit=async event=>{
  event.preventDefault();if(!background)return;
  const wanted=new Set($('verifiedSkills').value.split(/[\n,;]/).map(s=>s.trim()).filter(Boolean));
  const skills={...background.skills};
  for(const [group,values] of Object.entries(skills))if(!['learning','planned','independent_learning'].includes(group)){skills[group]=values.filter(s=>wanted.has(s));for(const skill of skills[group])wanted.delete(skill);}
  skills.additional=[...(skills.additional||[]),...wanted];
  const languages={};for(const row of languageRows)if(row.name?.trim()&&row.level?.trim())languages[row.name.trim()]=row.level.trim();
  const data={...background,languages,skills,source:'user:profile-editor'};
  for(const [key,fields] of Object.entries({education:['institution','degree'],experience:['title','employer'],certifications:['name','issuer']}))data[key]=data[key].filter(record=>fields.some(field=>String(record[field]||'').trim()));
  await put('/candidate-context',data);background=data;$('candidateContext').textContent=JSON.stringify(data,null,2);$('backgroundStatus').textContent='Background saved locally. No application was submitted.';alertMsg('Verified background saved');
};
