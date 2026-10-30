"""Synthetic behavior checks for complete clause review and precise withdrawal."""
import copy
import sys
import unittest
import json
import tempfile
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atomic_protocol as p
import clause_review as cr

class ClauseReviewTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'id':'E001','kind':'verbatim','date':'2025-02-01','text':'车辆交接步骤很省心。'},{'id':'E002','kind':'verbatim','date':'2025-03-01','text':'床上用品有明显灰尘。'},{'id':'E003','kind':'historical_tag_summary','tag':'网络信号','count':2}]
        self.atom={'kind':'conditional_forecast','text':'如果车辆交接再次省心，可能更愿意使用。','anchors':[{'ref':'F001','quote':'车辆交接步骤很省心'}],'condition':'similar_experience','confidence':'low'}
        self.wire={'protocol_version':4,'facts':[],'atoms':[copy.deepcopy(self.atom)],'direction':'promoter','direction_atom':0,'unknowns':['no_observed_outcome']}
    def review(self):
        return {'review_version':2,'wire_sha256':cr.digest(self.wire),'evidence_sha256':cr.digest(self.rows),'items':[{'atom_index':i,'clauses':[{'clause_index':j,'premise':'grounded','scope':'within_source','inference':'faithful_summary' if a['kind']=='source_summary' else 'bounded_hypothesis','source_refs':list(dict.fromkeys(x['ref'] for x in a['anchors'])),'issue':'none','problem_span':'','reason':'Synthetic grounded premise and bounded interpretation.'} for j,_ in enumerate(cr.clauses(a['text']))]} for i,a in enumerate(self.wire['atoms'])]}
    def test_complete_clause_partition_and_no_candidate_mutation(self):
        before=copy.deepcopy(self.wire)
        task=cr.task(self.rows,self.wire)
        self.assertEqual(''.join(c['text'] for c in task['atom_bindings'][0]['clauses']),self.atom['text'])
        self.assertFalse(task['atom_bindings'][0]['future_outcome_observation_required'])
        self.assertEqual(cr.apply(self.rows,self.wire,self.review()),before)
        self.assertEqual(self.wire,before)
    def test_unselected_fields_are_not_transmitted_and_dates_are_provenance(self):
        task=cr.task(self.rows,self.wire)
        self.assertEqual([s['ref'] for s in task['source_fields']],['F001'])
        self.assertEqual(task['source_fields'][0]['recorded_date'],'2025-02-01')
        self.assertNotIn('灰尘',str(task['source_fields']))
        self.assertNotIn('灰尘',json.dumps(cr.outbound_task(self.rows,self.wire),ensure_ascii=False))
    def test_host_cli_prompt_excludes_unselected_full_evidence(self):
        import authentic_user as au
        root=Path(__file__).resolve().parents[1]
        bundle=au.prepare(root/'examples/profiles','demo-rich','酒店退改和价格透明，你更在意什么？',cutoff='2026-01-01',industry='domestic_hotel')
        book=cr.sr.lookup(bundle['evidence']);selected=next(x for x in book.values() if x.get('field')=='text');unselected=next(x for x in book.values() if x.get('field')=='text' and x['ref']!=selected['ref'])
        wire=copy.deepcopy(self.wire);wire.update(facts=[],direction='unknown',direction_atom=None)
        wire['atoms'][0].update(kind='topic_hypothesis',text='可能关注该记录涉及的体验。',condition='none',anchors=[{'ref':selected['ref'],'quote':selected['value']}])
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);(d/'bundle.json').write_text(json.dumps(bundle,ensure_ascii=False));(d/'answer.json').write_text(json.dumps({'bundle_sha256':bundle['bundle_sha256'],'answer_mode':'simulation','wire_answer':wire},ensure_ascii=False))
            with patch.object(sys,'argv',['clause_review.py','prompt','--bundle',str(d/'bundle.json'),'--answer',str(d/'answer.json'),'--output',str(d/'prompt.txt')]):self.assertEqual(cr.main(),0)
            text=(d/'prompt.txt').read_text();payload=json.loads(text.rsplit('\n任务：',1)[1])
            self.assertNotIn('evidence',payload);self.assertNotIn(unselected['value'],text)
            self.assertEqual([v['ref'] for v in payload['source_fields']],[selected['ref']])
    def test_premises_do_not_need_duplicate_facts_selection(self):
        self.assertEqual(self.wire['facts'],[])
        self.assertEqual(cr.apply(self.rows,self.wire,self.review())['atoms'],[self.atom])
    def test_history_markers_are_review_hints_with_explicit_source_types(self):
        self.wire['atoms'][0].update(text='如果网络依旧稳定，可能愿意使用。',anchors=[{'ref':'F005','quote':'网络信号'}],condition='topic_improves')
        self.wire.update(direction='unknown',direction_atom=None)
        task=cr.task(self.rows,self.wire);binding=task['atom_bindings'][0]
        self.assertEqual(binding['selected_field_types'],['tag'])
        self.assertEqual(binding['clauses'][0]['history_relation_terms'],['依旧'])
        # A cue is not semantic certification; the original valid wire is unchanged.
        p.validate(self.rows,self.wire)
    def test_every_clause_coverage_hash_and_atom_identity_are_required(self):
        for variant in ('clause','hash','atom'):
            review=self.review()
            if variant=='clause':review['items'][0]['clauses'].pop()
            elif variant=='hash':review['wire_sha256']='other'
            else:review['items'][0]['atom_index']=5
            with self.subTest(variant=variant),self.assertRaises(p.ProtocolError):cr.apply(self.rows,self.wire,review)
    def test_partial_supported_compound_cannot_hide_unbound_object(self):
        self.wire['atoms'][0].update(kind='topic_hypothesis',text='页面照片是否一致、床上用品是否整洁，可能影响体验。',anchors=[{'ref':'F003','quote':'床上用品有明显灰尘'}],condition='none')
        self.wire.update(direction='unknown',direction_atom=None)
        review=self.review();first=review['items'][0]['clauses'][0]
        first.update(premise='unsupported',scope='expanded',issue='missing_premise',problem_span='页面照片是否一致',source_refs=[],reason='Bedding premise does not support photographs.')
        self.assertEqual(cr.apply(self.rows,self.wire,review)['atoms'],[])
    def test_presupposition_rejection_does_not_reject_independent_topic(self):
        self.wire['atoms'].append(copy.deepcopy(self.atom))
        self.wire['atoms'][0].update(text='如果网络仍然很差，可能暂缓使用。',anchors=[{'ref':'F005','quote':'网络信号'}],condition='topic_worsens')
        self.wire['direction_atom']=1
        review=self.review();review['items'][0]['clauses'][0].update(premise='unsupported',scope='expanded',issue='unsupported_presupposition',problem_span='仍然很差',reason='Neutral label does not establish earlier poor signal.')
        out=cr.apply(self.rows,self.wire,review)
        self.assertEqual(out['atoms'],[self.wire['atoms'][1]]);self.assertEqual(out['direction_atom'],0)
    def test_uncertain_review_is_not_positive_support(self):
        review=self.review();review['items'][0]['clauses'][0].update(premise='uncertain',issue='missing_premise',problem_span='车辆交接',reason='Synthetic uncertainty.')
        out=cr.apply(self.rows,self.wire,review)
        self.assertEqual(out['atoms'],[]);self.assertEqual(out['direction'],'unknown')
    def test_contract_error_is_pending_and_does_not_hide_other_atoms(self):
        self.wire['atoms'].append(copy.deepcopy(self.atom));self.wire['direction_atom']=1
        review=self.review();review['items'][0]['clauses'].pop();errors=[]
        out=cr.apply(self.rows,self.wire,review,contract_errors=errors)
        self.assertEqual(errors[0]['status'],'review_pending');self.assertEqual(out['atoms'],[self.atom]);self.assertEqual(out['direction_atom'],0)
        self.assertIn('review_pending',out['unknowns']);self.assertNotIn('review_withdrawal',out['unknowns'])
    def test_problem_span_and_references_cannot_be_borrowed_from_other_clause(self):
        review=self.review();review['items'][0]['clauses'][0].update(premise='unsupported',issue='missing_premise',problem_span='可能更愿意使用')
        with self.assertRaises(p.ProtocolError):cr.apply(self.rows,self.wire,review)
        review=self.review();review['items'][0]['clauses'][0]['source_refs']=['F003']
        with self.assertRaises(p.ProtocolError):cr.apply(self.rows,self.wire,review)
    def test_incomplete_or_wrong_type_acceptance_is_not_silently_accepted(self):
        for key,value in [('issue','scope_expansion'),('problem_span','车辆交接'),('source_refs',[]),('inference','overclaim')]:
            review=self.review();review['items'][0]['clauses'][0][key]=value
            with self.subTest(key=key),self.assertRaises(p.ProtocolError):cr.apply(self.rows,self.wire,review)
        self.wire['atoms'][0].update(kind='source_summary',text='旧记录说交接步骤省心。',condition='none')
        self.wire.update(direction='unknown',direction_atom=None)
        review=self.review();review['items'][0]['clauses'][0]['inference']='bounded_hypothesis'
        with self.assertRaises(p.ProtocolError):cr.apply(self.rows,self.wire,review)
    def test_temporal_summary_has_selected_source_dates_without_same_event_claim(self):
        self.rows=[{'id':'E001','kind':'survey','date':'2025-01-02','score':8},{'id':'E002','kind':'survey','date':'2025-04-02','score':4}]
        self.wire.update(direction='unknown',direction_atom=None)
        self.wire['atoms'][0].update(kind='source_summary',text='两次记录的分数先为8后为4。',anchors=[{'ref':'F001','quote':'8'},{'ref':'F003','quote':'4'}],condition='none')
        task=cr.task(self.rows,self.wire)
        self.assertEqual([f['recorded_date'] for f in task['source_fields']],['2025-01-02','2025-04-02'])
        self.assertEqual(cr.apply(self.rows,self.wire,self.review()),self.wire)
    def test_empty_atoms_review_has_no_fabricated_successful_judgment(self):
        self.wire.update(atoms=[],direction='unknown',direction_atom=None)
        self.assertEqual(cr.apply(self.rows,self.wire,self.review())['atoms'],[])

if __name__=='__main__':unittest.main()
