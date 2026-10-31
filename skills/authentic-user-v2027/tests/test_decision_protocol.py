"""Behavioral invariants on synthetic histories; no models or actual effectiveness scores."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import attitude_baseline as baseline
import decision_protocol as p
import decision_review as review
import source_registry as sr
import validation_workflow as vw
import validation_prep as vp
import test_validation_workflow as fixtures


def history():
    return [
        {'id':'E001','kind':'survey','industry':'rental','date':'2025-01-01','score':10,'tags':['服务']},
        {'id':'E002','kind':'verbatim','industry':'rental','date':'2025-02-01','score':0,'text':'合成原話：沒有按約定辦理，尚未收到退款。'},
        {'id':'E003','kind':'survey','industry':'rental','date':'2025-03-01','score':0,'tags':['规则']},
        {'id':'E004','kind':'verbatim','industry':'rental','date':'2025-03-02','score':10,'text':'合成示例：态度有改善。'},
    ]


def ref(evidence,eid,field):
    return next(k for k,v in sr.lookup(evidence).items() if v.get('evidence_id')==eid and v.get('field')==field)


def candidate(evidence):
    result=p.empty();result['facts']=[ref(evidence,'E003','score')]
    result['reactions']=[{'text':'如果此次办理符合约定，可能更满意。','source_refs':[ref(evidence,'E002','text')],'confidence':'low'}]
    result['prediction']={'direction':'detractor','reason':'所选最近调查评分为0，延续仅是估计。',
                          'source_refs':[ref(evidence,'E003','score')],'confidence':'low'}
    return result


def assessment(evidence,wire):
    task=review.task(evidence,wire,'individual_memory','rental')
    checks=[]
    for a in task['atom_bindings']:
        checks.append({'atom_index':a['atom_index'],'clauses':[
            {'clause_index':c['clause_index'],'role':'future_consequence' if a['kind']=='attitude_estimate' else 'future_condition',
             'premise':'grounded','scope':'within_source','inference':'bounded_hypothesis','source_refs':a['selected_refs'],
             'issue':'none','problem_span':'','reason':'Synthetic check fixture only.'} for c in a['clauses']]})
    return {'review_version':4,'evidence_sha256':task['evidence_sha256'],'wire_sha256':task['wire_sha256'],'items':checks}


def reject_first_clause(item,atom):
    item['clauses'][0].update(premise='unsupported',scope='expanded',inference='overclaim',issue='unsupported_detail',
                             problem_span=review.prior.clauses(atom['text'])[0].strip(),reason='Synthetic rejection fixture.')


class DecisionTests(unittest.TestCase):
    def setUp(self):self.e=history();self.w=candidate(self.e)

    def test_zero_survey_not_later_verbatim_is_the_baseline(self):
        b=baseline.card(self.e,'rental')
        self.assertEqual(b['direction'],'detractor');self.assertEqual(b['latest_score'],0)
        self.assertEqual(b['category_changes'],1)
        self.assertEqual(b['source_refs'],[ref(self.e,'E003','score')])
        self.assertFalse(b['is_ai_prediction']);self.assertFalse(b['calibrated'])

    def test_conflicting_latest_scores_abstain_and_preserve_both(self):
        self.e.append({'id':'E005','kind':'survey','industry':'rental','date':'2025-03-01','score':9,'tags':[]})
        b=baseline.card(self.e,'rental')
        self.assertEqual(b['direction'],'unknown');self.assertIsNone(b['latest_score'])
        self.assertEqual(b['trajectory'][-1]['scores'],[0,9]);self.assertEqual(len(b['source_refs']),2)

    def test_mixed_industry_requires_an_explicit_target(self):
        self.e.append({'id':'E005','kind':'survey','industry':'train','date':'2025-04-01','score':9,'tags':[]})
        self.assertEqual(baseline.card(self.e)['status'],'ambiguous_industry')
        self.assertEqual(baseline.card(self.e,'rental')['direction'],'detractor')
        with self.assertRaises(p.ProtocolError):p.render(self.e,self.w,'individual_memory')

    def test_quotes_are_extracted_without_retyping_traditional_characters_or_negation(self):
        original=copy.deepcopy(self.w);unit=p.units(self.e,self.w,'individual_memory','rental')[0]
        self.assertEqual(unit['anchors'][0]['quote'],self.e[1]['text'])
        self.assertEqual(self.w,original)
        self.assertNotIn('quote',self.w['reactions'][0])

    def test_invalid_reaction_does_not_delete_a_valid_independent_estimate(self):
        self.w['reactions'][0]['source_refs']=['F999'];original=copy.deepcopy(self.w)
        out,log=p.precheck(self.e,self.w,'individual_memory','rental')
        self.assertEqual(p.render(self.e,out,'individual_memory','rental')['direction'],'detractor')
        self.assertEqual(out['reactions'],[]);self.assertFalse(log['original_strict_contract_pass'])
        self.assertEqual(len(log['component_errors']),1);self.assertEqual(self.w,original)

    def test_review_rejects_reaction_but_preserves_estimate_and_original(self):
        a=assessment(self.e,self.w);atoms=p.units(self.e,self.w);original=copy.deepcopy(self.w)
        reject_first_clause(a['items'][0],atoms[0])
        out=review.apply(self.e,self.w,a,level='individual_memory',industry='rental')
        self.assertEqual(out['reactions'],[]);self.assertEqual(out['prediction'],self.w['prediction'])
        self.assertEqual(self.w,original)

    def test_estimate_rejection_does_not_fall_back_to_baseline_or_delete_reactions(self):
        a=assessment(self.e,self.w);atoms=p.units(self.e,self.w)
        reject_first_clause(a['items'][1],atoms[1])
        # A negative estimate is still a future inference even when rejected.
        a['items'][1]['clauses'][0]['inference']='bounded_hypothesis'
        out=review.apply(self.e,self.w,a,level='individual_memory',industry='rental')
        answer=p.render(self.e,out,'individual_memory','rental')
        self.assertIsNone(out['prediction']);self.assertEqual(out['reactions'],self.w['reactions'])
        self.assertEqual(answer['direction'],'unknown');self.assertEqual(answer['baseline']['direction'],'detractor')

    def test_incomplete_estimate_review_is_pending_without_losing_other_components(self):
        a=assessment(self.e,self.w);a['items'][1]['clauses'].pop();errors=[]
        out=review.apply(self.e,self.w,a,errors,level='individual_memory',industry='rental')
        self.assertEqual(len(errors),1);self.assertEqual(errors[0]['component_path'],['prediction'])
        self.assertIsNone(out['prediction']);self.assertEqual(out['reactions'],self.w['reactions'])

    def test_prediction_cannot_borrow_labels_or_other_industry(self):
        self.w['prediction']['source_refs']=[ref(self.e,'E003','tags')]
        with self.assertRaises(p.ProtocolError):p.validate(self.e,self.w,'individual_memory','rental')
        self.e.append({'id':'E005','kind':'survey','industry':'train','date':'2025-04-01','score':9,'tags':[]})
        self.w['prediction']['source_refs']=[ref(self.e,'E005','score')]
        with self.assertRaises(p.ProtocolError):p.validate(self.e,self.w,'individual_memory','rental')

    def test_limited_capability_allows_reactions_but_not_point_estimates(self):
        with self.assertRaises(p.ProtocolError):p.validate(self.e,self.w,'limited_attitude','rental')
        self.w['prediction']=None;p.validate(self.e,self.w,'limited_attitude','rental')
        with self.assertRaises(p.ProtocolError):p.validate(self.e,self.w,'facts_only','rental')

    def test_model_cannot_claim_script_review_states_or_invent_condition_fields(self):
        self.w['unknowns']=['review_pending']
        with self.assertRaises(p.ProtocolError):p.validate(self.e,self.w)
        self.w['unknowns']=[];self.w['reactions'][0]['condition']='topic_improves'
        with self.assertRaises(p.ProtocolError):p.validate(self.e,self.w)

    def test_wrong_protocol_is_not_repaired_by_precheck(self):
        self.w['protocol_version']=4
        with self.assertRaises(p.ProtocolError):p.precheck(self.e,self.w)

    def test_summary_cannot_silently_turn_a_tag_into_self_report(self):
        self.w['summaries']=[{'text':'合成标签摘要','source_refs':[ref(self.e,'E003','tags')],'confidence':'low'}]
        out,log=p.precheck(self.e,self.w,'individual_memory','rental')
        self.assertFalse(log['original_strict_contract_pass']);self.assertEqual(out['summaries'],[])

    def test_review_cannot_borrow_unselected_fields(self):
        a=assessment(self.e,self.w);a['items'][0]['clauses'][0]['source_refs']=[ref(self.e,'E003','score')];errors=[]
        out=review.apply(self.e,self.w,a,errors,level='individual_memory',industry='rental')
        self.assertEqual(len(errors),1);self.assertEqual(out['reactions'],[])
        self.assertIsNotNone(out['prediction'])

    def test_review_hash_failure_is_global_and_does_not_rewrite_candidate(self):
        a=assessment(self.e,self.w);a['wire_sha256']='wrong';original=copy.deepcopy(self.w)
        with self.assertRaises(p.ProtocolError):review.apply(self.e,self.w,a)
        self.assertEqual(self.w,original)

    def test_frozen_protocol_cannot_accept_legacy_answer_or_modified_rendering(self):
        context={'user_context':{'evidence':self.e,'capability':{'level':'individual_memory'},'target_industry':'rental'}}
        a=p.render(self.e,self.w,'individual_memory','rental');vw.check_common_answer(context,a,p.NAME)
        a['baseline']['direction']='promoter'
        with self.assertRaises(vw.au.InputError):vw.check_common_answer(context,a,p.NAME)
        with self.assertRaises(vw.au.InputError):vw.check_common_answer(context,{'protocol_version':4},p.NAME)


class DecisionInputTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ValidationWorkflowTests();self.f.setUp()
        self.inputs=self.f.root/'decision-inputs';self.judges=self.f.root/'decision-judges'
        vp.build(self.f.fixture.profiles,self.inputs,self.judges,per_group=1,repeats=1,include_zero=True,
                 response_protocol=p.NAME,comparison_kind=vp.MEMORY_COMPARISON)

    def tearDown(self):self.f.tearDown()

    def test_preparation_baseline_is_recomputed_from_visible_same_industry_only(self):
        _,_,protocol,calls,prompts=vw.audit_inputs(self.inputs)
        self.assertEqual(len(calls),16);self.assertEqual({c['condition'] for c in calls},{'M'})
        self.assertFalse(protocol['pilot_excludes_zero'])
        for row in prompts.values():
            u=row['payload']['user_context']
            self.assertEqual(u['baseline'],baseline.card(u['evidence'],u['target_industry']))

    def test_baseline_tamper_is_rejected_even_with_prompt_hashes_updated(self):
        path=self.inputs/'S001/M/Q2.txt';header,payload=vw.decode_prompt(path.read_text())
        payload['user_context']['baseline']['direction']='invented'
        text=header+json.dumps(payload,ensure_ascii=False)+'\n';path.write_text(text)
        manifest=vw.au.read_object(self.inputs/'manifest.json')
        relative=path.relative_to(self.inputs).as_posix()
        for row in manifest['inputs']:
            if row['path']==relative:row['sha256']=vw.text_digest(text)
        (self.inputs/'manifest.json').write_text(json.dumps(manifest))
        calls=[json.loads(line) for line in (self.inputs/'calls.jsonl').read_text().splitlines()]
        for row in calls:
            if row['prompt']==relative:row['prompt_sha256']=vw.text_digest(text)
        (self.inputs/'calls.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in calls))
        with self.assertRaisesRegex(vw.au.InputError,'Baseline card differs'):vw.audit_inputs(self.inputs)

    def test_incomplete_source_freeze_is_rejected_before_a_run_is_created(self):
        config=copy.deepcopy(self.f.config)
        config.update(provider='openai-chatgpt-plan',parameters={'temperature':None,'top_p':None,'max_output_tokens':None})
        config['transport']={'route':'https://api.openai.com/v1/responses','store':False,'stream':True,
            'billing_policy':'subscription_only_no_paid_fallback','reasoning_effort':'low','revision_policy':'provider_alias_exploratory',
            'max_input_characters':40000,'max_output_characters':20000,'reported_output_token_guard':6000,
            'response_protocol':p.NAME,'source_review_protocol':review.NAME,
            'output_schema_sha256':vw.digest(p.schema()),'execution_sources_sha256':{
                'record_selection.py':hashlib.sha256((ROOT/'scripts/record_selection.py').read_bytes()).hexdigest()}}
        cf=self.f.root/'decision-config.json';cf.write_text(json.dumps(config))
        rv=vw.au.read_object(self.f.review_file);rv['inputs_manifest_sha256']=vw.digest(vw.au.read_object(self.inputs/'manifest.json'))
        rf=self.f.root/'decision-review.json';rf.write_text(json.dumps(rv))
        target=self.f.root/'decision-run'
        with self.assertRaisesRegex(vw.au.InputError,'19 current execution sources'):vw.freeze(self.inputs,cf,rf,target)
        self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
