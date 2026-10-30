"""Synthetic contract tests, not model-semantic validation."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import scope_review as sr
import atomic_protocol as p
import authentic_user as au

class ScopeReviewTests(unittest.TestCase):
    def setUp(self):
        self.evidence=[{'id':'E001','kind':'verbatim','date':'2025-02-01','text':'接驳很准时，车内很干净。'},{'id':'E002','kind':'verbatim','date':'2025-03-02','text':'仅作未选字段测试的合成内容。'}]
        self.atom={'kind':'conditional_forecast','text':'如果本次接驳不准时，可能不愿推荐。','anchors':[{'ref':'F001','quote':'接驳很准时'}],'condition':'topic_worsens','confidence':'low'}
        self.wire={'protocol_version':4,'facts':[],'atoms':[copy.deepcopy(self.atom)],'direction':'detractor','direction_atom':0,'unknowns':['no_observed_outcome']}
    def review(self, roles=None):
        return {'review_version':3,'evidence_sha256':sr.digest(self.evidence),'wire_sha256':sr.digest(self.wire),'items':[{'atom_index':i,'clauses':[{'clause_index':j,'role':roles[i][j] if roles else 'future_condition' if j==0 else 'future_consequence','premise':'grounded','scope':'within_source','inference':'bounded_hypothesis','source_refs':[a['ref'] for a in atom['anchors']],'issue':'none','problem_span':'','reason':'Synthetic role fixture, not independent semantic evidence.'} for j,_ in enumerate(sr.prior.clauses(atom['text']))]} for i,atom in enumerate(self.wire['atoms'])]}
    def test_forward_negative_condition_is_not_rejected_by_polarity_or_transition_word(self):
        for text in ('如果本次接驳不准时，可能转为观望。','如果本次接驳准时度改善，可能愿意推荐。'):
            with self.subTest(text=text):
                self.wire['atoms'][0]['text']=text
                self.assertEqual(sr.apply(self.evidence,self.wire,self.review())['atoms'],self.wire['atoms'])
    def test_boundary_policy_withdraws_whole_mixed_atom_without_marking_other_atoms_bad(self):
        self.wire['atoms'].append({'kind':'topic_hypothesis','text':'可能关注接驳安排，但所有记录都没有赔付信息。','anchors':[{'ref':'F001','quote':'接驳很准时'}],'condition':'none','confidence':'low'})
        review=self.review([['future_condition','future_consequence'],['topic_hypothesis','evidence_boundary']]);errors=[];policy=[]
        result=sr.apply(self.evidence,self.wire,review,errors,policy)
        self.assertEqual(errors,[]);self.assertEqual([r['atom_index'] for r in policy],[1]);self.assertEqual(result['atoms'],[self.atom]);self.assertEqual(result['direction'],'detractor')
        self.assertIn('source_scope_boundary',result['unknowns']);self.assertNotIn('review_withdrawal',result['unknowns'])
        self.assertNotIn('所有记录都没有',p.render(self.evidence,result)['answer'])
    def test_invalid_role_is_pending_without_silent_semantic_rejection(self):
        review=self.review();review['items'][0]['clauses'][0]['role']='anything';errors=[];policy=[]
        result=sr.apply(self.evidence,self.wire,review,errors,policy)
        self.assertEqual(result['atoms'],[]);self.assertEqual(policy,[]);self.assertEqual(errors[0]['status'],'review_pending');self.assertIn('review_pending',result['unknowns'])
    def test_future_clause_cannot_be_certified_as_observed_history(self):
        review=self.review();review['items'][0]['clauses'][1]['inference']='faithful_summary'
        with self.assertRaises(p.ProtocolError):sr.apply(self.evidence,self.wire,review)
    def test_wrong_attribute_is_not_rescued_by_hypothesis_role(self):
        review=self.review();c=review['items'][0]['clauses'][0];c.update(premise='unsupported',scope='expanded',inference='overclaim',issue='unsupported_detail',problem_span='本次接驳不准时')
        self.assertEqual(sr.apply(self.evidence,self.wire,review)['atoms'],[])
    def test_unselected_full_evidence_stays_local_and_scope_is_explicit(self):
        payload=sr.outbound_task(self.evidence,self.wire)
        self.assertNotIn('evidence',payload);self.assertNotIn('未选字段',json.dumps(payload,ensure_ascii=False));self.assertEqual(payload['review_protocol'],sr.NAME)
    def test_scope_boundary_does_not_bypass_missing_clause_coverage(self):
        review=self.review();review['items'][0]['clauses'][0]['role']='evidence_boundary';review['items'][0]['clauses'].pop()
        errors=[];policy=[];result=sr.apply(self.evidence,self.wire,review,errors,policy)
        self.assertEqual(policy,[]);self.assertEqual(len(errors),1);self.assertEqual(result['direction'],'unknown')
    def test_host_cli_preserves_audit_and_selected_only_prompt(self):
        root=Path(__file__).resolve().parents[1];bundle=au.prepare(root/'examples/profiles','demo-rich','酒店退改和价格透明，你更在意什么？',cutoff='2026-01-01',industry='domestic_hotel')
        book=sr.prior.sr.lookup(bundle['evidence']);selected=next(v for v in book.values() if v.get('field')=='text');unselected=next(v for v in book.values() if v.get('field')=='text' and v['ref']!=selected['ref'])
        self.evidence=bundle['evidence'];self.wire['atoms'][0]['anchors']=[{'ref':selected['ref'],'quote':selected['value']}]
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);(d/'bundle.json').write_text(json.dumps(bundle,ensure_ascii=False));(d/'answer.json').write_text(json.dumps({'bundle_sha256':bundle['bundle_sha256'],'answer_mode':'simulation','wire_answer':self.wire},ensure_ascii=False));(d/'review.json').write_text(json.dumps(self.review(),ensure_ascii=False))
            base=['scope_review.py','prompt','--bundle',str(d/'bundle.json'),'--answer',str(d/'answer.json'),'--output',str(d/'prompt.txt')]
            with patch.object(sys,'argv',base):self.assertEqual(sr.main(),0)
            prompt=(d/'prompt.txt').read_text();self.assertNotIn(unselected['value'],prompt)
            base[1]='finalize';base[-1]=str(d/'final.json');base+=['--review',str(d/'review.json'),'--audit-output',str(d/'audit.json')]
            with patch.object(sys,'argv',base):self.assertEqual(sr.main(),0)
            self.assertTrue(json.loads((d/'audit.json').read_text())['all_reviews_valid']);self.assertEqual(json.loads((d/'audit.json').read_text())['policy_withdrawals'],[])

if __name__=='__main__':unittest.main()
