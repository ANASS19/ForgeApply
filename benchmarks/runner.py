"""Sequential real-inference runner; model outputs are scored, never executed."""
from __future__ import annotations
import base64
import hashlib
import json
import random
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from .assets import prepare_assets
from .environment import hardware,ResourceMonitor,command
from .schema import Case,SCHEMAS,SYSTEM
from .scoring import score


def read_cases(path:Path) -> tuple[dict,list[Case]]:
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('synthetic_only') is not True: raise ValueError('Only explicitly synthetic datasets are allowed')
    cases=[Case.model_validate(row) for row in data['cases']]
    if len({c.id for c in cases})!=len(cases): raise ValueError('Duplicate case IDs')
    return data,cases


def infer(client:httpx.Client,model:str,kind:str,inputs:dict,options:dict,*,image:Path|None=None,think=False) -> dict:
    user={'task':inputs,'response_schema':SCHEMAS[kind].model_json_schema()}
    message={'role':'user','content':json.dumps(user,ensure_ascii=False)}
    if image: message['images']=[base64.b64encode(image.read_bytes()).decode('ascii')]
    payload={'model':model,'stream':True,'think':think,'format':'json','keep_alive':'10m',
             'options':options,'messages':[{'role':'system','content':SYSTEM},message]}
    start=time.perf_counter(); first=None; pieces=[]; thinking=[]; metadata={}
    try:
        with client.stream('POST','/api/chat',json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if time.perf_counter()-start>(client.timeout.read or 180): raise TimeoutError('Total inference deadline exceeded')
                if not line: continue
                chunk=json.loads(line)
                if 'error' in chunk: raise RuntimeError(chunk['error'])
                content=chunk.get('message',{}).get('content','')
                if content and first is None: first=time.perf_counter()-start
                pieces.append(content)
                if chunk.get('message',{}).get('thinking'): thinking.append(chunk['message']['thinking'])
                if chunk.get('done'): metadata=chunk
        end=time.perf_counter()
        ns=lambda key:metadata.get(key)/1e9 if isinstance(metadata.get(key),(int,float)) else None
        generation=ns('eval_duration')
        return {'status':('truncated' if metadata.get('done_reason')=='length' else 'ok') if metadata.get('done') else 'incomplete','raw':''.join(pieces),
                'thinking':''.join(thinking),'metrics':{'latency_s':end-start,'ttft_s':first,
                'ollama_total_s':ns('total_duration'),'load_s':ns('load_duration'),
                'prompt_s':ns('prompt_eval_duration'),'generation_s':generation,
                'input_tokens':metadata.get('prompt_eval_count'),'output_tokens':metadata.get('eval_count'),
                'generation_tps':metadata.get('eval_count')/generation if generation else None,
                'done_reason':metadata.get('done_reason')},'_start':start,'_end':end}
    except (httpx.HTTPError,ValueError,RuntimeError,TimeoutError) as exc:
        end=time.perf_counter()
        return {'status':'error','raw':''.join(pieces),'error':type(exc).__name__+': '+str(exc)[:300],
                'metrics':{'latency_s':end-start,'ttft_s':first},'_start':start,'_end':end}


def unload(client:httpx.Client,models:list[str]):
    for model in models:
        response=client.post('/api/generate',json={'model':model,'keep_alive':0})
        response.raise_for_status()
    for _ in range(40):
        running=client.get('/api/ps').json().get('models',[])
        if not any(r['name'] in models for r in running): return
        time.sleep(.25)
    raise RuntimeError('Requested models did not unload; refusing a contaminated cold measurement')


def run(*,models:list[str],dataset:Path,output:Path,trials=3,context=8192,num_predict=768,timeout=180,
        base_url='http://127.0.0.1:11434',think=False,resume=False,only_categories=None):
    parsed=urlsplit(base_url)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password:
        raise ValueError('Benchmark endpoint must be a credential-free loopback Ollama HTTP URL')
    data,cases=read_cases(dataset)
    if only_categories: cases=[c for c in cases if c.category in only_categories]
    if not cases: raise ValueError('No selected benchmark cases')
    output.mkdir(parents=True,exist_ok=True)
    options={'temperature':0,'seed':42,'num_ctx':context,'num_predict':num_predict,
             'top_k':1,'top_p':1.,'repeat_penalty':1.,'presence_penalty':0.}
    protocol={'models':models,'trials':trials,'dataset_sha256':hashlib.sha256(dataset.read_bytes()).hexdigest(),
              'dataset_version':data['version'],'options':options,'think':think,'base_url':base_url,
              'categories':only_categories,'system_sha256':hashlib.sha256(SYSTEM.encode()).hexdigest(),
              'counterbalanced_model_order':True,'timeout_s':timeout,'json_mode':'json (schema in prompt, not grammar-enforced)',
              'response_cache':'Ollama default prefix caching; no custom response cache'}
    metadata_path=output/'environment.json'
    if metadata_path.exists():
        existing=json.loads(metadata_path.read_text(encoding='utf-8'))
        if not resume or existing['protocol']!=protocol: raise ValueError('Existing output needs --resume and an identical protocol')
    (output/'dataset.json').write_bytes(dataset.read_bytes())
    paths=output/'responses.jsonl'
    rows=[json.loads(line) for line in paths.read_text(encoding='utf-8').splitlines()] if paths.exists() else []
    complete={(r['model'],r['trial'],r['case_id'],r['phase']) for r in rows}
    assets=prepare_assets(cases,output)
    done=0;total=len(cases)*trials*len(models)
    with httpx.Client(base_url=base_url.rstrip('/'),timeout=httpx.Timeout(timeout,connect=10)) as client:
        version=client.get('/api/version'); version.raise_for_status()
        installed=client.get('/api/tags').json()['models']
        if metadata_path.exists():
            recorded={m['name']:m['digest'] for m in existing['installed_model_metadata']}
            current={m['name']:m['digest'] for m in installed}
            if any(current.get(name)!=digest for name,digest in recorded.items()): raise ValueError('Model digest changed; start a new benchmark output')
        for model in models:
            if not any(m['name']==model for m in installed): raise ValueError('Requested model is not installed: '+model)
        details={model:client.post('/api/show',json={'model':model}).json() for model in models}
        env=existing if metadata_path.exists() else {'protocol':protocol,'hardware':hardware(),
              'ollama_version':version.json(),'models':{m:{k:details[m].get(k) for k in ('details','capabilities','parameters','model_info')} for m in models},
              'installed_model_metadata':[{k:m.get(k) for k in ('name','digest','size')} for m in installed if m['name'] in models]}
        metadata_path.write_text(json.dumps(env,indent=2),encoding='utf-8')
        unrelated=[m['name'] for m in client.get('/api/ps').json().get('models',[]) if m['name'] not in models]
        if unrelated: raise RuntimeError('Other loaded models could contend for memory; stop them explicitly before benchmarking')
        with ResourceMonitor() as monitor, paths.open('a',encoding='utf-8',buffering=1) as stream:
            def append(row):
                rows.append(row)
                stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
            def measured(model,case,inputs,image=None):
                result=infer(client,model,case.kind,inputs,options,image=image,think=think)
                start,end=result.pop('_start'),result.pop('_end')
                result['resources']=monitor.during(start,end)
                result['residency']=client.get('/api/ps').json().get('models',[])
                return result
            try:
                for trial in range(trials):
                    order=models if trial%2==0 else list(reversed(models))
                    selected=list(cases);random.Random(42+trial).shuffle(selected)
                    for model in order:
                        if all((model,trial,c.id,'warm') in complete for c in selected): continue
                        unload(client,models)
                        cold_case=next(c for c in cases if c.kind!='vision' and not c.steps)
                        cold=measured(model,cold_case,cold_case.input)
                        cold.update(model=model,trial=trial,case_id='cold_load',category='cold',phase='cold')
                        append(cold)
                        # Explicit priming is excluded from quality/latency summaries.
                        prime=measured(model,cold_case,cold_case.input)
                        prime.update(model=model,trial=trial,case_id='warmup',category='warmup',phase='warmup')
                        append(prime)
                        if assets and 'vision' in details[model].get('capabilities',[]):
                            visual=next(c for c in cases if c.kind=='vision')
                            vision_prime=measured(model,visual,visual.input,Path(assets[visual.id]['image']))
                            vision_prime.update(model=model,trial=trial,case_id='vision_warmup',category='warmup',phase='vision_warmup')
                            append(vision_prime)
                        print(json.dumps({'phase':'model_loaded','model':model,'trial':trial,'ollama_ps':command(['ollama','ps'])}),flush=True)
                        for case in selected:
                            if (model,trial,case.id,'warm') in complete: done+=1;continue
                            row={'model':model,'trial':trial,'case_id':case.id,'category':case.category,'phase':'warm'}
                            if case.kind=='vision' and 'vision' not in details[model].get('capabilities',[]):
                                row.update(status='unsupported',task_correct=False,unsafe=False)
                            elif case.steps:
                                steps=[]
                                for step_index,step in enumerate(case.steps):
                                    response=measured(model,case,{'workflow':case.input,'step':step_index,'observation':step['input']})
                                    evaluated=score(case.kind,response['raw'],step['expected'],forbidden_targets=case.forbidden_targets,forbidden_values=case.forbidden_values)
                                    response.update(evaluated);steps.append(response)
                                    if response['status']!='ok' or not evaluated['task_correct']: break
                                row.update(status='ok' if all(s['status']=='ok' for s in steps) else 'error',
                                    task_correct=len(steps)==len(case.steps) and all(s['task_correct'] for s in steps),
                                    unsafe=any(s['unsafe'] for s in steps),hallucination=any(s['hallucination'] for s in steps),
                                    json_valid=all(s['json_valid'] for s in steps),schema_valid=all(s['schema_valid'] for s in steps),steps=steps,
                                    metrics={'latency_s':sum(s['metrics']['latency_s'] for s in steps)},
                                    resources={k:max(s['resources'].get(k,0) for s in steps) for k in set().union(*(s['resources'] for s in steps))})
                            else:
                                picture=Path(assets[case.id]['image']) if case.kind=='vision' else None
                                result=measured(model,case,case.input,picture)
                                gold=dict(case.expected)
                                if picture: gold['visible_text']=assets[case.id]['visible_text']
                                evaluation=score(case.kind,result['raw'],gold,critical_fields=case.critical_fields,
                                                 forbidden_targets=case.forbidden_targets,forbidden_values=case.forbidden_values)
                                row.update(result);row.update(evaluation)
                            append(row);done+=1
                            print(json.dumps({'done':done,'total':total,'model':model,'trial':trial,'case':case.id,
                                  'correct':row.get('task_correct'),'unsafe':row.get('unsafe'),'seconds':round(row.get('metrics',{}).get('latency_s',0),2)}),flush=True)
            finally:
                unload(client,models)
                (output/'resource_samples.json').write_text(json.dumps(monitor.samples),encoding='utf-8')
    return rows
