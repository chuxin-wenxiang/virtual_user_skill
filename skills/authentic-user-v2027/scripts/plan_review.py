#!/usr/bin/env python3
"""Optional plan-only, source-blind semantic audit; immutable raw candidates stay intact."""
import argparse,hashlib,json,os,time
from pathlib import Path
import authentic_user as au
import attribution_review as ar
import attribution_protocol as ap
import chatgpt_plan as cp
import validation_workflow as vw
import trial_audit
import atomic_protocol
import atomic_review
import clause_review

def review_protocol(run):
    transport=run['model_config']['transport']
    name=transport.get('source_review_protocol')
    vw.require(name in (None,clause_review.NAME),'Unsupported source review protocol')
    if name:
        vw.require(transport.get('response_protocol')=='atomic-bound-v4','Clause review requires atomic answers')
    return name or transport.get('response_protocol')

def review_model(run):
    model=run['model_config']['transport'].get('source_review_model',run['model_config']['model'])
    vw.require(isinstance(model,str) and bool(model.strip()) and model.strip().lower() not in ('auto','latest','default'),'Explicit source review model is required')
    return model

def review_timeout(run):
    value=run['model_config']['transport'].get('source_review_timeout_seconds',90)
    vw.require(type(value) is int and 30<=value<=300,'Invalid source review time guard')
    return value

def protocols(run):
    if run["model_config"]["transport"].get("response_protocol") == "atomic-bound-v4":
        return atomic_protocol, clause_review if review_protocol(run)==clause_review.NAME else atomic_review
    return ap, ar

def batch_schema(protocol="field-bound-v3"):
    item=(clause_review if protocol==clause_review.NAME else atomic_review if protocol == "atomic-bound-v4" else ar).schema();item['properties']['review_id']={'type':'string'};item['required'].append('review_id')
    return {'type':'object','properties':{'reviews':{'type':'array','minItems':1,'maxItems':4,'items':item}},'required':['reviews'],'additionalProperties':False}

def outbound_tasks(batch, protocol):
    if protocol not in ('atomic-bound-v4',clause_review.NAME): return batch
    return [{k:v for k,v in task.items() if k not in ('evidence','selected_fields','precheck','original_wire_sha256')} for task in batch]


def derive(evidence, wire, review, run):
    ap, ar = protocols(run)
    if ap is atomic_protocol:
        errors = []
        final = ar.apply(evidence, wire, review, contract_errors=errors)
        return {'answer': ap.render(evidence, final), 'review_contract_errors': errors}
    return {'answer': ap.render(evidence, ar.apply(evidence, wire, review))}


def phase_sources(run,phase_config=None):
    expected=run['model_config']['transport']['execution_sources_sha256']
    if phase_config is not None:
        cfg=au.read_object(phase_config)
        vw.require(cfg.get('run_sha256')==run['run_sha256'] and cfg.get('reason') and cfg.get('hidden_answers_seen') is False,'Explicit pre-outcome review amendment required')
        actual=cfg.get('sources_sha256',{})
        vw.require(set(actual)==set(expected),'Phase source file set differs')
        vw.require(all(actual[n]==v for n,v in expected.items() if n!='plan_review.py'),'Only the review adapter may change in a separate phase')
        expected=actual
    for name,value in expected.items():
        vw.require(hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()==value,'Source changed outside phase freeze')
    return expected

