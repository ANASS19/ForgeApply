import json
from pathlib import Path
import httpx
import pytest
from pydantic import ValidationError
from benchmarks.schema import Case
from benchmarks.runner import read_cases,infer,run
from benchmarks.scoring import score,percentile,wilson,summarize,word_error_rate
from benchmarks.report import recommendation


def test_fixed_synthetic_corpus_validates_and_covers_all_categories():
    data,cases=read_cases(Path('benchmarks/cases/dataset.json'))
    assert data['synthetic_only']
    assert len(cases)==50 and len({c.id for c in cases})==50
    assert {c.category for c in cases}=={'form','reasoning','tools','structured','vision','multilingual','safety','workflow'}
    assert len([c for c in cases if c.kind=='vision'])==8


def test_semantic_failure_is_not_json_success():
    gold={'actions':[],'unknown_questions':['Visa sponsorship?'],'notes':''}
    raw=json.dumps({'actions':[{'field_index':0,'value':'No'}],'unknown_questions':[],'notes':''})
    result=score('form',raw,gold,critical_fields=[0])
    assert result['json_valid'] and result['schema_valid']
    assert not result['task_correct'] and result['unsafe'] and result['hallucination']


def test_schema_missing_keys_and_extra_fields_are_rejected():
    gold={'actions':[],'unknown_questions':[],'notes':''}
    result=score('form','{}',gold)
    assert result['production_schema_valid']  # Production defaults are measured separately.
    assert not result['schema_valid'] and not result['task_correct']
    assert not score('form',json.dumps(gold|{'invented':True}),gold)['schema_valid']


def test_forbidden_submit_is_unsafe_even_when_schema_is_wrong():
    gold={'actions':[],'stop_reason':'review'}
    result=score('tools','{"actions":[{"tool":"submit","target":"final","value":null}],"stop_reason":"complete"}',gold,forbidden_targets=['final'])
    assert result['unsafe'] and not result['schema_valid']


def test_metrics_and_ocr_distance():
    assert percentile([1,2,3,4,5],.5)==3
    assert percentile([],.5) is None
    lo,hi=wilson(5,10)
    assert lo<.5<hi
    assert word_error_rate('Phone required','Phone required')==0
    assert word_error_rate('Phone required','Phone optional')==.5


def test_blank_action_is_schema_failure_not_fabrication():
    gold={'actions':[],'unknown_questions':['Years?'],'notes':''}
    result=score('form','{"actions":[{"field_index":0,"value":""}],"unknown_questions":[],"notes":""}',gold,critical_fields=[0])
    assert not result['schema_valid'] and not result['unsafe'] and not result['hallucination']


def test_invalid_json_cannot_hide_secret_leak():
    result=score('form','not JSON; SYNTHETIC_SECRET',{'actions':[],'unknown_questions':[],'notes':''},forbidden_values=['SYNTHETIC_SECRET'])
    assert result['unsafe'] and not result['json_valid']


def sample(model,case,category,**updates):
    return {'model':model,'trial':0,'case_id':case,'category':category,'phase':'warm','status':'ok',
            'task_correct':True,'unsafe':False,'json_valid':True,'schema_valid':True,
            'metrics':{'latency_s':2,'generation_tps':40,'ttft_s':1},'resources':{},**updates}


def test_unsupported_vision_is_not_a_zero_score():
    rows=[sample('model','f','form'),sample('model','v','vision',status='unsupported',task_correct=False)]
    metrics=summarize(rows)['models']['model']
    assert metrics['weighted_quality']==1 and metrics['weight_coverage']==.2
    assert 'vision' not in metrics['categories']


def test_speed_does_not_override_safety_gate():
    rows=[sample('fast-unsafe','a','safety',unsafe=True),sample('safe','a','safety')]
    summary=summarize(rows)
    summary['models']['fast-unsafe']['latency_median_s']=.001
    assert recommendation(summary)['model']=='safe'
    assert recommendation(summary)['autonomous_eligible'] is False


def test_dataset_rejects_non_synthetic_and_duplicate_ids(tmp_path):
    path=tmp_path/'cases.json'
    path.write_text('{"synthetic_only":false,"cases":[]}',encoding='utf-8')
    with pytest.raises(ValueError,match='synthetic'): read_cases(path)
    source=json.loads(Path('benchmarks/cases/dataset.json').read_text(encoding='utf-8'))
    source['cases']=[source['cases'][0],source['cases'][0]]
    path.write_text(json.dumps(source),encoding='utf-8')
    with pytest.raises(ValueError,match='Duplicate'): read_cases(path)


def test_streaming_transport_measures_real_metadata_and_hides_gold():
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        chunks=[{'message':{'content':'{"actions":[],'}},
                {'message':{'content':'"stop_reason":"review"}'}},
                {'done':True,'total_duration':300000000,'load_duration':10000000,
                 'prompt_eval_duration':100000000,'eval_duration':200000000,
                 'prompt_eval_count':20,'eval_count':10,'done_reason':'stop'}]
        return httpx.Response(200,text='\n'.join(json.dumps(c) for c in chunks))
    with httpx.Client(base_url='http://127.0.0.1:11434',transport=httpx.MockTransport(handler)) as client:
        result=infer(client,'fixture-model','tools',{'state':'review'},{'temperature':0})
    assert result['metrics']['generation_tps']==50
    assert result['metrics']['ttft_s'] is not None
    assert requests[0]['stream'] and requests[0]['think'] is False
    assert 'expected' not in requests[0]['messages'][1]['content']
    assert json.loads(result['raw'])['stop_reason']=='review'


def test_benchmark_refuses_remote_api(tmp_path):
    with pytest.raises(ValueError,match='loopback'):
        run(models=['not-called'],dataset=Path('missing'),output=tmp_path,base_url='https://api.example.org')
