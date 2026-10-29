"""Observable provenance, abstention and new target selection invariants."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import authentic_user as au,attribution_protocol as p,attribution_review as ar,validation_prep as vp

class AttributionTests(unittest.TestCase):
 def setUp(self):
  self.rows=[{'id':'E001','kind':'survey','score':8,'tags':['服务'],'date':'2025-01-01'}, {'id':'E002','kind':'verbatim','text':'退款当天到账，但服务是否及时未知。','date':'2025-01-01'}]
  self.w={'protocol_version':3,'facts':[{'evidence_id':'E002','field':'text'}],'inferences':[{'text':'若退款更慢，可能降低评价。','premises':[{'evidence_id':'E002','field':'text'}],'scope':'future_condition','confidence':'low','mechanism':'暂无可区分机制','alternative':'可能由未记录因素影响','update_condition':'新的实际反馈'}],'direction':'passive','direction_inference':0,'unknowns':[]}
 def review(self,verdict='supported'):
  return {'wire_sha256':ar.digest(self.w),'evidence_sha256':ar.digest(self.rows),'items':[{'inference_index':0,'verdict':verdict,'reason':'synthetic source-only review'}]}
 def test_full_source_field_shown_and_wrong_field_rejected(self):
  r=p.render(self.rows,self.w);self.assertIn('退款当天到账，但服务是否及时未知。',r['answer']);self.assertEqual(r['claims'][-1]['premise_fields'],self.w['inferences'][0]['premises'])
  self.w['inferences'][0]['premises'][0]['field']='tag'
  with self.assertRaises(p.ProtocolError):p.render(self.rows,self.w)
 def test_topic_labels_cannot_certify_experience_or_predict_direction(self):
  self.w['inferences'][0]['premises']=[{'evidence_id':'E001','field':'tags'}]
  with self.assertRaises(p.ProtocolError):p.render(self.rows,self.w)
  self.w.update(direction='unknown',direction_inference=None);self.w['inferences'][0]['scope']='self_report_summary'
  with self.assertRaises(p.ProtocolError):p.render(self.rows,self.w)
  self.w['inferences'][0]['scope']='topic_hypothesis';p.render(self.rows,self.w)
 def test_specific_direction_binding_cannot_reference_unrelated_or_missing_inference(self):
  self.w['direction_inference']=1
  with self.assertRaises(p.ProtocolError):p.render(self.rows,self.w)
 def test_ambiguous_or_unsupported_removed_not_rewritten(self):
  before=copy.deepcopy(self.w)
  for verdict in ['ambiguous','unsupported']:
   final=ar.apply(self.rows,self.w,self.review(verdict));self.assertEqual(final['inferences'],[]);self.assertEqual(final['direction'],'unknown');self.assertTrue(final['unknowns']);self.assertEqual(self.w,before)
 def test_supported_kept_exactly_and_reordered_direction_binding(self):
  self.assertEqual(ar.apply(self.rows,self.w,self.review()),self.w)
  self.w['inferences'].append(copy.deepcopy(self.w['inferences'][0]));self.w['direction_inference']=1
  review=self.review();review['items'].append({'inference_index':1,'verdict':'supported','reason':'supported source'});review['items'][0]['verdict']='ambiguous'
  final=ar.apply(self.rows,self.w,review);self.assertEqual(final['direction_inference'],0);self.assertEqual(len(final['inferences']),1)
 def test_review_binding_and_missing_duplicate_rows_fail(self):
  for change in ('wire','source','missing','duplicate'):
   review=self.review()
   if change=='wire':review['wire_sha256']='other'
   elif change=='source':review['evidence_sha256']='other'
   elif change=='missing':review['items']=[]
   else:review['items']*=2
   with self.assertRaises(p.ProtocolError):ar.apply(self.rows,self.w,review)
 def test_invalid_source_text_cannot_be_used_as_inference_premise(self):
  self.rows[1]['text']='����'
  with self.assertRaises(p.ProtocolError):p.render(self.rows,self.w)
 def test_old_bundle_capability_semantics_retained(self):
  self.assertIn('2027.0.0-alpha.5',au.SUPPORTED_BUNDLE_VERSIONS)
 def test_fresh_target_gap_empty_duplicate_and_distinct_content(self):
  records=[{'kind':'verbatim','industry':'rental','date':'2025-01-01','text':'取还很方便，车辆干净整洁。'}, {'kind':'verbatim','industry':'rental','date':'2025-02-01','text':'价格优惠，费用清楚。'}]
  c={'industry':'rental','holdout':{'date':'2025-03-01','industry':'rental','text':'联系客服以后仍没有拿到取车地点。'}}
  self.assertTrue(vp.fresh_target(c,records));c['holdout']['date']='2025-02-02';self.assertFalse(vp.fresh_target(c,records));c['holdout']['date']='2025-03-01';c['holdout']['text']=records[0]['text'];self.assertFalse(vp.fresh_target(c,records));c['holdout']['text']='性价比：商家服务：';self.assertFalse(vp.fresh_target(c,records))

 def test_generic_multilingual_praise_is_not_a_reason_target(self):
  self.assertFalse(vp.target_has_reason_signal('Very good! 很好，很不错！'))
  self.assertFalse(vp.target_has_reason_signal('Very nice! 非常满意，五星好评！'))
  self.assertTrue(vp.target_has_reason_signal('很好，服务人员解释了押金退还时间。'))