def precheck(evidence, wire):
    """Withdraw invalid atoms, never rewrite text or hide the original strict failure."""
    import copy
    p = atomic_protocol
    p.require(isinstance(wire, dict) and set(wire) == set(p.schema()['required']), 'Atomic global fields differ')
    p.require(isinstance(wire['facts'], list) and len(wire['facts']) <= 4 and isinstance(wire['atoms'], list) and len(wire['atoms']) <= 6, 'Atomic arrays differ')
    p.require(wire['direction'] in p.p.DIRECTIONS, 'Invalid global direction')
    base = copy.deepcopy(wire)
    base.update(facts=[], atoms=[], direction='unknown', direction_atom=None)
    if not base['unknowns']: base['unknowns'] = ['review_withdrawal']
    p.validate(evidence, base)
    facts = []; atoms = []; kept = []
    log = {'kept_atom_indices': kept, 'fact_errors': [], 'atom_errors': [], 'direction_errors': []}
    try:
        p.validate(evidence, wire); log['original_strict_contract_pass'] = True
    except p.ProtocolError as exc:
        log.update(original_strict_contract_pass=False, original_strict_error=str(exc))
    for i, fact in enumerate(wire['facts']):
        try:
            p.require(fact not in facts, 'Duplicate fact selector')
            p.validate(evidence, base | {'facts': [fact]})
            facts.append(fact)
        except p.ProtocolError as exc: log['fact_errors'].append({'fact_index':i, 'error':str(exc)})
    for i, atom in enumerate(wire['atoms']):
        try:
            p.validate(evidence, base | {'atoms': [atom]})
            atoms.append(atom); kept.append(i)
        except p.ProtocolError as exc: log['atom_errors'].append({'atom_index':i, 'error':str(exc)})
    out = copy.deepcopy(wire); out.update(facts=facts, atoms=atoms, direction='unknown', direction_atom=None)
    index = wire['direction_atom']
    if wire['direction'] != 'unknown':
        try:
            p.require(type(index) is int and index in kept, 'Direction depends on an absent or rejected atom')
            out.update(direction=wire['direction'], direction_atom=kept.index(index))
            p.validate(evidence, out)
        except p.ProtocolError as exc:
            log['direction_errors'].append(str(exc)); out.update(direction='unknown', direction_atom=None)
    elif index is not None: log['direction_errors'].append('Unknown direction has an unused binding')
    if any(log[k] for k in ('fact_errors','atom_errors','direction_errors')):
        out['unknowns'] = [x for x in out['unknowns'] if x != 'review_withdrawal'][:5] + ['review_withdrawal']
    p.validate(evidence, out)
    return out, log


def precheck_bundle(bundle, answer):
    au.validate_bundle(bundle)
    vw.require(answer.get('bundle_sha256') == bundle['bundle_sha256'], 'Precheck answer belongs to another bundle')
    wire = answer.get('wire_answer')
    filtered, log = precheck(bundle['evidence'], wire)
    rendered = au.render_bound_answer(bundle, {'bundle_sha256':bundle['bundle_sha256'], 'answer_mode':answer.get('answer_mode'), 'wire_answer':filtered})
    return rendered, {'origin':'deterministic_precheck_withdrawal', 'bundle_sha256':bundle['bundle_sha256'], 'original_wire_sha256':ar.digest(wire), 'filtered_wire_sha256':ar.digest(filtered), 'precheck':log}


def candidates(root,calls,prompts,run):
    ap, ar = protocols(run)
    records=[];by_review={};rejected={}
    order=sorted(calls,key=lambda c:vw.digest(['source-review-v1',run['run_sha256'],c]))
    for cid in order:
        envelope=au.read_object(root/'incoming'/(cid+'.json'));wire=envelope['answer']['wire_answer'];payload=prompts[calls[cid]['prompt']]['payload']
        try:
            if ap is atomic_protocol:
                candidate, log = precheck(payload['user_context']['evidence'], wire)
                task=ar.task(payload['user_context']['evidence'],candidate)
                task.update(original_wire_sha256=ar.digest(wire), precheck=log)
            else:task=ar.task(payload['user_context']['evidence'],wire)
        except ap.ProtocolError as e:
            rejected[cid]={'call_id':cid,'origin':'structural_rejection','candidate_sha256':ar.digest(wire),'reason':str(e)}
            continue
        rid=f'A{len(records)+1:04d}';item={'review_id':rid,'question':payload['question'],**task}
        records.append(item);by_review[rid]={'call_id':cid,'task':item}
    return records,by_review,rejected

