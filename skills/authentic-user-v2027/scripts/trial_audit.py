#!/usr/bin/env python3
"""Audit frozen prompts against immutable saved plan receipts; no network calls."""
import argparse
import hashlib
import json
from pathlib import Path

import authentic_user as au
import claim_protocol as typed
import attribution_protocol as field_typed
import atomic_protocol as atomic
import chatgpt_plan as cp
import validation_workflow as vw


def audit(run_dir):
    directory,run,calls,prompts=vw.load_run(run_dir);root=directory.parent
    config=run['model_config'];transport=config['transport']
    schema=atomic.schema() if transport.get('response_protocol')=='atomic-bound-v4' else field_typed.schema() if transport.get('response_protocol')=='field-bound-v3' else typed.schema() if transport.get('response_protocol')=='typed-source-v2' else cp.answer_schema()
    vw.require(vw.digest(schema)==transport['output_schema_sha256'],'Frozen schema changed')
    ids=set();inputs=outputs=valid=failures=0;finished=[];hashes={}
    for folder in ('attempts','provider-events','incoming','receipt-index'):
        vw.require({p.stem for p in (root/folder).glob('*.json')}==set(calls),'Incomplete/extra '+folder+' grid')
    for cid,call in calls.items():
        attempt=au.read_object(root/'attempts'/(cid+'.json'))
        vw.require(attempt['status'] in ('imported','structural_failure'),'Unfinished or failed transport attempt')
        saved=au.read_object(root/'provider-events'/(cid+'.json'));response=saved['response']
        envelope=au.read_object(root/'incoming'/(cid+'.json'));index=au.read_object(root/'receipt-index'/(cid+'.json'))
        vw.validate_response(run,calls,prompts,envelope,check_answer=False)
        vw.require(index['call_id']==attempt['call_id']==cid and index['run_sha256']==attempt['run_sha256']==run['run_sha256'],'Ledger binding mismatch')
        vw.require(response['status']=='completed' and response['model']==config['model'],'Provider completion/model mismatch')
        rid=response['id'];vw.require(rid not in ids,'Duplicate provider response ID');ids.add(rid)
        vw.require(rid==envelope['provider_request_id']==index['provider_response_id'],'Response identity mismatch')
        for name,field in (('provider-events','receipt_sha256'),('incoming','envelope_sha256')):
            value=hashlib.sha256((root/name/(cid+'.json')).read_bytes()).hexdigest()
            vw.require(value==index[field],'Raw evidence changed after first storage');hashes[cid+'/'+name]=value
        wire=json.loads(saved['text'])
        if transport.get('response_protocol') in ('typed-source-v2','field-bound-v3','atomic-bound-v4'):
            vw.require(envelope['answer'].get('wire_answer')==wire,'Raw wire answer changed')
        else:vw.require(envelope['answer']==wire,'Raw answer changed')
        prompt=vw.safe_path(Path(run['input_dir']),call['prompt']).read_text()
        body={'model':config['model'],'instructions':transport['adapter_instructions'],
              'input':[{'role':'user','content':[{'type':'input_text','text':prompt}]}],
              'reasoning':{'effort':'low'},'store':False,'stream':True,
              'text':{'format':{'type':'json_schema','name':'authentic_user_trial','strict':True,'schema':schema}}}
        vw.require(hashlib.sha256(json.dumps(body,ensure_ascii=False).encode()).hexdigest()==saved['request_body_sha256']==envelope['request_body_sha256'],'Transmitted prompt/schema differs from frozen inputs')
        for field in ('input_tokens','output_tokens'):
            vw.require(envelope['usage'][field]==response['usage'][field],'Returned usage mismatch')
        inputs+=response['usage']['input_tokens'];outputs+=response['usage']['output_tokens']
        vw.require(saved.get('paid_fallback_used') is False,'Unexpected billing path')
        try:vw.check_common_answer(prompts[call['prompt']]['payload'],envelope['answer'],transport.get('response_protocol'));passed=True
        except au.InputError:passed=False
        vw.require((attempt['status']=='imported')==passed,'First check disagrees with current contract; do not silently replace')
        if passed:valid+=1
        else:failures+=1
        vw.require('finished_unix' in attempt,'No attempt completion time')
        finished.append((attempt['started_unix'],attempt['finished_unix']))
    finished.sort()
    vw.require(all(start<=end for start,end in finished),'Invalid execution clock')
    vw.require(all(finished[i][1]<=finished[i+1][0] for i in range(len(finished)-1)),'Overlapping model calls detected')
    state=au.read_object(root/'live-status.json')
    expected={'provider_completed':len(calls),'valid_imports':valid,'structural_failures':failures,'transport_failures':0,'input_tokens':inputs,'output_tokens':outputs}
    vw.require(all(state.get(k)==v for k,v in expected.items()),'Live counters do not reconcile with receipts')
    return {'local_integrity_passed':True,'provider_verified_independently':False,'users':len({c['case'] for c in calls.values()}),
            'complete_grid':len(calls),'unique_response_ids':len(ids),'overlapping_calls':0,
            'source_value_protocol':transport.get('response_protocol','legacy-v1'),'wire_contract_pass':valid,'wire_contract_failures':failures,
            'input_tokens':inputs,'output_tokens':outputs,'paid_fallback_used':False,
            'run_sha256':run['run_sha256'],'receipt_index_sha256':vw.digest(hashes)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    try:
        result=audit(args.run_dir);au.write_new(args.output,json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result));return 0
    except (au.InputError,OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'local_integrity_passed':False,'error':str(exc) if isinstance(exc,au.InputError) else type(exc).__name__}));return 2
if __name__=='__main__':raise SystemExit(main())
