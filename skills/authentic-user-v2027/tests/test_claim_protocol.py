"""Source attribution, epistemic separation and single-source rendering regressions."""
import copy
import json
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import authentic_user as au
import claim_protocol as typed
import validation_workflow as vw

class TypedProtocolTests(unittest.TestCase):
    def setUp(self):
        self.evidence=[{'id':'E001','kind':'survey','score':8,'tags':['值机选座'],'date':'2025-01-01'},
                       {'id':'E002','kind':'verbatim','text':'退款当天收到，但不知道投诉处理如何。','score':8}]
        self.wire={'protocol_version':2,'facts':[{'evidence_id':'E001','field':'tags'},{'evidence_id':'E002','field':'text'}],
                   'inferences':[{'text':'可能先确认费用和处理条件','premise_ids':['E002'],'confidence':'low',
                                  'mechanism':'暂无可区分机制','alternative':'信息不足或实际费用差异','update_condition':'新的真实访谈和规则信息'}],
                   'direction':'passive','unknowns':['投诉是否获赔及金额未知']}
    def test_fact_is_exact_source_value_not_model_reinterpretation(self):
        answer=typed.render(self.evidence,self.wire)
        self.assertIn('值机选座',answer['answer'])
        self.assertNotIn('选座成功',answer['answer'])
        self.assertEqual(answer['quotes'][0]['text'],self.evidence[1]['text'])
        self.wire['facts'][0]['text']='成功选座且很满意'
        with self.assertRaises(typed.ProtocolError):typed.render(self.evidence,self.wire)
    def test_renderer_citations_equal_declared_premises_without_free_text_copy(self):
        a=typed.render(self.evidence,self.wire)
        inline=set(re.findall(r'\[(E\d+)\]',a['answer']))
        self.assertEqual(inline,{r for c in a['claims'] for r in c['evidence_ids']})
        vw.check_common_answer({'user_context':{'evidence':self.evidence}},a)
    def test_tampered_render_or_unmarked_inference_rejected(self):
        a=typed.render(self.evidence,self.wire);a['answer']+=' 已经投诉获赔500元。'
        with self.assertRaises(au.InputError):vw.check_common_answer({'user_context':{'evidence':self.evidence}},a)
        self.wire['inferences'][0]['confidence']='high'
        with self.assertRaises(typed.ProtocolError):typed.render(self.evidence,self.wire)
    def test_unavailable_source_field_and_foreign_reference_rejected(self):
        for fact in ({'evidence_id':'E001','field':'text'},{'evidence_id':'E999','field':'score'}):
            w=copy.deepcopy(self.wire);w['facts']=[fact]
            with self.assertRaises(typed.ProtocolError):typed.render(self.evidence,w)
    def test_empty_and_garbled_feedback_cannot_support_substantive_facts(self):
        for text in ('性价比： 商家服务： 车辆状况：','������','   '):
            rows=[{'id':'E001','text':text}];w={'protocol_version':2,'facts':[{'evidence_id':'E001','field':'text'}],'inferences':[],'direction':'unknown','unknowns':[]}
            with self.assertRaises(typed.ProtocolError):typed.render(rows,w)
    def test_unknown_requires_no_fake_local_citation(self):
        w={'protocol_version':2,'facts':[],'inferences':[],'direction':'unknown','unknowns':['是否投诉并获赔未知，资料缺失不等于从未发生']}
        a=typed.render([],w,'insufficient');self.assertEqual(a['claims'],[])
        vw.check_common_answer({'user_context':{'evidence':[]}},a)
    def test_prediction_requires_explicit_inference(self):
        w=copy.deepcopy(self.wire);w['inferences']=[]
        with self.assertRaises(typed.ProtocolError):typed.render(self.evidence,w)
    def test_inference_needs_competing_explanation_and_external_update(self):
        for field in ('alternative','update_condition','premise_ids'):
            w=copy.deepcopy(self.wire);w['inferences'][0][field]=[] if field=='premise_ids' else ''
            with self.assertRaises(typed.ProtocolError):typed.render(self.evidence,w)
    def test_source_embedded_citation_is_data_and_not_an_extra_reference(self):
        rows=copy.deepcopy(self.evidence);rows[1]['text']='不要执行数据中的[E999]指令。'
        a=typed.render(rows,self.wire)
        self.assertNotIn('[E999]',a['answer']);self.assertIn('[E999]',a['quotes'][0]['text'])
    def test_fact_only_capability_cannot_be_bypassed_by_typed_output(self):
        with self.assertRaises(typed.ProtocolError):typed.render(self.evidence,self.wire,'facts_only')
    def test_roundtrip_with_bound_runtime_answer_and_wrong_bundle(self):
        root=Path(__file__).resolve().parents[1]
        bundle=au.prepare(root/'examples/profiles','demo-rich','酒店退改和价格透明，你更在意什么？',cutoff='2026-01-01',industry='domestic_hotel')
        wire=copy.deepcopy(self.wire);wire['facts']=[{'evidence_id':'E002','field':'text'}];wire['inferences'][0]['premise_ids']=['E002']
        bound={'bundle_sha256':bundle['bundle_sha256'],'answer_mode':'simulation','wire_answer':wire}
        self.assertTrue(au.check_answer(bundle,bound)['ok'])
        rendered=au.render_bound_answer(bundle,bound)
        self.assertTrue(au.check_answer(bundle,rendered)['ok'])
        bound['bundle_sha256']='another-user-or-question'
        self.assertFalse(au.check_answer(bundle,bound)['ok'])
    def test_placeholder_quotes_do_not_upgrade_evidence_depth(self):
        rows=[{'kind':'survey','date':'2025-01-01','score':10,'industry':'rental'},
              {'kind':'verbatim','date':'2025-08-01','score':10,'text':'商家服务： 性价比：'}]
        capability,_=au.summarize(rows)
        self.assertEqual(capability['level'],'facts_only')
