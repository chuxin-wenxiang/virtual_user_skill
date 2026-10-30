"""Interrupted ledgers and prediction denominators; synthetic artifacts only."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import authentic_user as au
import validation_workflow as vw
import validation_report as report
import test_validation_workflow as fixtures


class ValidationReportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ValidationWorkflowTests(); self.fixture.setUp(); self.fixture.freeze()
        self.directory, self.run, self.calls, self.prompts = vw.load_run(self.fixture.run_dir)
        self.root = self.directory.parent

    def tearDown(self): self.fixture.tearDown()

    def save(self, path, obj): vw.save(path, obj)

    def generation(self, cid, state='imported'):
        attempt = {'call_id': cid, 'run_sha256': self.run['run_sha256'], 'status': state}
        self.save(self.root/'attempts'/(cid+'.json'), attempt)
        if state == 'transport_failure': return
        envelope = self.fixture.response(self.run, self.calls[cid], self.prompts)
        envelope['provider_request_id'] = 'synthetic-'+cid
        saved = {'response': {'id': envelope['provider_request_id'], 'model': envelope['model'], 'status': 'completed',
                             'usage': dict(envelope['usage'], input_tokens_details={'cached_tokens': 0})},
                 'paid_fallback_used': False}
        rp, ep = self.root/'provider-events'/(cid+'.json'), self.root/'incoming'/(cid+'.json')
        self.save(rp, saved); self.save(ep, envelope)
        self.save(self.root/'receipt-index'/(cid+'.json'), {'call_id': cid, 'run_sha256': self.run['run_sha256'],
            'provider_response_id': envelope['provider_request_id'], 'receipt_sha256': report.sha(rp), 'envelope_sha256': report.sha(ep)})

    def source_plan(self):
        tasks = [{'review_id': f'A{i:04d}', 'wire_sha256': f'synthetic-wire-{i}'} for i in range(len(self.calls))]
        key = {t['review_id']: {'call_id': cid} for t, cid in zip(tasks, self.calls)}
        dest = self.root/'source-review'
        self.save(dest/'plan.json', {'run_sha256': self.run['run_sha256'], 'batch_size': 4,
            'total_candidates': len(self.calls), 'candidate_count': len(tasks), 'batches': (len(tasks)+3)//4,
            'tasks': tasks, 'model': 'synthetic-review-model', 'structural_rejections': {}})
        self.save(dest/'private-key.json', key)
        return dest, tasks, key

    def test_empty_run_reports_not_attempted_and_never_opens_hidden_material(self):
        with patch.object(vw, 'load_judges') as hidden:
            result = report.inventory(self.directory)
        hidden.assert_not_called()
        self.assertEqual(result['generation']['not_attempted'], 64)
        self.assertEqual(result['source_review_candidates']['not_planned'], 64)
        self.assertFalse(result['full_integrity_audit_performed'])

    def test_transport_failure_is_unknown_not_zero_usage_or_completed(self):
        cids = list(self.calls)
        self.generation(cids[0]); self.generation(cids[1], 'structural_failure'); self.generation(cids[2], 'transport_failure')
        before = {str(p): p.read_bytes() for p in self.root.rglob('*.json')}
        result = report.inventory(self.directory)
        self.assertEqual(result['generation']['request_state_unknown'], 1)
        self.assertEqual(result['generation']['not_attempted'], 61)
        self.assertEqual(result['generation']['indexed_structural_failure'], 1)
        self.assertEqual(result['known_indexed_usage'], {'input_tokens': 200, 'output_tokens': 60})
        self.assertIsNone(result['unknown_request_usage'])
        self.assertFalse(result['automatic_resume_allowed'])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*.json')})

    def test_saved_receipt_without_initial_index_is_not_certified(self):
        cid = next(iter(self.calls)); self.generation(cid)
        (self.root/'receipt-index'/(cid+'.json')).unlink()
        result = report.inventory(self.directory)
        self.assertEqual(result['generation']['response_saved_unverified'], 1)
        self.assertEqual(result['known_indexed_usage']['input_tokens'], 0)
        self.assertFalse(result['generation_response_grid_complete'])

    def test_tampered_receipt_and_extra_call_fail_instead_of_printing_complete(self):
        cid = next(iter(self.calls)); self.generation(cid)
        p = self.root/'provider-events'/(cid+'.json'); p.write_text(p.read_text()+' ')
        with self.assertRaises(au.InputError): report.inventory(self.directory)
        self.save(self.root/'attempts/unplanned.json', {})
        with self.assertRaises(au.InputError): report.inventory(self.directory)

    def test_partial_source_grid_separates_final_unknown_and_unattempted(self):
        for cid in self.calls: self.generation(cid)
        dest, tasks, key = self.source_plan()
        for bid in ('B001', 'B002'):
            self.save(dest/(bid+'.attempt.json'), {'run_sha256': self.run['run_sha256'], 'status': 'started'})
        rp = dest/'B001.receipt.json'
        self.save(rp, {'response': {'id': 'synthetic-source-response', 'status': 'completed', 'model': 'synthetic-review-model',
                                   'usage': {'input_tokens': 200, 'output_tokens': 70}}, 'paid_fallback_used': False})
        self.save(dest/'B001.index.json', {'receipt_sha256': report.sha(rp), 'response_id': 'synthetic-source-response'})
        for i, t in enumerate(tasks[:4]):
            cid = key[t['review_id']]['call_id']
            self.save(dest/(cid+'.final.json'), {'call_id': cid, 'candidate_sha256': t['wire_sha256'], 'review_contract_errors': ['synthetic-pending'] if i == 0 else []})
        result = report.inventory(self.directory)
        self.assertEqual(result['source_review_candidates']['final_saved'], 4)
        self.assertEqual(result['source_review_candidates']['request_state_unknown'], 4)
        self.assertEqual(result['source_review_candidates']['not_attempted'], 56)
        self.assertEqual(result['missing_final_answers'], 60)
        self.assertEqual(result['source_review_batches']['request_state_unknown'], 1)
        self.assertEqual(sum(result['source_review_candidates'].values()), len(self.calls))
        self.assertEqual(result['source_review_pending_atoms'], 1)
        self.assertFalse(result['final_file_grid_complete'])

    def test_status_rejects_a_final_without_receipt(self):
        dest, tasks, key = self.source_plan()
        cid = key[tasks[0]['review_id']]['call_id']
        self.save(dest/(cid+'.final.json'), {'call_id': cid})
        with self.assertRaises(au.InputError): report.inventory(self.directory)

    def test_persistence_uses_only_prior_same_industry_surveys_and_keeps_zero(self):
        rows = [
            {'kind': 'survey', 'industry': 'rental', 'date': '2025-01-01', 'score': 0},
            {'kind': 'survey', 'industry': 'train', 'date': '2025-03-01', 'score': 10},
            {'kind': 'verbatim', 'industry': 'rental', 'date': '2025-04-01', 'score': 10},
            {'kind': 'survey', 'industry': 'rental', 'date': '2026-01-01', 'score': 10},
        ]
        cutoff = au.date_value('2026-01-01')
        self.assertEqual(report.persistence(rows, 'rental', cutoff), 'detractor')
        rows.append({'kind': 'survey', 'industry': 'rental', 'date': '2025-01-01', 'score': 9})
        self.assertEqual(report.persistence(rows, 'rental', cutoff), 'unknown')
        self.assertEqual(report.persistence(rows, 'intl_hotel', cutoff), 'unknown')

    def test_attitude_denominators_include_missing_invalid_and_abstentions(self):
        _, judges = vw.load_judges(self.fixture.judges, self.run)
        chosen_case = sorted(judges)[0]
        for cid, call in self.calls.items():
            if call['question_id'] != 'Q2': continue
            memory = judges[call['case']]['condition_map'][call['condition']] == 'individual_memory'
            envelope = self.fixture.response(self.run, call, self.prompts)
            if call['case'] == chosen_case and memory:
                envelope['answer']['direction'] = judges[chosen_case]['hidden_segment']
            elif not memory and call['case'] == chosen_case and call['run'] == 1:
                envelope['answer']['answer'] = 'missing required citation'
            elif memory:
                continue
            self.save(self.root/'incoming'/(cid+'.json'), envelope)
        result = report.attitude(self.directory, self.fixture.judges, model_phases_ended=True)
        m = result['metrics']['individual_memory']; b = result['metrics']['historical_tag_baseline']
        self.assertEqual(m['planned_positions'], 8); self.assertEqual(m['users'], 4)
        self.assertEqual(m['correct_positions'], 2); self.assertEqual(m['states']['missing'], 6)
        self.assertEqual(m['coverage'], .25); self.assertEqual(m['hit_given_classification'], 1)
        self.assertEqual(m['end_to_end_hit_rate'], .25)
        self.assertEqual(b['states'], {'invalid': 1, 'abstained': 7})
        self.assertEqual(result['memory_vs_simple_baselines']['last_same_industry']['paired_users'], 4)
        self.assertEqual(result['analysis_origin'], 'posthoc_descriptive')

    def test_missing_finals_remain_missing_without_claiming_prediction_failure(self):
        result = report.attitude(self.directory, self.fixture.judges, 'source-final', model_phases_ended=True)
        for label in ('individual_memory', 'historical_tag_baseline'):
            self.assertEqual(result['metrics'][label]['states'], {'missing': 8})
            self.assertIsNone(result['metrics'][label]['hit_given_classification'])

    def test_analysis_requires_end_acknowledgement_and_resolved_execution_locks(self):
        with patch.object(vw, 'load_judges') as hidden:
            with self.assertRaises(au.InputError): report.attitude(self.directory, self.fixture.judges)
        hidden.assert_not_called()
        (self.directory/'.plan-trial.lock').touch()
        with self.assertRaises(au.InputError): report.attitude(self.directory, self.fixture.judges, model_phases_ended=True)


if __name__ == '__main__': unittest.main()
