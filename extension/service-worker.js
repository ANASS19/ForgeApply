
chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'}).catch(()=>{});
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
  if(!['/pair','/status','/plan','/jobs','/match','/activity','/answer'].includes(path))throw Error('Unsupported bridge operation');
  const {pairToken,backendPort=8765}=await chrome.storage.local.get(['pairToken','backendPort']);
  if(!Number.isInteger(Number(backendPort))||backendPort<1024||backendPort>65535)throw Error('Invalid local backend port');
  const BASE='http://127.0.0.1:'+Number(backendPort);
  const headers={'Content-Type':'application/json','X-ForgeApply-Extension':chrome.runtime.id};
  if(pairToken)headers.Authorization='Bearer '+pairToken;
  let response;
  try{response=await fetch(BASE+'/api/extension'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:AbortSignal.timeout(120000)});}catch{throw Error('ForgeApply is offline. Start the local backend, then retry.');}
  const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
}
async function tabInfo(tabId) {
  const tab=await chrome.tabs.get(tabId);
  if(!tab.url||!/^https?:\/\//.test(tab.url))throw Error('Authorize an http(s) page using the toolbar or context menu. Browser/internal pages are unsupported.');
  return {id:tab.id,url:tab.url,...policy(tab.url)};
}
async function pageCall(tabId,operation,args=[]) {
  const tab=await tabInfo(tabId);if(tab.restricted)throw Error('Native LinkedIn/Indeed inspection and automation are disabled. Import the URL and supply job details manually.');
  try {
    await chrome.scripting.executeScript({target:{tabId},files:['content.js']});
    const results=await chrome.scripting.executeScript({target:{tabId},func:async(op,params)=>globalThis.ForgeApplyPage[op](...params),args:[operation,args]});
    if(!results[0]?.result)throw Error('Page inspection returned no state');return results[0].result;
  }catch(error){throw Error(error.message+' If access was revoked, invoke the toolbar or context menu on this tab again.');}
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
    case 'plan': {
      const current=await tabInfo(message.tabId);
      if(current.url!==message.snapshot.url||current.restricted)throw Error('Destination changed or is restricted; analyze again.');
      return api('/plan','POST',{url:current.url,snapshot_id:message.snapshot.snapshot_id,fields:message.snapshot.fields,site_authorized:message.site_authorized,use_ai:!!message.use_ai,page_text:message.use_ai?message.snapshot.page_text:''});
    }
    case 'fill': {
      if(!message.site_authorized)throw Error('Confirm site authorization before filling.');
      const tab=await tabInfo(message.tabId);if(tab.url!==message.plan.url||tab.restricted)throw Error('Page changed or restricted');
      return pageCall(message.tabId,'fill',[message.plan]);
    }
    case 'next':if(!message.site_authorized)throw Error('Confirm site authorization first.');return pageCall(message.tabId,'next',[message.token,message.snapshot_id]);
    case 'choose_file':if(!message.site_authorized)throw Error('Confirm site authorization first.');return pageCall(message.tabId,'chooseFile',[message.token,message.snapshot_id]);
    case 'save_job':return api('/jobs','POST',message.job);
    case 'match':return api('/match','POST',message.job);
    case 'manual_answer':return api('/answer','POST',{question:message.question});
    default:throw Error('Unknown extension request');
  }
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  handle(message,sender).then(data=>respond({ok:true,data}),error=>respond({ok:false,error:error.message}));return true;
});
