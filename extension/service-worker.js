
chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'}).catch(()=>{});
const WORKER_VERSION='0.4.3';
chrome.runtime.onInstalled.addListener(()=>{
  chrome.contextMenus.create({id:'forge-analyze',title:'ForgeApply — Analyze this page',contexts:['page','editable']});
});
chrome.contextMenus.onClicked.addListener((info,tab)=>{
  if(info.menuItemId==='forge-analyze'&&tab?.id){
    chrome.storage.session.set({requestedTab:tab.id});chrome.sidePanel.open({tabId:tab.id}).catch(()=>{});
    pageCall(tab.id,'inspect').then(snapshot=>chrome.storage.session.set({pendingInspection:{tabId:tab.id,snapshot}}),
      error=>chrome.storage.session.set({pendingInspection:{tabId:tab.id,error:error.message}}));
  }
});
function policy(url) {
  const host=new URL(url).hostname.toLowerCase();
  const restricted=['linkedin.com','indeed.com','indeed.it','indeed.co.uk'].some(d=>host===d||host.endsWith('.'+d))||/(^|\.)indeed\.(?:com|[a-z]{2}|co\.[a-z]{2}|com\.[a-z]{2})$/.test(host);
  return {restricted,host};
}
async function api(path,method='GET',body) {
  if(!['/pair','/status','/plan','/jobs','/match','/activity','/answer','/reviewed-plan','/motivation-letter','/cv-draft','/document-pdf','/local-models','/local-model','/agent/decision','/agent/run'].includes(path))throw Error('Unsupported bridge operation');
  const {pairToken,backendPort=8765}=await chrome.storage.local.get(['pairToken','backendPort']);
  if(!Number.isInteger(Number(backendPort))||backendPort<1024||backendPort>65535)throw Error('Invalid local backend port');
  const BASE='http://127.0.0.1:'+Number(backendPort);
  const headers={'Content-Type':'application/json','X-ForgeApply-Extension':chrome.runtime.id};
  if(pairToken)headers.Authorization='Bearer '+pairToken;
  let response;
  try{response=await fetch(BASE+'/api/extension'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:AbortSignal.timeout(120000)});}catch{throw Object.assign(Error('Start the local ForgeApply backend, then retry.'),{code:'offline'});}
  const data=await response.json();
  if(!response.ok){
    // Report validation locations, never Pydantic's input values (which can contain profile facts).
    const fields=response.status===422&&Array.isArray(data.detail)?data.detail.slice(0,5).map(e=>e.loc.join('.')+' ('+e.type+')').join(', '):'';
    const detail=fields?'Request validation failed for '+path+': '+fields:typeof data.detail==='string'?data.detail:'The request could not be completed. Inspect the page and retry.';
    throw Object.assign(Error(detail),{code:response.status===401?'pair_required':response.status===422?'validation_failed':'request_failed'});
  }
  return data;
}
async function tabInfo(tabId) {
  const tab=await chrome.tabs.get(tabId);
  if(!tab.url)throw Object.assign(Error('Backend connected. Page access is needed: click the ForgeApply toolbar icon on this application tab, or use its right-click menu.'),{code:'permission_required'});
  if(!/^https?:\/\//.test(tab.url))throw Error('Open an application webpage and invoke ForgeApply from its toolbar icon. Browser/internal pages are unsupported.');
  return {id:tab.id,window_id:tab.windowId,url:tab.url,...policy(tab.url)};
}
async function pageCall(tabId,operation,args=[]) {
  const tab=await tabInfo(tabId);if(tab.restricted)throw Error('Native LinkedIn/Indeed inspection and automation are disabled. Import the URL and supply job details manually.');
  try {
    await chrome.scripting.executeScript({target:{tabId},files:['content.js']});
    const results=await chrome.scripting.executeScript({target:{tabId},func:async(op,params)=>globalThis.ForgeApplyPage[op](...params),args:[operation,args]});
    if(!results[0]?.result)throw Error('Page inspection returned no state');return results[0].result;
  }catch(error){throw Error(error.message+' If access was revoked, invoke the toolbar or context menu on this tab again.');}
}
async function captureCurrentTab(tabId){
  const current=await tabInfo(tabId);if(current.restricted)throw Error('This platform stays manual.');
  let changed=false;
  const activated=info=>{if(info.windowId===current.window_id&&info.tabId!==tabId)changed=true;};
  const updated=(id,change)=>{if(id===tabId&&change.url&&change.url!==current.url)changed=true;};
  chrome.tabs.onActivated.addListener(activated);chrome.tabs.onUpdated.addListener(updated);
  try{
  const active=(await chrome.tabs.query({active:true,windowId:current.window_id}))[0];
  if(active?.id!==tabId)throw Error('Activate the authorized application tab before taking its screenshot.');
  let url=await chrome.tabs.captureVisibleTab(current.window_id,{format:'jpeg',quality:65});
  const after=(await chrome.tabs.query({active:true,windowId:current.window_id}))[0];
  if(changed||after?.id!==tabId||after.url!==current.url)throw Error('The authorized tab changed during screenshot capture. Image discarded.');
  const raw=atob(url.split(',')[1]),mime=url.slice(5,url.indexOf(';'));
  const bitmap=await createImageBitmap(new Blob([Uint8Array.from(raw,char=>char.charCodeAt(0))],{type:mime}));
  const scale=Math.min(1,1280/bitmap.width),canvas=new OffscreenCanvas(Math.round(bitmap.width*scale),Math.round(bitmap.height*scale));
  canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  const blob=await canvas.convertToBlob({type:'image/jpeg',quality:.65});
  const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';for(let start=0;start<bytes.length;start+=8192)binary+=String.fromCharCode(...bytes.subarray(start,start+8192));
  if(changed)throw Error('The authorized tab changed during screenshot capture. Image discarded.');
  return {url:'data:image/jpeg;base64,'+btoa(binary),page_url:current.url};
  }finally{chrome.tabs.onActivated.removeListener(activated);chrome.tabs.onUpdated.removeListener(updated);}
}
async function handle(message,sender) {
  if(sender.id!==chrome.runtime.id||!sender.url?.startsWith(chrome.runtime.getURL('panel.html')))throw Error('Only the extension UI may request privileged actions');
  switch(message.type) {
    case 'pair': {
      await chrome.storage.local.set({backendPort:Number(message.port||8765)});
      const result=await api('/pair','POST',{extension_id:chrome.runtime.id,code:message.code.trim()});
      await chrome.storage.local.set({pairToken:result.token});return {paired:true};
    }
    case 'disconnect':try{await api('/pair','DELETE');}finally{await chrome.storage.local.remove('pairToken');}return {disconnected:true};
    case 'status':return api('/status');
    case 'activity':return api('/activity');
    case 'tab':return tabInfo(message.tabId);
    case 'inspect':return pageCall(message.tabId,'inspect');
    case 'agent_decision':{const current=await tabInfo(message.tabId);if(current.restricted||current.url!==message.url)throw Error('Page changed; observe again.');const screenshot=message.use_vision&&message.use_ai?(await captureCurrentTab(message.tabId)).url.split(',')[1]:'';return api('/agent/decision','POST',{url:current.url,stage:message.stage,use_ai:message.use_ai,candidates:message.candidates,screenshot});}
    case 'agent_progress':return api('/agent/run','POST',message.run);
    case 'agent_history':return api('/agent/run');
    case 'screenshot':return captureCurrentTab(message.tabId);
    case 'plan': {
      const current=await tabInfo(message.tabId);
      if(current.url!==message.snapshot.url||current.restricted)throw Error('Destination changed or is restricted; analyze again.');
      return api('/plan','POST',{url:current.url,snapshot_id:message.snapshot.snapshot_id,fields:message.snapshot.fields,add_controls:message.snapshot.add_controls||[],site_authorized:message.site_authorized,use_ai:!!message.use_ai,page_text:message.use_ai?message.snapshot.page_text:'',language:message.language||'auto',page_language:message.snapshot.page_language||'',job_title:message.job?.title||message.snapshot.job?.title||'',company:message.job?.company||message.snapshot.job?.company||'',job_description:(message.job?.description||message.snapshot.job?.description||'').slice(0,6000)});
    }
    case 'fill': {
      if(!message.site_authorized)throw Error('Confirm site authorization before filling.');
      const tab=await tabInfo(message.tabId);if(tab.url!==message.plan.url||tab.restricted)throw Error('Page changed or restricted');
      return pageCall(message.tabId,'fill',[message.plan]);
    }
    case 'next':{
      if(!message.site_authorized)throw Error('Confirm site authorization first.');
      const before=await tabInfo(message.tabId);
      try{return await pageCall(message.tabId,'next',[message.token,message.snapshot_id]);}
      catch(error){
        // A full navigation destroys the injected call. Observe the new page without clicking twice.
        for(let i=0;i<5;i++){
          const after=await tabInfo(message.tabId);
          if(after.url!==before.url&&!after.restricted){try{return {transition_verified:true,snapshot:await pageCall(message.tabId,'inspect')};}catch{}}
          await new Promise(resolve=>setTimeout(resolve,150));
        }
        throw error;
      }
    }
    case 'choose_file':if(!message.site_authorized)throw Error('Confirm site authorization first.');return pageCall(message.tabId,'chooseFile',[message.token,message.snapshot_id]);
    case 'save_job':return api('/jobs','POST',message.job);
    case 'match':return api('/match','POST',message.job);
    case 'manual_answer':return api('/answer','POST',{question:message.question});
    case 'models':return api('/local-models');
    case 'choose_model':return api('/local-model','POST',{model:message.model});
    case 'letter':return api('/motivation-letter','POST',message.letter);
    case 'cv':return api('/cv-draft','POST',message.letter);
    case 'document_pdf':return api('/document-pdf','POST',message.document);
    case 'reviewed':{const current=await tabInfo(message.tabId);if(current.restricted||current.url!==message.snapshot.url)throw Error('Page changed; prepare again.');return api('/reviewed-plan','POST',{url:current.url,snapshot_id:message.snapshot.snapshot_id,fields:message.snapshot.fields,site_authorized:true,reviewed:true,answers:message.answers});}
    default:throw Error('Unknown extension request');
  }
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  handle(message,sender).then(data=>respond({ok:true,data,worker_version:WORKER_VERSION}),error=>respond({ok:false,error:error.message,error_code:error.code||'request_failed',worker_version:WORKER_VERSION}));return true;
});