def execute(run_dir,credential_dir,consent_file,phase_config=None):
    directory,run,calls,prompts=vw.load_run(run_dir);root=directory.parent
    ap, ar = protocols(run); protocol = review_protocol(run)
    trial_audit.audit(directory)
    sources=phase_sources(run,phase_config)
    consent=au.read_object(consent_file)
    vw.require(consent.get('approved') is True and consent.get('source_review_approved') is True and consent.get('run_sha256')==run['run_sha256'] and consent.get('destination')==cp.API+'/responses' and consent.get('subscription_only') is True and bool(consent.get('human_authorization')),'Run-bound source audit authorization required')
    vw.require(run['model_config']['transport'].get('response_protocol') in ('field-bound-v3','atomic-bound-v4'),'Source audit requires a supported source-bound protocol')
    dest=root/'source-review';dest.mkdir(mode=0o700,exist_ok=True);lock=dest/'.lock'
    try:fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:raise cp.PlanStop('Source reviewer already running or stale lock needs review') from None
    try:
        os.close(fd)
        vw.require(not (dest/'plan.json').exists(),'Existing source audit must be inspected; no automatic replay')
        records,by_review,rejected=candidates(root,calls,prompts,run)
        for cid,row in rejected.items():vw.save(dest/(cid+'.rejected.json'),row)
        batches=[records[i:i+4] for i in range(0,len(records),4)]
        plan={'run_sha256':run['run_sha256'],'total_candidates':len(calls),'structural_rejections':rejected,'phase_sources_sha256':sources,'phase_amendment':au.read_object(phase_config) if phase_config else None,'candidate_count':len(records),'batches':len(batches),'batch_size':4,'automatic_retries':0,'schema':batch_schema(protocol),'instructions':ar.INSTRUCTIONS,'model':review_model(run),'tasks':records,'judge_access':False}
        vw.save(dest/'plan.json',plan);vw.save(dest/'private-key.json',by_review)
        client=cp.PlanClient(credential_dir);state={'status':'running','planned_batches':len(batches),'structural_rejections':len(rejected),'completed_batches':0,'reviewed_answers':0,'global_review_rejections':0,'review_pending_atoms':0,'input_tokens':0,'output_tokens':0,'paid_fallback_used':False};intervals=[];response_ids=set()
        for i,batch in enumerate(batches,1):
            for name,expected in sources.items():
                vw.require(hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()==expected,'Source changed during source-only audit')
            bid=f'B{i:03d}';prompt=json.dumps({'tasks':outbound_tasks(batch,protocol)},ensure_ascii=False);started=time.time();vw.save(dest/(bid+'.attempt.json'),{'status':'started','started_unix':started,'run_sha256':run['run_sha256']})
            try:result=client.respond(plan['model'],prompt,ar.INSTRUCTIONS,schema=batch_schema(protocol),max_input_chars=40000,max_output_chars=20000,timeout=review_timeout(run))
            except Exception as e:
                state.update(status='stopped_transport',reason=str(e) if isinstance(e,au.InputError) else type(e).__name__);cp.atomic_private(dest/'status.json',state);print(json.dumps(state),flush=True);return state
            vw.save(dest/(bid+'.receipt.json'),result)
            # Anchor the first stored response before any candidate parsing can fail.
            usage=result['response']['usage'];vw.require(result['response']['status']=='completed' and result['response']['model']==plan['model'] and result['paid_fallback_used'] is False,'Unexpected completion or billing')
            rid=result['response']['id'];vw.require(rid not in response_ids,'Duplicate review response');response_ids.add(rid)
            finished=time.time();intervals.append((started,finished));state['completed_batches']+=1
            for k in ('input_tokens','output_tokens'):state[k]+=usage[k]
            vw.save(dest/(bid+'.index.json'),{'receipt_sha256':hashlib.sha256((dest/(bid+'.receipt.json')).read_bytes()).hexdigest(),'started_unix':started,'finished_unix':finished,'response_id':rid,'request_body_sha256':result['request_body_sha256']})
            expected={t['review_id']:t for t in batch};seen=set()
            try:
                out=json.loads(result['text']);vw.require(isinstance(out,dict) and set(out)=={'reviews'} and isinstance(out['reviews'],list),'Invalid review envelope')
                ids=[row.get('review_id') if isinstance(row,dict) else None for row in out['reviews']]
                vw.require(len(ids)==len(batch) and all(isinstance(r,str) for r in ids) and len(set(ids))==len(ids) and set(ids)==set(expected),'Unknown, duplicate or missing review ID')
            except (ValueError,au.InputError) as exc:
                state.update(status='stopped_review_contract',reason=str(exc) if isinstance(exc,au.InputError) else 'Invalid review JSON')
                cp.atomic_private(dest/'status.json',state);return state
            for row in out['reviews']:
                rid=row.get('review_id');vw.require(rid in expected and rid not in seen,'Unknown or duplicate review ID');seen.add(rid)
                assessment={k:v for k,v in row.items() if k!='review_id'};task=expected[rid]
                try:derived=derive(task['evidence'],task['candidate'],assessment,run)
                except ap.ProtocolError as exc:
                    cid=by_review[rid]['call_id']
                    vw.save(dest/(cid+'.review-rejected.json'),{'call_id':cid,'review_id':rid,'origin':'global_assessment_contract_rejection','candidate_sha256':task['wire_sha256'],'raw_assessment_sha256':ar.digest(assessment),'error':str(exc),'batch':bid})
                    state['global_review_rejections']+=1
                    continue
                if ap is atomic_protocol: derived.update(original_wire_sha256=task['original_wire_sha256'], precheck=task['precheck'])
                if protocol==clause_review.NAME:state['review_pending_atoms']+=len(derived['review_contract_errors'])
                cid=by_review[rid]['call_id']
                vw.save(dest/(cid+'.assessment.json'),assessment)
                vw.save(dest/(cid+'.final.json'),{'call_id':cid,'origin':'derived_source_review','review_origin':'separate_plan_model_context','candidate_sha256':task['wire_sha256'],'assessment_sha256':ar.digest(assessment),**derived})
            vw.require(set(expected)==seen,'Missing review in batch')
            state['reviewed_answers']+=len(batch)
            if usage['input_tokens']>16000 or usage['output_tokens']>6000:state.update(status='stopped_usage_guard');cp.atomic_private(dest/'status.json',state);return state
            cp.atomic_private(dest/'status.json',state)
            if i%4==0:print(json.dumps(state),flush=True)
        state.update(status='completed_with_review_rejections' if state['global_review_rejections'] else 'completed_with_pending_reviews' if state['review_pending_atoms'] else 'completed',unique_response_ids=len(response_ids),overlapping_calls=sum(intervals[i][1]>intervals[i+1][0] for i in range(len(intervals)-1)))
        cp.atomic_private(dest/'status.json',state);print(json.dumps(state),flush=True);return state
    finally:lock.unlink(missing_ok=True)

