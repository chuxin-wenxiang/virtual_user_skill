"""Regression cases for attribution failures, bounded forecasts and review contracts."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import atomic_protocol as p
import atomic_review as ar
import source_registry as sr
import validation_workflow as vw

class AtomicTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {'id': 'E001', 'kind': 'survey', 'tags': ['价格', '取还'], 'score': 9, 'date': '2025-01-01'},
            {'id': 'E002', 'kind': 'verbatim', 'text': '价格清楚。没有说取还车很好，也未提赔付。', 'date': '2025-01-01'},
            {'id': 'E003', 'kind': 'survey', 'tags': ['取还'], 'score': 8, 'date': '2025-03-01'},
            {'id': 'E004', 'kind': 'verbatim', 'text': '网络是否改善还不知道。', 'date': '2025-03-01'},
        ]
        self.book = sr.lookup(self.rows)
        self.ref = next(k for k,v in self.book.items() if v.get('evidence_id') == 'E002' and v.get('field') == 'text')
        self.atom = {'kind': 'conditional_forecast', 'text': '如果价格仍然清楚，可能保持较积极的评价。', 'condition': 'similar_experience', 'confidence': 'low', 'anchors': [{'ref': self.ref, 'quote': '价格清楚。'}]}
        self.wire = {'protocol_version': 4, 'facts': ['T001'], 'atoms': [copy.deepcopy(self.atom)], 'direction': 'promoter', 'direction_atom': 0, 'unknowns': ['no_observed_outcome']}

    def review(self):
        return {'wire_sha256': ar.digest(self.wire), 'evidence_sha256': ar.digest(self.rows), 'items': [
            {'atom_index': i, 'verdict': 'bounded_hypothesis', 'issue': 'none', 'used_refs': list(dict.fromkeys(a['ref'] for a in atom['anchors'])), 'missing_refs': [], 'problem_span': '', 'reason': 'Explicit condition; source topic matches, no personal causal claim.'}
            for i, atom in enumerate(self.wire['atoms'])]}

    def test_complete_counts_not_subset_or_independent_event_claim(self):
        statistic = self.book['T001']
        self.assertEqual([(v['tag'], v['count']) for v in statistic['values']], [('取还', 2), ('价格', 1)])
        self.assertIn('not independent events', statistic['unit'])
        self.assertEqual(statistic['values'][0]['evidence_ids'], ['E001', 'E003'])

    def test_source_type_errors_and_nonexact_quotes_rejected(self):
        for ref, quote in [('E002', '价格清楚。'), ('F999', '价格清楚。'), (self.ref, '价格很便宜')]:
            w = copy.deepcopy(self.wire); w['atoms'][0]['anchors'] = [{'ref':ref,'quote':quote}]
            with self.subTest(ref=ref, quote=quote), self.assertRaises(p.ProtocolError): p.render(self.rows,w)

    def test_uncited_topic_is_flagged_then_withdrawn_by_semantic_review(self):
        self.wire['atoms'][0]['text'] = '如果网络改善，可能更愿意推荐。'
        task = ar.task(self.rows,self.wire)
        self.assertEqual(task['lexical_review_hints'][0]['unmatched_topic_keywords'],['network'])
        ref = next(k for k,v in self.book.items() if v.get('evidence_id')=='E004' and v.get('field')=='text')
        review = self.review()
        review['items'][0].update(verdict='unsupported',issue='missing_premise',missing_refs=[ref],problem_span='网络改善')
        final = ar.apply(self.rows,self.wire,review)
        self.assertEqual(final['atoms'],[]); self.assertEqual(final['direction'],'unknown')

    def test_keyword_count_does_not_certify_semantics_or_reject_compound_terms(self):
        rows=[{'id':'E001','kind':'verbatim','text':'退订费用合理，信用住服务履行顺利。'}]
        for text in ['如果退订费用合理，可能更满意。','如果信用住服务继续顺利，可能更满意。']:
            wire=copy.deepcopy(self.wire);wire['facts']=[]
            wire['atoms'][0].update(text=text,anchors=[{'ref':'F001','quote':rows[0]['text']}])
            self.assertGreater(len(ar.task(rows,wire)['lexical_review_hints'][0]['multiple_topic_keywords']),1)
            p.render(rows,wire)

    def test_free_frequency_comparison_remains_script_rendered_only(self):
        self.wire['atoms'][0]['text']='如果价格仍然清楚，可能仍将价格视作最看重的问题。'
        with self.assertRaises(p.ProtocolError):p.render(self.rows,self.wire)

    def test_distinct_snippets_share_one_field_and_exact_duplicate_is_rejected(self):
        atom=self.wire['atoms'][0]
        atom['anchors'].append({'ref':self.ref,'quote':'没有说取还车很好'})
        task=ar.task(self.rows,self.wire)
        self.assertEqual(len(task['selected_fields'][0]),1)
        self.assertEqual(ar.apply(self.rows,self.wire,self.review()),self.wire)
        atom['anchors'].append(copy.deepcopy(atom['anchors'][0]))
        with self.assertRaisesRegex(p.ProtocolError,'Duplicate exact'):p.render(self.rows,self.wire)

    def test_synonym_hint_is_not_a_missing_premise_verdict(self):
        rows=[{'id':'E001','kind':'verbatim','text':'接待员协助细心又耐心。'}]
        wire=copy.deepcopy(self.wire);wire['facts']=[]
        wire['atoms'][0].update(text='如果工作人员服务依旧耐心，可能更满意。',anchors=[{'ref':'F001','quote':'接待员协助细心又耐心'}])
        self.assertEqual(ar.task(rows,wire)['lexical_review_hints'][0]['unmatched_topic_keywords'],['service'])
        review={'wire_sha256':ar.digest(wire),'evidence_sha256':ar.digest(rows),'items':[{'atom_index':0,'verdict':'bounded_hypothesis','issue':'none','used_refs':['F001'],'missing_refs':[],'problem_span':'','reason':'Staff attentiveness supports the service paraphrase in full context.'}]}
        self.assertEqual(ar.apply(rows,wire,review),wire)

    def test_negation_context_is_preserved_and_cannot_be_certified_by_script(self):
        self.wire['atoms'][0]['anchors'][0]['quote'] = '取还车很好'
        rendered = p.render(self.rows,self.wire)
        self.assertIn('没有说取还车很好', rendered['answer'])
        # A literal substring alone never proves semantic entailment.
        self.assertEqual(ar.task(self.rows,self.wire)['selected_fields'][0][0]['value'], self.rows[1]['text'])

    def test_bounded_forecast_kept_without_claiming_proved_causality(self):
        before = copy.deepcopy(self.wire)
        self.assertEqual(ar.apply(self.rows,self.wire,self.review()), before)
        self.assertIn('尚无个人因果证明', p.render(self.rows,self.wire)['answer'])

    def test_remove_only_bad_atom_and_rebind_direction(self):
        self.wire['atoms'].append(copy.deepcopy(self.atom)); self.wire['direction_atom'] = 1
        review = self.review(); review['items'][0].update(verdict='ambiguous', issue='scope_expansion', problem_span='保持较积极的评价')
        final = ar.apply(self.rows,self.wire,review)
        self.assertEqual(final['atoms'], [self.wire['atoms'][1]])
        self.assertEqual(final['direction_atom'], 0)
        self.assertEqual(len(self.wire['atoms']), 2)

    def test_false_missing_reference_is_quarantined_not_accepted(self):
        self.wire['atoms'].append(copy.deepcopy(self.atom)); self.wire['direction_atom'] = 1
        review = self.review(); review['items'][0].update(verdict='ambiguous', issue='missing_premise', missing_refs=[self.ref], problem_span='价格')
        with self.assertRaisesRegex(p.ProtocolError,'already selected'): ar.apply(self.rows,self.wire,review)
        errors = []; final = ar.apply(self.rows,self.wire,review,contract_errors=errors)
        self.assertEqual(len(errors),1); self.assertEqual(len(final['atoms']),1); self.assertEqual(final['direction_atom'],0)

    def test_missing_review_coverage_hash_and_wrong_standard_fail(self):
        for change in ('hash','coverage','standard','span','used'):
            review = self.review()
            if change == 'hash': review['wire_sha256'] = 'different'
            elif change == 'coverage': review['items'] = []
            elif change == 'standard': review['items'][0]['verdict'] = 'supported'
            elif change == 'used': review['items'][0]['used_refs'] = []
            else: review['items'][0].update(verdict='ambiguous',issue='unsupported_detail',problem_span='不存在的片段')
            with self.subTest(change=change), self.assertRaises(p.ProtocolError): ar.apply(self.rows,self.wire,review)

    def test_labels_cannot_predict_attitude_or_certify_self_report(self):
        ref = next(k for k,v in self.book.items() if v.get('field') == 'tags')
        self.wire['atoms'][0]['anchors'] = [{'ref':ref, 'quote':'价格'}]
        with self.assertRaises(p.ProtocolError): p.render(self.rows,self.wire)
        self.wire.update(direction='unknown',direction_atom=None)
        self.wire['atoms'][0].update(kind='source_summary',condition='none')
        with self.assertRaises(p.ProtocolError): p.render(self.rows,self.wire)

    def test_render_tampering_and_capability_limits_fail(self):
        answer = p.render(self.rows,self.wire); payload = {'user_context': {'evidence':self.rows}}
        vw.check_common_answer(payload, answer)
        answer['answer'] += '\nAdded assertion'
        with self.assertRaises(Exception): vw.check_common_answer(payload, answer)
        with self.assertRaises(p.ProtocolError): p.render(self.rows,self.wire,'facts_only')

    def test_duplicate_evidence_and_unknown_fact_fail(self):
        with self.assertRaises(p.ProtocolError): sr.catalogue(self.rows + [self.rows[0]])
        self.wire['facts'] = ['T999']
        with self.assertRaises(p.ProtocolError): p.render(self.rows,self.wire)


class PrecheckTests(unittest.TestCase):
    setUp = AtomicTests.setUp
    def test_structural_atom_withdrawal_preserves_unrelated_forecast_and_raw(self):
        import plan_review as pr
        original = copy.deepcopy(self.wire)
        original['facts'].append('F999')
        tag_ref = next(k for k,v in self.book.items() if v.get('field')=='tags')
        bad = {'kind':'source_summary','text':'价格和取还属于已发生满意经历。','anchors':[{'ref':tag_ref,'quote':'价格'}],'confidence':'low','condition':'none'}
        original['atoms'].insert(0,bad);original['direction_atom']=1
        before = copy.deepcopy(original)
        final, log = pr.precheck(self.rows,original)
        self.assertEqual(original,before)
        self.assertEqual(final['atoms'],[self.atom]);self.assertEqual(final['direction_atom'],0)
        self.assertEqual(log['kept_atom_indices'],[1]);self.assertEqual(len(log['atom_errors']),1);self.assertEqual(len(log['fact_errors']),1)
        self.assertEqual(final['facts'],['T001']);p.validate(self.rows,final)


    def test_host_precheck_is_bound_to_bundle_and_keeps_provenance(self):
        import plan_review as pr
        import authentic_user as au
        root=Path(__file__).resolve().parents[1]
        bundle=au.prepare(root/'examples/profiles','demo-rich','酒店退改和价格透明，你更在意什么？',cutoff='2026-01-01',industry='domestic_hotel')
        raw=au.read_object(root/'examples/answer-atomic-demo.json')
        raw['wire_answer']['facts'].append('F999')
        before=copy.deepcopy(raw)
        result, log=pr.precheck_bundle(bundle,raw)
        self.assertEqual(raw,before);self.assertTrue(au.check_answer(bundle,result)['ok'])
        self.assertEqual(len(log['precheck']['fact_errors']),1)
        self.assertEqual(log['original_wire_sha256'],ar.digest(raw['wire_answer']))
        raw['bundle_sha256']='different'
        with self.assertRaises(au.InputError):pr.precheck_bundle(bundle,raw)

if __name__ == '__main__': unittest.main()
