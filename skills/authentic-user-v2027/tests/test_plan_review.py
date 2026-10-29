"""Complete mocked generation/audit lifecycle and raw review tamper detection."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import authentic_user as au,attribution_protocol as ap,validation_workflow as vw,plan_trial as pt,plan_review as pr,chatgpt_plan as cp,trial_audit
import test_validation_workflow as fm
import atomic_protocol as atomic, source_registry as sr
class PlanReviewTests(unittest.TestCase):
 def test_complete_source_only_review_preserves_candidates_and_detects_tamper(self):
  self.lifecycle(False)
 def test_structural_failure_remains_rejected_in_full_denominator(self):
  self.lifecycle(True)
 def test_atomic_protocol_complete_lifecycle(self):
  self.lifecycle(False,"atomic-bound-v4")
 def test_global_hash_mismatch_is_rejected_without_rewriting_or_losing_other_candidates(self):
  self.lifecycle(False,"atomic-bound-v4",True)
 def test_unassignable_batch_stops_with_first_storage_index_and_no_retry(self):
  self.lifecycle(False,"atomic-bound-v4",batch_invalid=True)
 def lifecycle(self,invalid,protocol_name="field-bound-v3",review_invalid=False,batch_invalid=False):
  f=fm.ValidationWorkflowTests();f.setUp()
  try:
   root=f.root/'review-plan';root.mkdir();inputs=root/'inputs'
   if protocol_name=='atomic-bound-v4':fm.vp.build(f.fixture.profiles,inputs,root/'new-judge',per_group=1,repeats=2,response_protocol=protocol_name)
   else:fm.vp.reframe(f.inputs,inputs)
   manifest=au.read_object(inputs/'manifest.json');protocol=au.read_object(inputs/'protocol.json');protocol['response_protocol']=protocol_name;manifest['protocol_sha256']=vw.digest(protocol)
   (inputs/'protocol.json').write_text(json.dumps(protocol));(inputs/'manifest.json').write_text(json.dumps(manifest))
   config=copy.deepcopy(f.config);config.update(provider='openai-chatgpt-plan',model='synthetic-plan-model',revision='provider-alias:synthetic',synthetic=False,parameters={'temperature':None,'top_p':None,'max_output_tokens':None})
   config['transport']={'route':cp.API+'/responses','store':False,'stream':True,'billing_policy':'subscription_only_no_paid_fallback','reasoning_effort':'low','revision_policy':'provider_alias_exploratory','max_input_characters':40000,'max_output_characters':16000,'reported_output_token_guard':4000,'concurrency':1,'automatic_retries':0,'execution_order':'paired_interleaved_v1','adapter_instructions':'synthetic','response_protocol':protocol_name,'output_schema_sha256':vw.digest(atomic.schema() if protocol_name=='atomic-bound-v4' else ap.schema()),'execution_sources_sha256':{}}
   cf=root/'config.json';cf.write_text(json.dumps(config));rv=au.read_object(f.review_file);rv['inputs_manifest_sha256']=vw.digest(manifest);rf=root/'review.json';rf.write_text(json.dumps(rv));rd=root/'run';vw.freeze(inputs,cf,rf,rd);_,run,calls,_=vw.load_run(rd)
   consent=root/'consent.json';consent.write_text(json.dumps({'run_sha256':run['run_sha256'],'approved':True,'source_review_approved':True,'destination':cp.API+'/responses','subscription_only':True,'human_authorization':'synthetic fixture'}));counter=[]
   def respond(model,prompt,instructions,**kwargs):
    counter.append(1)
    body={'model':model,'instructions':instructions,'input':[{'role':'user','content':[{'type':'input_text','text':prompt}]}],'reasoning':{'effort':'low'},'store':False,'stream':True,'text':{'format':{'type':'json_schema','name':'authentic_user_trial','strict':True,'schema':kwargs['schema']}}}
    if instructions=='synthetic':wire={'protocol_version':3,'facts':[],'inferences':[],'direction':'unknown','direction_inference':None,'unknowns':['synthetic unknown']}
    if instructions=='synthetic' and protocol_name=='atomic-bound-v4':
     payload=vw.decode_prompt(prompt)[1];book=sr.lookup(payload['user_context']['evidence']);ref=next((r for r,v in book.items() if v.get('field')=='text'),None)
     atoms=[] if ref is None else [{'kind':'conditional_forecast','text':'如果相似体验延续，可能维持评价。','condition':'similar_experience','confidence':'low','anchors':[{'ref':ref,'quote':sr.value_text(book[ref])}]}]
     wire={'protocol_version':4,'facts':[],'atoms':atoms,'direction':'passive' if atoms else 'unknown','direction_atom':0 if atoms else None,'unknowns':['no_observed_outcome']}
    if instructions=='synthetic' and invalid and len(counter)==1:wire['direction']='promoter'
    if instructions!='synthetic':wire={'reviews':[{'review_id':t['review_id'],'wire_sha256':t['wire_sha256'],'evidence_sha256':t['evidence_sha256'],'items':[]} for t in json.loads(prompt)['tasks']]}
    if instructions!='synthetic' and protocol_name=='atomic-bound-v4':
     for row,task in zip(wire['reviews'],json.loads(prompt)['tasks']):
      row['items']=[{'atom_index':i,'verdict':'bounded_hypothesis','issue':'none','used_refs':[a['ref'] for a in atom['anchors']],'missing_refs':[],'problem_span':'','reason':'Synthetic bounded hypothesis'} for i,atom in enumerate(task['candidate']['atoms'])]
    if instructions!='synthetic' and review_invalid and len(counter)==65:wire['reviews'][0]['wire_sha256']='wrong-candidate'
    if instructions!='synthetic' and batch_invalid:wire={'reviews':[]}
    return {'text':json.dumps(wire),'response':{'id':'synthetic-'+str(len(counter)),'status':'completed','model':model,'usage':{'input_tokens':100,'output_tokens':50}},'request_body_sha256':hashlib.sha256(json.dumps(body,ensure_ascii=False).encode()).hexdigest(),'paid_fallback_used':False}
   client=Mock();client.respond.side_effect=respond
   with patch.object(cp,'PlanClient',return_value=client),patch('builtins.print'):
    self.assertEqual(pt.execute(rd,'unused',consent)['status'],'completed_with_structural_failures' if invalid else 'completed')
    state=pr.execute(rd,'unused',consent)
    self.assertEqual(state['status'],'stopped_review_contract' if batch_invalid else 'completed_with_review_rejections' if review_invalid else 'completed')
   if batch_invalid:
    dest=root/'source-review';self.assertEqual(len(counter),len(calls)+1)
    self.assertEqual(state['reviewed_answers'],0);self.assertEqual(state['completed_batches'],1)
    receipt=dest/'B001.receipt.json';index=au.read_object(dest/'B001.index.json')
    self.assertEqual(index['receipt_sha256'],hashlib.sha256(receipt.read_bytes()).hexdigest())
    self.assertEqual(list(dest.glob('*.final.json')),[])
    with self.assertRaises(au.InputError):pr.audit(rd)
    return
   a=pr.audit(rd);self.assertEqual(a['global_review_rejections'],int(review_invalid));self.assertEqual(len(list((root/'source-review').glob('*.review-rejected.json'))),int(review_invalid));self.assertEqual(len(list((root/'source-review').glob('*.final.json'))),len(calls)-int(invalid)-int(review_invalid));self.assertEqual(a['structural_rejections'],int(invalid));self.assertEqual(a['reviewed_answers'],len(calls)-int(invalid));self.assertEqual(a['completed_batches'],len(calls)//4);self.assertEqual(len(counter),len(calls)*5//4)
   receipt=next((root/'source-review').glob('*.receipt.json'));receipt.write_text(receipt.read_text()+' ')
   with self.assertRaises(au.InputError):pr.audit(rd)
  finally:f.tearDown()
