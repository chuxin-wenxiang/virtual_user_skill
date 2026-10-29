"""Complete mocked generation/audit lifecycle and raw review tamper detection."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import authentic_user as au,attribution_protocol as ap,validation_workflow as vw,plan_trial as pt,plan_review as pr,chatgpt_plan as cp,trial_audit
import test_validation_workflow as fm
class PlanReviewTests(unittest.TestCase):
 def test_complete_source_only_review_preserves_candidates_and_detects_tamper(self):
  self.lifecycle(False)
 def test_structural_failure_remains_rejected_in_full_denominator(self):
  self.lifecycle(True)
 def lifecycle(self,invalid):
  f=fm.ValidationWorkflowTests();f.setUp()
  try:
   root=f.root/'review-plan';root.mkdir();inputs=root/'inputs';fm.vp.reframe(f.inputs,inputs)
   manifest=au.read_object(inputs/'manifest.json');protocol=au.read_object(inputs/'protocol.json');protocol['response_protocol']='field-bound-v3';manifest['protocol_sha256']=vw.digest(protocol)
   (inputs/'protocol.json').write_text(json.dumps(protocol));(inputs/'manifest.json').write_text(json.dumps(manifest))
   config=copy.deepcopy(f.config);config.update(provider='openai-chatgpt-plan',model='synthetic-plan-model',revision='provider-alias:synthetic',synthetic=False,parameters={'temperature':None,'top_p':None,'max_output_tokens':None})
   config['transport']={'route':cp.API+'/responses','store':False,'stream':True,'billing_policy':'subscription_only_no_paid_fallback','reasoning_effort':'low','revision_policy':'provider_alias_exploratory','max_input_characters':40000,'max_output_characters':16000,'reported_output_token_guard':4000,'concurrency':1,'automatic_retries':0,'execution_order':'paired_interleaved_v1','adapter_instructions':'synthetic','response_protocol':'field-bound-v3','output_schema_sha256':vw.digest(ap.schema()),'execution_sources_sha256':{}}
   cf=root/'config.json';cf.write_text(json.dumps(config));rv=au.read_object(f.review_file);rv['inputs_manifest_sha256']=vw.digest(manifest);rf=root/'review.json';rf.write_text(json.dumps(rv));rd=root/'run';vw.freeze(inputs,cf,rf,rd);_,run,calls,_=vw.load_run(rd)
   consent=root/'consent.json';consent.write_text(json.dumps({'run_sha256':run['run_sha256'],'approved':True,'source_review_approved':True,'destination':cp.API+'/responses','subscription_only':True,'human_authorization':'synthetic fixture'}));counter=[]
   def respond(model,prompt,instructions,**kwargs):
    counter.append(1)
    body={'model':model,'instructions':instructions,'input':[{'role':'user','content':[{'type':'input_text','text':prompt}]}],'reasoning':{'effort':'low'},'store':False,'stream':True,'text':{'format':{'type':'json_schema','name':'authentic_user_trial','strict':True,'schema':kwargs['schema']}}}
    if instructions=='synthetic':wire={'protocol_version':3,'facts':[],'inferences':[],'direction':'unknown','direction_inference':None,'unknowns':['synthetic unknown']}
    if instructions=='synthetic' and invalid and len(counter)==1:wire['direction']='promoter'
    if instructions!='synthetic':wire={'reviews':[{'review_id':t['review_id'],'wire_sha256':t['wire_sha256'],'evidence_sha256':t['evidence_sha256'],'items':[]} for t in json.loads(prompt)['tasks']]}
    return {'text':json.dumps(wire),'response':{'id':'synthetic-'+str(len(counter)),'status':'completed','model':model,'usage':{'input_tokens':100,'output_tokens':50}},'request_body_sha256':hashlib.sha256(json.dumps(body,ensure_ascii=False).encode()).hexdigest(),'paid_fallback_used':False}
   client=Mock();client.respond.side_effect=respond
   with patch.object(cp,'PlanClient',return_value=client),patch('builtins.print'):
    self.assertEqual(pt.execute(rd,'unused',consent)['status'],'completed_with_structural_failures' if invalid else 'completed');self.assertEqual(pr.execute(rd,'unused',consent)['status'],'completed')
   a=pr.audit(rd);self.assertEqual(a['structural_rejections'],int(invalid));self.assertEqual(a['reviewed_answers'],len(calls)-int(invalid));self.assertEqual(a['completed_batches'],len(calls)//4);self.assertEqual(len(counter),len(calls)*5//4)
   receipt=next((root/'source-review').glob('*.receipt.json'));receipt.write_text(receipt.read_text()+' ')
   with self.assertRaises(au.InputError):pr.audit(rd)
  finally:f.tearDown()
