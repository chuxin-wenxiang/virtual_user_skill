"""Scope review of v5 components; an estimate has its own support and lifecycle."""
import argparse
import copy
import json
from pathlib import Path
import authentic_user as au
import decision_protocol as p
import clause_review as prior
import scope_review as scope
import source_registry as sr

NAME = 'decision-scope-v1'
digest = prior.digest


def schema():
    result=scope.schema()
    result['properties']['review_version']['enum']=[4]
    return result


def task(evidence,wire,level=None,industry=None):
    atoms=p.units(evidence,wire,level,industry);book=sr.lookup(evidence);rows={r['id']:r for r in evidence}
    refs=list(dict.fromkeys(a['ref'] for atom in atoms for a in atom['anchors']))
    fields=[copy.deepcopy(book[r])|{'recorded_date':rows[book[r]['evidence_id']].get('date')} for r in refs]
    return {'review_protocol':NAME,'evidence_sha256':digest(evidence),'wire_sha256':digest(wire),
            'evidence':evidence,'candidate':wire,'source_fields':fields,
            'capability_level':level,'target_industry':industry,
            'atom_bindings':[{'atom_index':i,'component_path':a['path'],'kind':a['kind'],'text':a['text'],
                              'selected_refs':[x['ref'] for x in a['anchors']],
                              'selected_field_types':sorted({book[x['ref']]['field'] for x in a['anchors']}),
                              'selected_scope':'Only this component selected complete fields; no other component or baseline may supply premises.',
                              'clauses':[{'clause_index':j,'text':part} for j,part in enumerate(prior.clauses(a['text']))]}
                             for i,a in enumerate(atoms)],
            'context_rule':'Dates describe source chronology, not event identity or causality. Review an estimate as uncalibrated future inference, not as an already observed outcome.'}


def outbound_task(evidence,wire,level=None,industry=None):
    return {k:v for k,v in task(evidence,wire,level,industry).items() if k!='evidence'}


def apply(evidence,wire,review,contract_errors=None,policy_withdrawals=None,level=None,industry=None):
    atoms=p.units(evidence,wire,level,industry)
    p.require(isinstance(review,dict) and set(review)==set(schema()['required']) and type(review['review_version']) is int and review['review_version']==4, 'Decision review fields differ')
    p.require(review['wire_sha256']==digest(wire) and review['evidence_sha256']==digest(evidence), 'Review belongs to another decision candidate or source')
    items=review['items'];p.require(isinstance(items,list) and len(items)==len(atoms), 'Every component must be reviewed once')
    keep=[];seen=set();shape=set(schema()['properties']['items']['items']['properties']['clauses']['items']['required'])
    for item in items:
        p.require(isinstance(item,dict) and set(item)=={'atom_index','clauses'}, 'Component review fields differ')
        i=item['atom_index'];p.require(type(i) is int and 0<=i<len(atoms) and i not in seen, 'Unknown or duplicate component review');seen.add(i)
        try:
            checks=item['clauses'];p.require(isinstance(checks,list), 'Clause checks must be a list')
            for c in checks:
                p.require(isinstance(c,dict) and set(c)==shape and c['role'] in scope.ROLES, 'Clause role or fields differ')
                if atoms[i]['kind']=='source_summary':
                    p.require(c['role'] in ('historical_claim','evidence_boundary'), 'A source summary cannot masquerade as future inference')
                if c['role'] in ('future_condition','future_consequence','topic_hypothesis'):
                    p.require(c['inference']!='faithful_summary', 'Future inference is not an observed outcome')
                if atoms[i]['kind']=='attitude_estimate' and c['clause_index']==0:
                    p.require(c['role']=='future_consequence' and c['inference']=='bounded_hypothesis', 'The script-rendered estimate must be assessed as uncalibrated future inference')
            legacy={'atom_index':i,'clauses':[{k:v for k,v in c.items() if k!='role'} for c in checks]}
            supported=prior.check_item(atoms[i],legacy)
            boundaries=[c['clause_index'] for c in checks if c['role']=='evidence_boundary']
            if boundaries:
                if policy_withdrawals is not None:policy_withdrawals.append({'atom_index':i,'component_path':atoms[i]['path'],'clause_indices':boundaries,'status':'boundary_policy_withdrawal'})
            elif supported:keep.append(i)
        except p.ProtocolError as exc:
            if contract_errors is None:raise
            contract_errors.append({'atom_index':i,'component_path':atoms[i]['path'],'error':str(exc),'status':'review_pending'})
    kept={tuple(atoms[i]['path']) for i in keep};out=copy.deepcopy(wire)
    for group in p.GROUPS:out[group]=[v for i,v in enumerate(wire[group]) if (group,i) in kept]
    if ('prediction',) not in kept:out['prediction']=None
    if not out['facts'] and not any(out[g] for g in p.GROUPS) and out['prediction'] is None and not out['unknowns']:
        out['unknowns']=['no_supported_estimate']
    p.validate(evidence,out,level,industry)
    return out


