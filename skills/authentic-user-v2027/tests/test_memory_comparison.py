"""Single model arm vs computed baselines, preserving user/repeat denominators."""
import json
import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import authentic_user as au
import validation_prep as vp
import validation_workflow as vw
import validation_report as report
import atomic_protocol as atomic
import source_registry as sr
import plan_review as pr
import test_validation_workflow as fixtures


class MemoryComparisonTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ValidationWorkflowTests();self.f.setUp()
        self.inputs,self.judges,self.run_dir=(self.f.root/n for n in ('memory-inputs','memory-judges','memory-run'))
        vp.build(self.f.fixture.profiles,self.inputs,self.judges,per_group=1,repeats=2,
                 response_protocol='atomic-bound-v4',comparison_kind=vp.MEMORY_COMPARISON)
        _,manifest,_,calls,_=vw.audit_inputs(self.inputs)
        self.review=self.f.root/'memory-review.json'
        vw.save(self.review,{'inputs_manifest_sha256':vw.digest(manifest),'reviewer':'synthetic fixture',
                            'cases':{c['case']:{'status':'reviewed','unsupported_parts':['synthetic unknown amount']} for c in calls}})
        config=dict(self.f.config,provider='openai-chatgpt-plan',parameters={'temperature':None,'top_p':None,'max_output_tokens':None})
        config['transport']={'route':'https://api.openai.com/v1/responses','store':False,'stream':True,
                             'billing_policy':'subscription_only_no_paid_fallback','reasoning_effort':'low',
                             'revision_policy':'provider_alias_exploratory','max_input_characters':40000,'max_output_characters':20000,
                             'reported_output_token_guard':6000,'response_protocol':'atomic-bound-v4',
                             'output_schema_sha256':vw.digest(atomic.schema()),
                             'execution_sources_sha256':{'record_selection.py':hashlib.sha256((ROOT/'scripts/record_selection.py').read_bytes()).hexdigest()}}
        self.f.config_file.write_text(json.dumps(config))

    def tearDown(self):self.f.tearDown()

    def freeze(self):
        vw.freeze(self.inputs,self.f.config_file,self.review,self.run_dir)
        return vw.load_run(self.run_dir)

    def test_four_users_have_32_calls_and_16_prompts_not_a_fake_tag_arm(self):
        _,manifest,protocol,calls,prompts=vw.audit_inputs(self.inputs)
        self.assertEqual(manifest['users'],4);self.assertEqual(len(calls),32);self.assertEqual(len(prompts),16)
        self.assertEqual({c['condition'] for c in calls},{'M'})
        self.assertEqual(protocol['computed_attitude_baselines'],['last_same_industry','constant_promoter','constant_passive','constant_detractor'])
        self.assertTrue(vw.audit(self.inputs,self.judges)['judge_checksums_verified'])

    def test_single_arm_rejects_x_y_calls_instead_of_silently_changing_denominator(self):
        p=self.inputs/'calls.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()]
        rows[0]['condition']='X';p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
        with self.assertRaisesRegex(au.InputError,'Invalid condition'):vw.audit_inputs(self.inputs)

    def test_model_answer_import_blind_pack_and_descriptive_scores_use_actual_grid(self):
        directory,run,calls,prompts=self.freeze()
        _,judges=vw.load_judges(self.judges,run)
        for cid,call in calls.items():
            response=self.f.response(run,call,prompts)
            evidence=prompts[call['prompt']]['payload']['user_context']['evidence']
            book=sr.lookup(evidence);ref=next(k for k,v in book.items() if v.get('field')=='text')
            wire={'protocol_version':4,'facts':[ref],'atoms':[],'direction':'unknown','direction_atom':None,'unknowns':['no_observed_outcome']}
            if call['question_id']=='Q2':
                wire.update(atoms=[{'kind':'conditional_forecast','text':'如果相似体验持续，可能保持评价。','condition':'similar_experience','confidence':'low','anchors':[{'ref':ref,'quote':sr.value_text(book[ref])}]}],direction=judges[call['case']]['hidden_segment'],direction_atom=0)
            response['answer']=atomic.render(evidence,wire)
            path=self.f.root/'inbox'/f'{cid}.json';vw.save(path,response);vw.ingest(directory,path)
            vw.save(directory.parent/'incoming'/f'{cid}.json',response)
        self.assertEqual(vw.status(directory)['imported_responses'],32)
        pack=self.f.root/'memory-pack';vw.blind(directory,self.judges,pack,True)
        template=au.read_object(pack/'scores.template.json');template.update(reviewer='synthetic only',origin='synthetic_test')
        targets={'attitude_direction':'Q2','theme_overlap':'Q3','unknown_restraint':'Q4'}
        for row in template['scores']:
            qid=au.read_object(pack/'tasks'/f"{row['review_id']}.json")['question_id']
            row['status']='scored'
            row['scores']={m:None if m in targets and targets[m]!=qid else 0 if m=='fabricated_experience_rate' else 1 for m in vw.METRICS}
        for row in template['repeat_scores']:row.update(status='scored',score=1)
        path=self.f.root/'memory-scores.synthetic.json';vw.save(path,template)
        result=vw.summarize(directory,path)
        self.assertEqual(result['comparison_kind'],vp.MEMORY_COMPARISON)
        self.assertEqual(result['metrics']['fact_accuracy']['users'],4)
        self.assertEqual(result['metrics']['fact_accuracy']['mean'],1)
        self.assertEqual(len(template['repeat_scores']),16)
        q2=report.attitude(directory,self.judges,model_phases_ended=True)
        self.assertNotIn('historical_tag_baseline',q2['metrics'])
        self.assertEqual(q2['metrics']['individual_memory']['correct_positions'],8)
        self.assertEqual(q2['memory_vs_simple_baselines']['last_same_industry']['paired_users'],4)

    def test_comparison_and_condition_mapping_are_frozen(self):
        directory,run,_,_=self.freeze()
        run['comparison_kind']=vp.TAG_COMPARISON;run['run_sha256']=vw.digest({k:v for k,v in run.items() if k!='run_sha256'})
        (directory/'run.json').write_text(json.dumps(run))
        with self.assertRaisesRegex(au.InputError,'comparison design'):vw.load_run(directory)

    def test_invalid_design_or_budget_is_rejected_before_material_is_created(self):
        for kwargs in ({'comparison_kind':vp.MEMORY_COMPARISON}, {'max_records':0}, {'selection_policy':'invented'}):
            a,b=self.f.root/'bad-inputs',self.f.root/'bad-judges'
            with self.assertRaises(au.InputError):vp.build(self.f.fixture.profiles,a,b,**kwargs)
            self.assertFalse(a.exists());self.assertFalse(b.exists())

    def test_frozen_atomic_run_rejects_free_text_but_keeps_raw_failure_for_analysis(self):
        directory,run,calls,prompts=self.freeze()
        cid=next(k for k,c in calls.items() if c['question_id']=='Q2')
        response=self.f.response(run,calls[cid],prompts)
        path=directory.parent/'incoming'/f'{cid}.json';vw.save(path,response)
        before=path.read_bytes()
        with self.assertRaisesRegex(au.InputError,'protocol differs'):vw.ingest(directory,path)
        _,failures=vw.raw_responses_for(path.parent,run,calls,prompts)
        self.assertIn(cid,failures);self.assertEqual(path.read_bytes(),before)
        result=report.attitude(directory,self.judges,model_phases_ended=True)
        self.assertEqual(result['metrics']['individual_memory']['states']['invalid'],1)

    def test_capability_tamper_is_detected_after_rehashing_prompt(self):
        p=next((self.inputs/'S001/M').glob('Q*.txt'))
        header,payload=vw.decode_prompt(p.read_text());payload['user_context']['capability']['level']='facts_only'
        raw=header+json.dumps(payload,ensure_ascii=False)+'\n';p.write_text(raw)
        manifest=au.read_object(self.inputs/'manifest.json')
        for row in manifest['inputs']:
            if row['path']==p.relative_to(self.inputs).as_posix():row['sha256']=vw.text_digest(raw)
        (self.inputs/'manifest.json').write_text(json.dumps(manifest))
        calls_path=self.inputs/'calls.jsonl';calls=[json.loads(line) for line in calls_path.read_text().splitlines()]
        for call in calls:
            if call['prompt']==p.relative_to(self.inputs).as_posix():call['prompt_sha256']=vw.text_digest(raw)
        calls_path.write_text(''.join(json.dumps(call)+'\n' for call in calls))
        with self.assertRaisesRegex(au.InputError,'capability differs'):vw.audit_inputs(self.inputs)

    def test_facts_only_precheck_withdraws_atoms_and_keeps_selected_fields(self):
        evidence=[{'id':'E001','kind':'survey','date':'2025-01-01','score':0,'tags':['费用']}]
        ref=next(k for k,v in sr.lookup(evidence).items() if v.get('field')=='score')
        wire={'protocol_version':4,'facts':[ref],'atoms':[{'kind':'conditional_forecast','text':'如果费用下降，可能更满意。','condition':'topic_improves','confidence':'low','anchors':[{'ref':ref,'quote':'0'}]}],
              'direction':'promoter','direction_atom':0,'unknowns':['no_direct_intent']}
        final,log=pr.precheck(evidence,wire,'facts_only')
        self.assertFalse(log['original_strict_contract_pass'])
        self.assertEqual(final['facts'],[ref]);self.assertEqual(final['atoms'],[]);self.assertEqual(final['direction'],'unknown')


if __name__=='__main__':unittest.main()
