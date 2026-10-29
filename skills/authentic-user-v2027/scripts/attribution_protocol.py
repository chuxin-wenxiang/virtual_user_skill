#!/usr/bin/env python3
"""Field-bound attribution; v2 source rendering stays reproducible."""
import copy
import claim_protocol as old
ProtocolError=old.ProtocolError
require=old.require
SCOPES=('self_report_summary','topic_hypothesis','future_condition')
def schema():
    s=copy.deepcopy(old.schema());s['properties']['protocol_version']['enum']=[3]
    inf=s['properties']['inferences']['items'];inf['properties'].pop('premise_ids');inf['required'].remove('premise_ids')
    inf['properties']['premises']={'type':'array','minItems':1,'maxItems':8,'items':copy.deepcopy(s['properties']['facts']['items'])}
    inf['properties']['scope']={'type':'string','enum':list(SCOPES)};inf['required']+=['premises','scope']
    s['properties']['direction_inference']={'type':['integer','null'],'minimum':0,'maximum':2};s['required'].append('direction_inference')
    return s

def downgrade(evidence,wire):
    require(isinstance(wire,dict) and set(wire)==set(schema()['required']),'Field-bound answer fields differ')
    require(type(wire['protocol_version']) is int and wire['protocol_version']==3,'Expected field-bound protocol 3')
    require(isinstance(wire['inferences'],list) and len(wire['inferences'])<=3,'Invalid inference list')
    lookup={r['id']:r for r in evidence};converted=[]
    for item in wire['inferences']:
        require(isinstance(item,dict) and set(item)==set(schema()['properties']['inferences']['items']['required']),'Inference fields differ')
        premises=item['premises'];scope=item['scope']
        require(scope in SCOPES and isinstance(premises,list) and 1<=len(premises)<=8,'Missing scope or field premises')
        seen=set()
        for p in premises:
            require(isinstance(p,dict) and set(p)=={'evidence_id','field'},'Premise must select an exact source field')
            ref,field=p['evidence_id'],p['field']
            require(isinstance(ref,str) and ref in lookup and isinstance(field,str),'Unknown premise source')
            old.source_value(lookup[ref],field)
            require((ref,field) not in seen,'Duplicate premise field');seen.add((ref,field))
        if scope=='self_report_summary':
            require(any(p['field'] in ('text','score') for p in premises),'Labels cannot certify self-reported experience or evaluation')
        if scope=='future_condition':
            require(any(p['field'] in ('text','score','tag','tags') for p in premises),'Metadata alone cannot support a future hypothesis')
        converted.append({k:v for k,v in item.items() if k not in ('premises','scope')}|{'premise_ids':list(dict.fromkeys(p['evidence_id'] for p in premises))})
    index=wire['direction_inference']
    if wire['direction']=='unknown':require(index is None,'Unknown direction must have no prediction inference')
    else:
        require(type(index) is int and 0<=index<len(wire['inferences']),'Direction must bind to one specific inference')
        linked=wire['inferences'][index]
        require(linked['scope']=='future_condition' and any(p['field'] in ('text','score') for p in linked['premises']),'Direction needs explicit self-report/score premises, not topic labels alone')
    legacy={k:v for k,v in wire.items() if k!='direction_inference'};legacy.update(protocol_version=2,inferences=converted)
    return legacy

def render(evidence,wire,level=None):
    result=old.render(evidence,downgrade(evidence,wire),level)
    result.update(protocol_version=3,wire_answer=wire,renderer='field-bound-v3')
    lookup={r['id']:r for r in evidence}
    for claim,inf in zip([c for c in result['claims'] if c['kind']=='inference'],wire['inferences']):
        claim['scope']=inf['scope'];claim['premise_fields']=copy.deepcopy(inf['premises'])
        details=[]
        for p in inf['premises']:
            row=lookup[p['evidence_id']];value=old.source_value(row,p['field'])
            import json
            details.append(p['evidence_id']+'.'+p['field']+'='+json.dumps(value,ensure_ascii=False).replace('[E','［E'))
        result['answer']+='\n推断依据字段（保留完整上下文）：'+'；'.join(details)
    return result

INSTRUCTIONS=old.INSTRUCTIONS+"""
本次使用 field-bound-v3 / protocol_version=3，推断改用 premises=[{evidence_id,field}]，不能只写整条记录编号。
只把该字段实际说出的意思用作前提。标签仅支持话题，分数仅指当时调查；同一时点多次表达不等于多个独立事件。
scope=self_report_summary仅归纳可见自述或分数；topic_hypothesis仅提出可能话题；future_condition用于未来条件性反应。
未指明退款、通知对象或流程时不补具体对象；含糊处保留未知。逐条检查候选机制、竞争解释也没有暗含未经支持的过去事实。
用direction_inference绑定承载方向预测的那一条推断的零基索引；unknown时为null。方向不能只靠标签猜测。
交付前还需来源语义审核；原始候选不改写，歧义或不支持的推断撤下，不生成更好答案替换。
"""
