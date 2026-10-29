"""Offline trial safety and failure-inclusion regressions."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import authentic_user as au
import chatgpt_plan as cp
import plan_trial as pt
import validation_workflow as vw
import test_validation_workflow as fixture_module


# A small standalone class reuses the fixture lifecycle and builders explicitly.
class TrialSafetyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.ValidationWorkflowTests()
        self.fixture.setUp()
        self.fixture.freeze()
        self.directory, self.run, self.calls, self.prompts = vw.load_run(self.fixture.run_dir)

    def tearDown(self):
        self.fixture.tearDown()

    def test_second_runner_cannot_start_or_remove_first_lock(self):
        lock = self.directory / '.plan-trial.lock'
        lock.write_text('synthetic existing lock')
        with patch.object(cp, 'PlanClient') as client:
            with self.assertRaises(cp.PlanStop):
                pt.execute(self.directory, 'unused', 'unused')
            client.assert_not_called()
        self.assertTrue(lock.exists())

    def test_consent_missing_stops_before_client_creation(self):
        config = copy.deepcopy(self.run)
        config['model_config']['provider'] = 'openai-chatgpt-plan'
        config['model_config']['synthetic'] = False
        consent = self.fixture.root / 'consent.json'
        consent.write_text(json.dumps({'approved': False}))
        with patch.object(vw, 'load_run', return_value=(self.directory, config, self.calls, self.prompts)), patch.object(cp, 'PlanClient') as client:
            with self.assertRaises(au.InputError):
                pt.execute(self.directory, 'unused', consent)
            client.assert_not_called()
        self.assertFalse((self.directory / '.plan-trial.lock').exists())

    def plan_fixture(self):
        run = copy.deepcopy(self.run)
        config = run['model_config']
        config.update(provider='openai-chatgpt-plan', synthetic=False)
        config['transport'] = {'output_schema_sha256': vw.digest(cp.answer_schema()), 'concurrency': 1,
                               'automatic_retries': 0, 'execution_order': 'paired_interleaved_v1',
                               'max_input_characters': 40000, 'max_output_characters': 16000,
                               'reported_output_token_guard': 4000, 'adapter_instructions': 'synthetic'}
        consent = self.fixture.root / 'consent.json'
        consent.write_text(json.dumps({'run_sha256': run['run_sha256'], 'approved': True,
                                      'destination': cp.API + '/responses', 'subscription_only': True,
                                      'human_authorization': 'synthetic fixture only'}))
        return run, consent

    def test_quota_failure_stops_whole_schedule_without_retry(self):
        run, consent = self.plan_fixture()
        client = Mock()
        client.respond.side_effect = cp.PlanStop('subscription_sharing_usage_limit_exceeded')
        with patch.object(vw, 'load_run', return_value=(self.directory, run, self.calls, self.prompts)), patch.object(cp, 'PlanClient', return_value=client), patch('builtins.print'):
            result = pt.execute(self.directory, 'unused', consent)
        self.assertEqual(result['status'], 'stopped_transport')
        self.assertEqual(result['provider_completed'], 0)
        self.assertEqual(client.respond.call_count, 1)
        self.assertFalse(result['paid_fallback_used'])

    def test_existing_receipt_cannot_be_overwritten_before_call(self):
        run, consent = self.plan_fixture()
        subset = dict(list(self.calls.items())[:1])
        cid = next(iter(subset))
        target = self.directory.parent / 'provider-events' / (cid + '.json')
        target.parent.mkdir()
        target.write_text('{"synthetic_sentinel":true}')
        before = target.read_bytes()
        client = Mock()
        with patch.object(vw, 'load_run', return_value=(self.directory, run, subset, self.prompts)), patch.object(cp, 'PlanClient', return_value=client):
            with self.assertRaises(au.InputError):
                pt.execute(self.directory, 'unused', consent)
        client.respond.assert_not_called()
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.directory / '.plan-trial.lock').exists())

    def test_contract_failure_preserved_and_not_retried(self):
        run, consent = self.plan_fixture()
        subset = dict(list(self.calls.items())[:2])
        client = Mock()
        client.respond.return_value = {'text': '{"answer":"synthetic"}',
            'response': {'id': 'synthetic-response', 'model': run['model_config']['model'],
                         'usage': {'input_tokens': 100, 'output_tokens': 50}}, 'request_body_sha256': 'synthetic'}
        with patch.object(vw, 'load_run', return_value=(self.directory, run, subset, self.prompts)), patch.object(cp, 'PlanClient', return_value=client), patch.object(vw, 'ingest', side_effect=au.InputError('Synthetic contract failure')), patch('builtins.print'):
            result = pt.execute(self.directory, 'unused', consent)
        self.assertEqual(result['status'], 'completed_with_structural_failures')
        self.assertEqual(result['provider_completed'], 2)
        self.assertEqual(result['structural_failures'], 2)
        self.assertEqual(client.respond.call_count, 2)
        incoming = list((self.directory.parent / 'incoming').glob('*.json'))
        self.assertEqual(len(incoming), 2)
        self.assertTrue(all(au.read_object(p)['answer'] == {'answer': 'synthetic'} for p in incoming))

    def test_raw_review_keeps_contract_failure_without_repair(self):
        source = self.fixture.root / 'incoming'
        source.mkdir()
        first_key = next(iter(self.calls))
        for key, call in self.calls.items():
            response = self.fixture.response(self.run, call, self.prompts)
            if key == first_key:
                response['answer']['answer'] = 'AI 模拟：无正文引用，必须保留原始格式失败。'
            (source / (key + '.json')).write_text(json.dumps(response))
        responses, failures = vw.raw_responses_for(source, self.run, self.calls, self.prompts)
        self.assertEqual(len(failures), 1)
        self.assertIn(first_key, failures)
        self.assertNotIn('[E', responses[first_key]['answer']['answer'])
        target = self.fixture.root / 'blinded'
        vw.blind(self.directory, self.fixture.judges, target, True, source)
        tasks = [au.read_object(p) for p in (target / 'tasks').glob('*.json')]
        self.assertEqual(sum(not t['mechanical_check']['passed'] for t in tasks), 1)
        grades = au.read_object(target / 'scores.template.json')
        grades.update(reviewer='synthetic assistant fixture', origin='assistant_review')
        targets = {'attitude_direction': 'Q2', 'theme_overlap': 'Q3', 'unknown_restraint': 'Q4'}
        task_map = {t['review_id']: t for t in tasks}
        for row in grades['scores']:
            row['status'] = 'scored'
            for metric in vw.METRICS:
                row['scores'][metric] = 0 if metric not in targets or targets[metric] == task_map[row['review_id']]['question_id'] else None
        for row in grades['repeat_scores']:
            row.update(status='scored', score=1)
        score_file = self.fixture.root / 'scores.json'
        score_file.write_text(json.dumps(grades))
        report = vw.summarize(self.directory, score_file)
        self.assertEqual(report['answer_contract_failures'], 1)
        self.assertEqual(report['reviewed_answers'], len(self.calls))
        self.assertEqual(report['status'], 'scored_exploratory')
        # A raw metadata mismatch is still rejected; failure mode is not an integrity bypass.
        path = source / (first_key + '.json')
        response = au.read_object(path)
        response['run_sha256'] = 'different-run'
        path.write_text(json.dumps(response))
        with self.assertRaises(au.InputError):
            vw.raw_responses_for(source, self.run, self.calls, self.prompts)

    def test_real_second_process_cannot_enter_same_execution(self):
        import subprocess
        import time
        script = str(Path(__file__).resolve().parents[1] / 'scripts')
        code = "import sys,time;sys.path.insert(0,sys.argv[1]);import plan_trial as p;p._execute=lambda *args:(print('LOCKED',flush=True),time.sleep(2));p.execute(sys.argv[2],'unused','unused')"
        child = subprocess.Popen([sys.executable,'-c',code,script,str(self.directory)],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'LOCKED')
            with patch.object(cp,'PlanClient') as client:
                with self.assertRaises(cp.PlanStop):pt.execute(self.directory,'unused','unused')
                client.assert_not_called()
            self.assertTrue((self.directory/'.plan-trial.lock').exists())
        finally:
            child.wait(timeout=5)
            child.stdout.close()
        self.assertFalse((self.directory/'.plan-trial.lock').exists())

    def test_complete_typed_execution_receipts_reconcile_and_tampering_fails(self):
        import hashlib
        import claim_protocol as typed
        import trial_audit
        config=copy.deepcopy(self.fixture.config)
        config.update(provider='openai-chatgpt-plan',model='synthetic-plan-model',revision='provider-alias:synthetic',synthetic=False,
                      parameters={'temperature':None,'top_p':None,'max_output_tokens':None})
        config['transport']={'route':cp.API+'/responses','store':False,'stream':True,'billing_policy':'subscription_only_no_paid_fallback',
            'reasoning_effort':'low','revision_policy':'provider_alias_exploratory','max_input_characters':40000,'max_output_characters':16000,
            'reported_output_token_guard':4000,'concurrency':1,'automatic_retries':0,'execution_order':'paired_interleaved_v1',
            'adapter_instructions':'synthetic-only','response_protocol':'typed-source-v2','output_schema_sha256':vw.digest(typed.schema())}
        root=self.fixture.root/'typed-plan';root.mkdir();run_dir=root/'run';config_file=root/'config.json';config_file.write_text(json.dumps(config))
        new_inputs=root/'inputs';fixture_module.vp.reframe(self.fixture.inputs,new_inputs)
        review=au.read_object(self.fixture.review_file);review['inputs_manifest_sha256']=vw.digest(au.read_object(new_inputs/'manifest.json'))
        review_file=root/'review.json';review_file.write_text(json.dumps(review))
        vw.freeze(new_inputs,config_file,review_file,run_dir)
        _,run,_,_=vw.load_run(run_dir)
        consent=root/'consent.json';consent.write_text(json.dumps({'run_sha256':run['run_sha256'],'approved':True,'destination':cp.API+'/responses','subscription_only':True,'human_authorization':'synthetic fixture only'}))
        counter=[]
        def respond(model,prompt,instructions,**kwargs):
            counter.append(1)
            body={'model':model,'instructions':instructions,'input':[{'role':'user','content':[{'type':'input_text','text':prompt}]}],
                  'reasoning':{'effort':'low'},'store':False,'stream':True,
                  'text':{'format':{'type':'json_schema','name':'authentic_user_trial','strict':True,'schema':kwargs['schema']}}}
            wire={'protocol_version':2,'facts':[],'inferences':[],'direction':'unknown','unknowns':['synthetic fixture unknown']}
            return {'text':json.dumps(wire),'response':{'id':'synthetic-response-'+str(len(counter)),'status':'completed','model':model,
                    'usage':{'input_tokens':100,'output_tokens':50}},'request_body_sha256':hashlib.sha256(json.dumps(body,ensure_ascii=False).encode()).hexdigest(),'paid_fallback_used':False}
        client=Mock();client.respond.side_effect=respond
        with patch.object(cp,'PlanClient',return_value=client),patch('builtins.print'):
            result=pt.execute(run_dir,'unused',consent)
        self.assertEqual(result['status'],'completed')
        audit=trial_audit.audit(run_dir)
        self.assertTrue(audit['local_integrity_passed']);self.assertEqual(audit['complete_grid'],64)
        raw=next((root/'provider-events').glob('*.json'));raw.write_text(raw.read_text()+' ')
        with self.assertRaises(au.InputError):trial_audit.audit(run_dir)