def audit(run_dir):
    directory,run,calls,prompts=vw.load_run(run_dir);root=directory.parent;dest=root/'source-review'
    ap, ar = protocols(run); protocol = review_protocol(run)
    plan=au.read_object(dest/'plan.json');key=au.read_object(dest/'private-key.json')
    vw.require(plan['run_sha256']==run['run_sha256'] and plan['schema']==batch_schema(protocol) and plan['instructions']==ar.INSTRUCTIONS and plan['model']==review_model(run),'Source review plan changed')
    records,expected_key,rejected=candidates(root,calls,prompts,run)
    vw.require(plan['tasks']==records and key==expected_key and plan.get('structural_rejections')==rejected and plan.get('total_candidates')==len(calls),'Review coverage or structural failure set changed')
    all_candidates={v['call_id'] for v in key.values()}
    review_rejections={p.name[:-len('.review-rejected.json')] for p in dest.glob('*.review-rejected.json')}
    vw.require(review_rejections<=all_candidates, 'Unknown rejected review candidate')
    expected_files={c+'.assessment.json' for c in all_candidates-review_rejections}
    vw.require({p.name for p in dest.glob('*.assessment.json')}==expected_files,'Incomplete or extra assessments')
    vw.require({p.name for p in dest.glob('*.final.json')}=={n.replace('.assessment.','.final.') for n in expected_files},'Incomplete or extra final outputs')
    vw.require({p.name for p in dest.glob('*.rejected.json')}=={c+'.rejected.json' for c in rejected},'Rejected output grid differs')
    for cid,row in rejected.items():vw.require(au.read_object(dest/(cid+'.rejected.json'))==row,'Structural rejection changed')
    total_in=total_out=reviewed=global_rejections=0;ids=set();intervals=[];hashes={}
    for offset in range(0,len(plan['tasks']),4):
        batch=plan['tasks'][offset:offset+4];bid=f'B{offset//4+1:03d}'
        receipt=au.read_object(dest/(bid+'.receipt.json'));index=au.read_object(dest/(bid+'.index.json'))
        sha=hashlib.sha256((dest/(bid+'.receipt.json')).read_bytes()).hexdigest();vw.require(sha==index['receipt_sha256'],'Review receipt changed');hashes[bid]=sha
        body={'model':plan['model'],'instructions':plan['instructions'],'input':[{'role':'user','content':[{'type':'input_text','text':json.dumps({'tasks':outbound_tasks(batch,protocol)},ensure_ascii=False)}]}],'reasoning':{'effort':'low'},'store':False,'stream':True,'text':{'format':{'type':'json_schema','name':'authentic_user_trial','strict':True,'schema':batch_schema(protocol)}}}
        vw.require(hashlib.sha256(json.dumps(body,ensure_ascii=False).encode()).hexdigest()==receipt['request_body_sha256']==index['request_body_sha256'],'Review transmitted body differs')
        response=receipt['response'];rid=response['id'];vw.require(rid==index['response_id'] and rid not in ids and response['status']=='completed' and response['model']==plan['model'] and receipt['paid_fallback_used'] is False,'Review response identity/status/billing mismatch');ids.add(rid)
        interval=(index['started_unix'],index['finished_unix']);vw.require(interval[0]<=interval[1],'Review clock invalid');intervals.append(interval)
        for field in ('input_tokens','output_tokens'):
            if field=='input_tokens':total_in+=response['usage'][field]
            else:total_out+=response['usage'][field]
        rows=json.loads(receipt['text'])['reviews'];vw.require(len(rows)==len(batch) and {r['review_id'] for r in rows}=={x['review_id'] for x in batch},'Review grid mismatch')
        by_id={r['review_id']:r for r in rows}
        for task in batch:
            cid=key[task['review_id']]['call_id'];source=au.read_object(root/'incoming'/(cid+'.json'))['answer']['wire_answer'];evidence=prompts[calls[cid]['prompt']]['payload']['user_context']['evidence']
            candidate = source
            if ap is atomic_protocol:
                candidate, log = precheck(evidence, source)
                vw.require(task['original_wire_sha256']==ar.digest(source) and task['precheck']==log, 'Precheck differs from original strict candidate')
            vw.require(task['candidate']==candidate and task['evidence']==evidence and task['wire_sha256']==ar.digest(candidate) and task['evidence_sha256']==ar.digest(evidence),'Review task differs from original or deterministic withdrawal')
            assessment={k:v for k,v in by_id[task['review_id']].items() if k!='review_id'}
            try:expected=derive(evidence,candidate,assessment,run)
            except ap.ProtocolError as exc:
                rejected_review={'call_id':cid,'review_id':task['review_id'],'origin':'global_assessment_contract_rejection','candidate_sha256':task['wire_sha256'],'raw_assessment_sha256':ar.digest(assessment),'error':str(exc),'batch':bid}
                vw.require(cid in review_rejections and au.read_object(dest/(cid+'.review-rejected.json'))==rejected_review, 'Rejected review differs from raw response')
                reviewed+=1;global_rejections+=1;continue
            vw.require(cid not in review_rejections and assessment==au.read_object(dest/(cid+'.assessment.json')),'Saved assessment differs from raw response')
            derived=au.read_object(dest/(cid+'.final.json'))
            if ap is atomic_protocol: expected.update(original_wire_sha256=ar.digest(source), precheck=log)
            vw.require(derived['call_id']==cid and derived['candidate_sha256']==ar.digest(candidate) and derived['assessment_sha256']==ar.digest(assessment) and all(derived.get(k)==v for k,v in expected.items()),'Derived output not reproducible from review')
            reviewed+=1
    vw.require(all(intervals[i][1]<=intervals[i+1][0] for i in range(len(intervals)-1)),'Overlapping source review calls')
    state=au.read_object(dest/'status.json');vw.require(state['status'] in ('completed','completed_with_review_rejections','completed_with_pending_reviews') and state['reviewed_answers']==reviewed==len(records) and state['structural_rejections']==len(rejected) and state.get('global_review_rejections',0)==global_rejections and state['completed_batches']==len(ids) and state['input_tokens']==total_in and state['output_tokens']==total_out,'Source review counters mismatch')
    pending=sum(len(au.read_object(p).get('review_contract_errors',[])) for p in dest.glob('*.final.json'))
    if protocol==clause_review.NAME:vw.require(state['review_pending_atoms']==pending,'Pending atom count differs')
    return {'local_integrity_passed':True,'provider_verified_independently':False,'total_candidates':len(calls),'structural_rejections':len(rejected),'reviewed_answers':reviewed,'global_review_rejections':global_rejections,'all_assessments_usable':global_rejections==0 and pending==0,'all_atom_reviews_valid':pending==0,'valid_assessments':reviewed-global_rejections,'review_contract_error_atoms':pending,'review_pending_atom_count':pending if protocol==clause_review.NAME else 0,'review_protocol':protocol,'review_model':plan['model'],'completed_batches':len(ids),'unique_response_ids':len(ids),'overlapping_calls':0,'input_tokens':total_in,'output_tokens':total_out,'paid_fallback_used':False,'receipt_index_sha256':vw.digest(hashes),'origin':'separate_plan_model_context; not independent human'}