INSTRUCTIONS = scope.INSTRUCTIONS.replace('review_version=3','review_version=4')+'''
本轮decision-bound-v5不使用direction_atom。atom_bindings已把summaries、hypotheses、reactions和prediction编译为各自完整待审条目，component_path对应原位置。
attitude_estimate是下一次同业NPS类别的未校准估计，有自己选择的text/score字段。首个脚本分句固定是未来估计，role必须future_consequence、inference=bounded_hypothesis；理由中的历史陈述逐句核源。不要求先观测未来，也不宣称预测准确。
prediction与reaction独立，不能因一个反应失败连带否定其他条目；也不能用另一个条目、历史基线、未选字段替prediction补前提。prediction的实际所选字段不足时如实拒绝，脚本只撤该估计、不回填基线。
不返回修改后的候选或新答案。资料缺口用已有unknowns，审核合约未完成与语义拒绝分别记录。'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('precheck','prompt','finalize'))
    for name in ('bundle','answer','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--review');parser.add_argument('--audit-output');args=parser.parse_args()
    try:
        bundle=au.validate_bundle(au.read_object(args.bundle));raw=au.read_object(args.answer)
        p.require(raw.get('bundle_sha256')==bundle['bundle_sha256'], 'Answer belongs to another bundle')
        evidence=bundle['evidence'];level=bundle['capability']['level'];industry=bundle.get('industry_filter');wire=raw.get('wire_answer')
        p.require(not Path(args.output).exists(), 'Output already exists')
        errors=[];policy=[]
        if args.command=='prompt':
            au.render_bound_answer(bundle,raw)
            result=INSTRUCTIONS+'\n审核schema：'+json.dumps(schema(),ensure_ascii=False)+'\n任务：'+json.dumps(outbound_task(evidence,wire,level,industry),ensure_ascii=False)
        else:
            p.require(args.audit_output and not Path(args.audit_output).exists(), 'New audit output required')
            if args.command=='precheck':final,log=p.precheck(evidence,wire,level,industry)
            else:
                p.require(args.review, 'Review is required')
                final=apply(evidence,wire,au.read_object(args.review),errors,policy,level,industry)
                log={'review_protocol':NAME,'review_contract_errors':errors,'policy_withdrawals':policy,'all_reviews_valid':not errors}
            log.update(original_wire_sha256=digest(wire),final_wire_sha256=digest(final),evidence_sha256=digest(evidence))
            bound={k:raw[k] for k in ('bundle_sha256','answer_mode')}|{'wire_answer':final}
            rendered=au.render_bound_answer(bundle,bound)
            au.write_new(args.audit_output,json.dumps(log,ensure_ascii=False,indent=2)+'\n')
            result=json.dumps(rendered,ensure_ascii=False,indent=2)+'\n'
        au.write_new(args.output,result);return 2 if errors else 0
    except (au.InputError,p.ProtocolError,OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'ok':False,'error':str(exc) if isinstance(exc,(au.InputError,p.ProtocolError)) else type(exc).__name__}));return 2


if __name__=='__main__':raise SystemExit(main())
