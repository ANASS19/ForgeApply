// SPDX-FileCopyrightText: 2026 Anass Nassiri and contributors
// SPDX-License-Identifier: Apache-2.0
// Short-horizon executor. Values come only from validated plans; models choose offered tool IDs.
(() => {
  const runtime=globalThis.ForgeApplyAgent={running:false,control:'',run:null};
  const statuses=['running','paused','stopped','interrupted','human_review','failed','review_ready'];
  const tools=['inspect','fill','add_record','advance_step','request_input','final_review','pause','stop'];
  const outcomes=['started','verified','human_review','failed','paused','stopped'];
  const count=(value,max)=>Number.isInteger(value)&&value>=0?Math.min(value,max):0;
  // Project checkpoints onto the wire schema. Old/local extra metadata never reaches strict API models.
  function canonicalRun(value={}){value=value&&typeof value==='object'?value:{};return {
    id:/^[a-f0-9-]{36}$/.test(value.id||'')?value.id:crypto.randomUUID(),tab_id:count(value.tab_id,2147483647),
    url:typeof value.url==='string'?value.url.slice(0,2000):'',stage:typeof value.stage==='string'?value.stage.slice(0,500):'',
    status:statuses.includes(value.status)?value.status:'interrupted',steps:count(value.steps,80),verified:count(value.verified,500),
    model_calls:count(value.model_calls,5),elapsed_ms:count(value.elapsed_ms,3600000),
    events:(Array.isArray(value.events)?value.events:[]).filter(e=>e&&tools.includes(e.tool)&&outcomes.includes(e.outcome)).slice(-100)
      .map(e=>({tool:e.tool,label:String(e.label||'').slice(0,500),outcome:e.outcome}))};}
  const safeURL=url=>{const u=new URL(url);return u.origin+u.pathname;};
  async function pageKey(url){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(url));return [...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('');}
  function show(){
    const run=runtime.run;$('agentControls').hidden=!runtime.running;
    if(runtime.running&&snapshot)$('summary').textContent=snapshot.final_review?'Final review reached. Nothing was submitted.':`${snapshot.fields.length} controls on this page; ${plan?.drafts?.length||0} answers to review.`;
    if(run){$('agentGoal').textContent=`${run.stage||'Application'} · ${run.status.replaceAll('_',' ')} · ${run.verified} verified actions · ${run.steps} actions attempted — ${run.events.at(-1)?.label||''}`;
      $('agentLog').replaceChildren(...run.events.slice(-20).map(e=>{const item=document.createElement('li');item.textContent=e.tool+' → '+e.label+' ('+e.outcome+')';return item;}));}
    $('runAgent').textContent=run&&['paused','interrupted','human_review','failed'].includes(run.status)?'Resume application':'Complete Application';actions();
  }
  async function checkpoint(status,tool,label,outcome){
    const run=runtime.run=canonicalRun(runtime.run);run.status=status;
    if(tool)run.events.push({tool,label:String(label||'').slice(0,500),outcome});run.events=run.events.slice(-100);
    run.elapsed_ms=Math.min(3600000,Date.now()-runtime.started);
    const saved={run:{...run,url:safeURL(tab.url)},page_key:await pageKey(tab.url)};
    await chrome.storage.local.set({agentCheckpoint:saved});
    try{await send('agent_progress',{run:{...run,url:tab.url}});}
    catch(error){throw Object.assign(Error('Progress could not be saved: '+error.message),{code:error.code,operation:'save_progress'});}
    // Do not advertise a completed/review state before its durable backend receipt.
    show();
  }
  $('agentPause').onclick=()=>{runtime.control='pause';$('agentGoal').textContent='Pausing after the current verified action...';};
  $('agentStop').onclick=()=>{runtime.control='stop';$('agentGoal').textContent='Stopping after the current action. Your entries stay on the page.';};
  button('showScreenshot',async()=>{const result=await send('screenshot',{tabId});$('agentScreenshot').src=result.url;$('agentScreenshot').hidden=false;});
  button('runAgent',async()=>{
    const target=tabId,origin=new URL(tab.url).origin,key=await pageKey(tab.url);
    const saved=(await chrome.storage.local.get('agentCheckpoint')).agentCheckpoint;
    const previous=canonicalRun(saved?.run);
    const reusable=saved?.page_key===key&&['paused','interrupted','human_review','failed','running'].includes(previous.status)&&previous.steps<80;
    runtime.run=reusable?{...previous,tab_id:target}:canonicalRun({tab_id:target,url:safeURL(tab.url),status:'running'});
    runtime.control='';runtime.running=true;runtime.started=Date.now()-runtime.run.elapsed_ms;show();
    const plannedPages=new Set(),retries=new Map(),acknowledgedStages=new Set(),deferred=new Set(),issues=[];
    if(reusable&&previous.status==='human_review')acknowledgedStages.add(previous.stage);
    try{
      await checkpoint('running','inspect','Observe the authorized application page','started');
      while(runtime.run.steps<80&&Date.now()-runtime.started<180000){
        if(runtime.control||pendingTab!==null){const stop=runtime.control==='stop';await checkpoint(stop?'stopped':'paused',stop?'stop':'pause','User control',stop?'stopped':'paused');return;}
        if(tabId!==target||new URL(tab.url).origin!==origin)throw Error('The authorized page changed. Inspect and start again on that page.');
        runtime.operation='inspect';captureEdits();adopt(await send('inspect',{tabId:target}),true);runtime.run.stage=snapshot.stage||'';
        if(new URL(snapshot.url).origin!==origin)throw Error('The destination origin changed. Authorize and review the new page before continuing.');
        if(snapshot.final_review){await checkpoint('review_ready','final_review','Final review reached. Submit manually only if you choose.','human_review');return;}
        if(snapshot.needs_login||snapshot.site_error||snapshot.truncated_controls){await checkpoint('human_review','request_input',snapshot.needs_login?'Sign in manually':snapshot.site_error?'The website reports a page/server error':'Page inspection limit reached','human_review');return;}
        const pageStage=JSON.stringify([snapshot.url,snapshot.stage,snapshot.fields.map(f=>[f.label,f.name,f.type,f.section,f.record_index])]);
        let useAI=false;
        runtime.operation='prepare';await prepare(false);
        // Fill verified facts before model latency. SPA steps share a URL, so the
        // unfamiliar-question fallback is tracked per form structure and stage.
        if(!plan.actions.length&&!plan.structure_actions.length&&!plannedPages.has(pageStage)){
          plannedPages.add(pageStage);
          useAI=$('aiMode').checked&&runtime.run.model_calls<3;
          if(useAI){await prepare(true);if(plan.model_called)runtime.run.model_calls++;}
        }
        let candidates=[],actionIndices=[];
        if(plan.structure_actions.length)candidates=[{id:0,tool:'add_record',label:'Add one verified '+plan.structure_actions[0].section+' record'}];
        else candidates=plan.actions.map((a,id)=>{const field=snapshot.fields.find(f=>f.token===a.token);return {id,tool:'fill',label:[field?.section?field.section+' '+(field.record_index+1):'',field?.label].filter(Boolean).join(' → ')};}).filter(c=>!deferred.has(snapshot.url+'|'+c.label)).slice(0,5).map((c,id)=>{actionIndices[id]=c.id;return {...c,id};});
        if(!candidates.length){
          const missing=snapshot.fields.some(f=>f.required&&(!f.valid||(f.type==='checkbox'?!f.checked:f.type==='radio'?!f.group_answered:!f.value)));
          const review=plan.drafts.some(d=>!d.optional||!!d.value)||plan.manual.some(t=>!t.optional&&(!t.answered||!acknowledgedStages.has(runtime.run.stage)));
          if(missing||review||deferred.size){await checkpoint('human_review','request_input',deferred.size?deferred.size+' controls need selection or validation review. Other supported fields were attempted; Resume after correction.':'Review missing answers, personal declarations or document selection, then Resume.','human_review');return;}
          if(snapshot.navigation.length!==1){await checkpoint('human_review','request_input','Choose the next page or final review manually.','human_review');return;}
          candidates=[{id:0,tool:'advance_step',label:snapshot.navigation[0].name}];
        }
        runtime.operation='choose_action';const decision=await send('agent_decision',{tabId:target,url:snapshot.url,stage:snapshot.stage,candidates,
          use_ai:$('aiMode').checked&&(useAI||$('visionMode').checked)&&candidates.length>1&&runtime.run.model_calls<3,use_vision:$('visionMode').checked});
        if(decision.source==='model')runtime.run.model_calls++;
        const chosen=candidates.find(c=>c.id===decision.candidate_id);if(!chosen)throw Error('Planner selected an unavailable tool.');
        await checkpoint('running',chosen.tool,chosen.label,'started');runtime.run.steps++;
        if(runtime.control||pendingTab!==null){const stop=runtime.control==='stop';await checkpoint(stop?'stopped':'paused',stop?'stop':'pause','User control before the next browser action',stop?'stopped':'paused');return;}
        runtime.operation=chosen.tool;
        if(chosen.tool==='advance_step'){
          const result=await send('next',{tabId:target,token:snapshot.navigation[0].token,snapshot_id:snapshot.snapshot_id,site_authorized:true});
          edits.clear();adopt(result.snapshot,true);
          if(!result.transition_verified){await checkpoint('human_review','advance_step','Page validation or server response needs review.','failed');return;}
        }else{
          const actionPlan={...plan,structure_actions:chosen.tool==='add_record'?[{...plan.structure_actions[0],count:1}]:[],actions:chosen.tool==='fill'?[plan.actions[actionIndices[chosen.id]]]:[]};
          const result=await send('fill',{tabId:target,plan:actionPlan,site_authorized:true});adopt(result.snapshot);
          if(result.errors.length){
            const changed=result.errors.every(e=>e.code==='CONTROL_CHANGED'||/^Control changed/.test(e.error));
            if(changed&&!retries.has(chosen.label)){retries.set(chosen.label,1);await checkpoint('running',chosen.tool,chosen.label+' — re-observing replaced control','failed');continue;}
            issues.push(...result.errors.map(e=>`${e.label||chosen.label}: ${e.error}`));$('error').textContent=issues.slice(-8).join('\n');await prepare(false);
            if(chosen.tool==='fill'){
              deferred.add(snapshot.url+'|'+chosen.label);
              await checkpoint('running',chosen.tool,chosen.label+' — needs review; continuing independent fields','failed');continue;
            }
            await checkpoint('human_review',chosen.tool,chosen.label,'failed');return;
          }
          runtime.run.verified+=result.filled.length+(result.structure_changed?1:0);
          if(!result.filled.length&&!result.structure_changed){await checkpoint('human_review',chosen.tool,'No state change was verified; inspect this control.','failed');return;}
        }
        await checkpoint('running',chosen.tool,chosen.label,'verified');
      }
      await checkpoint('stopped','stop','Execution limit reached. Review the page before starting another run.','stopped');
    }catch(error){
      $('error').textContent=error.message;
      const cause=(error.operation||runtime.operation||'initialize')+' failed ('+(error.code||'execution_error')+'). '+(runtime.run.steps?'Your entries were preserved.':'No browser action started.');
      try{await checkpoint('failed','request_input',cause,'failed');}catch(saveError){$('error').textContent=error.message+' '+saveError.message;}
    }finally{runtime.running=false;show();}
  });
  (async()=>{const saved=(await chrome.storage.local.get('agentCheckpoint')).agentCheckpoint;if(saved){runtime.run=canonicalRun(saved.run);if(runtime.run.status==='running')runtime.run.status='interrupted';show();}})();
})();