def main():
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='precheck':
        parser=argparse.ArgumentParser(description='Local atom withdrawal; preserve original and audit, no model call')
        for name in ('bundle','answer','output','audit-output'):parser.add_argument('--'+name,required=True)
        a=parser.parse_args(sys.argv[2:])
        try:
            result,log=precheck_bundle(au.read_object(a.bundle),au.read_object(a.answer))
            log['original_answer_file_sha256']=hashlib.sha256(Path(a.answer).read_bytes()).hexdigest()
            vw.require(not Path(a.output).exists() and not Path(a.audit_output).exists(), 'Precheck output already exists')
            au.write_new(a.audit_output,json.dumps(log,ensure_ascii=False,indent=2)+'\n')
            au.write_new(a.output,json.dumps(result,ensure_ascii=False,indent=2)+'\n');return 0
        except (au.InputError,ap.ProtocolError,OSError,KeyError,TypeError,ValueError) as exc:
            print(json.dumps({'ok':False,'error':str(exc) if isinstance(exc,(au.InputError,ap.ProtocolError)) else type(exc).__name__}));return 2
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',required=True);p.add_argument('--credential-dir',required=True);p.add_argument('--consent-file',required=True);p.add_argument('--phase-config');a=p.parse_args()
    try:return 0 if execute(a.run_dir,a.credential_dir,a.consent_file,a.phase_config)['status']=='completed' else 2
    except (au.InputError,ap.ProtocolError,OSError,KeyError,TypeError,ValueError) as e:
        print(json.dumps({'status':'stopped_review','reason':str(e) if isinstance(e,(au.InputError,ap.ProtocolError)) else type(e).__name__}));return 2
if __name__=='__main__':raise SystemExit(main())
