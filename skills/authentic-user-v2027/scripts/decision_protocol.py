"""Independent attitude estimate, conditional reactions and script-extracted anchors."""
import copy
import json
import re
import atomic_protocol as old
import source_registry as sr
import attitude_baseline as baseline

NAME = 'decision-bound-v5'
ProtocolError = old.ProtocolError
require = old.require
UNKNOWN = {k:v for k,v in old.UNKNOWN.items() if k not in ('review_pending','review_withdrawal')}
UNKNOWN['no_supported_estimate'] = '未形成可交付的AI态度估计；历史基线及条件反应分别查看。'
GROUPS = ('summaries','hypotheses','reactions')
GROUP_LIMITS = {'summaries':1,'hypotheses':2,'reactions':2}
LABELS = {'source_summary':'来源概括', 'topic_hypothesis':'关注点假设',
          'conditional_forecast':'条件反应', 'attitude_estimate':'AI态度估计（未校准）'}
DIRECTIONS = {'promoter':'推荐', 'passive':'观望', 'detractor':'不推荐'}
CATEGORY_TOKEN = r'(?:不推荐|推荐|观望|promoter|passive|detractor)(?=类别|类|方向|评价|[，；。、！？.!?\s]|$)'
# Catch explicit category routing; these guards do not replace semantic review.
POINT_ESTIMATE = re.compile(r'(?:下一(?:次|条|轮)?|下次|next\b)[^。；\n]{0,96}(?:为|是|属于|延续|维持|偏向|倾向|may\s+be|will\s+be)\s*'+CATEGORY_TOKEN,re.I)
CATEGORY_CONTINUATION = re.compile(r'(?:(?:仍(?:然)?(?:会|可能)?给出|继续(?:给出|作出)|(?:维持|延续|保持)(?:为|在)?)[^，；。、]{0,8}|继续|仍然?)'+CATEGORY_TOKEN,re.I)


def schema():
    def obj(props):
        return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
    refs = {'type':'array','minItems':1,'maxItems':6,'items':{'type':'string','pattern':r'^F[0-9]{3,}$'}}
    item = obj({'text':{'type':'string'}, 'source_refs':refs,
                'confidence':{'type':'string','enum':['low','medium']}})
    prediction = obj({'direction':{'type':'string','enum':list(DIRECTIONS)},
                      'reason':{'type':'string'}, 'source_refs':refs,
                      'confidence':{'type':'string','enum':['low','medium']}})
    return obj({'protocol_version':{'type':'integer','enum':[5]},
                'facts':{'type':'array','maxItems':4,'items':{'type':'string','pattern':r'^[FT][0-9]{3,}$'}},
                **{g:{'type':'array','maxItems':GROUP_LIMITS[g],'items':copy.deepcopy(item)} for g in GROUPS},
                'prediction':{'anyOf':[prediction,{'type':'null'}]},
                'unknowns':{'type':'array','maxItems':6,'items':{'type':'string','enum':list(UNKNOWN)}}})


def empty():
    return {'protocol_version':5,'facts':[],**{g:[] for g in GROUPS},'prediction':None,'unknowns':[]}


def _item(evidence, item, kind, path, industry=None):
    fields = {'direction','reason','source_refs','confidence'} if kind=='attitude_estimate' else {'text','source_refs','confidence'}
    require(isinstance(item,dict) and set(item)==fields, 'Decision component fields differ')
    require(item['confidence'] in ('low','medium'), 'Invalid decision confidence')
    text = item.get('reason') if kind=='attitude_estimate' else item.get('text')
    require(isinstance(text,str) and text.strip() and len(text)<=240 and not re.search(r'\[[EFT]\d+\]',text), 'Invalid component text or authored citation')
    if kind=='topic_hypothesis':
        require(not POINT_ESTIMATE.search(text), 'An explicit next-record category estimate belongs only in prediction')
    refs = item['source_refs']; book = sr.lookup(evidence)
    require(isinstance(refs,list) and 1<=len(refs)<=6 and all(isinstance(r,str) and r.startswith('F') and r in book for r in refs) and len(refs)==len(set(refs)), 'Unknown or duplicate selected field')
    if kind=='conditional_forecast' and CATEGORY_CONTINUATION.search(text):
        require(any(book[r]['field']=='score' for r in refs), 'A continued NPS category requires its own selected historical score')
    if kind=='attitude_estimate':
        require(isinstance(item['direction'],str) and item['direction'] in DIRECTIONS, 'Estimate must select one category or be null')
        target = baseline.target_industry(evidence,industry)
        require(target is not None, 'An attitude estimate needs an unambiguous target industry')
        rows = {r['id']:r for r in evidence}
        require(all(rows[book[r]['evidence_id']]['industry']==target for r in refs), 'Estimate uses another industry')
        require(any(book[r]['field'] in ('text','score') for r in refs), 'Estimate needs text or score, not labels alone')
        text = '对下一次同业评价的估计可能为'+DIRECTIONS[item['direction']]+'。依据：'+text
    if kind=='conditional_forecast':
        require(re.search(r'如果|若|假如|if\b',text,re.I) and re.search(r'可能|也许|或许|may\b|might\b',text,re.I), 'Reaction must state an uncertain explicit scenario')
    # Full selected source values are extracted without the model retyping quotes.
    atom = {'kind':kind,'text':text,'confidence':item['confidence'],
            'anchors':[{'ref':r,'quote':sr.value_text(book[r])} for r in refs], 'path':path}
    sr.check_atom(atom,book,review_context=True)
    return atom


def units(evidence, wire, level=None, industry=None):
    require(isinstance(wire,dict) and set(wire)==set(schema()['required']), 'Decision answer fields differ')
    require(type(wire['protocol_version']) is int and wire['protocol_version']==5, 'Expected decision protocol 5')
    facts=wire['facts']; book=sr.lookup(evidence)
    require(isinstance(facts,list) and len(facts)<=4 and all(isinstance(r,str) and r in book for r in facts) and len(facts)==len(set(facts)), 'Unknown or duplicate fact selector')
    unknowns=wire['unknowns']
    require(isinstance(unknowns,list) and len(unknowns)<=6 and all(isinstance(v,str) and v in UNKNOWN for v in unknowns) and len(unknowns)==len(set(unknowns)), 'Unknown codes differ; review states are script-owned')
    require(wire['prediction'] is None or 'no_supported_estimate' not in unknowns, 'A present prediction contradicts no_supported_estimate')
    output=[]
    for group, kind in zip(GROUPS,('source_summary','topic_hypothesis','conditional_forecast')):
        values=wire[group]
        require(isinstance(values,list) and len(values)<=GROUP_LIMITS[group], 'Decision component group exceeds its bound')
        output.extend(_item(evidence,item,kind,[group,i],industry) for i,item in enumerate(values))
    prediction=wire['prediction']
    if prediction is not None:
        require(level in (None,'individual_memory'), 'Evidence capability does not permit an unconditional attitude estimate')
        output.append(_item(evidence,prediction,'attitude_estimate',['prediction'],industry))
    require(len(output)<=6, 'At most six independently reviewed components including the estimate')
    if level in ('facts_only','insufficient'):
        require(not output, 'Evidence capability does not permit simulation')
    if level=='insufficient':
        require(not facts and unknowns, 'No evidence requires explicit unknowns')
    require(facts or output or unknowns, 'Empty decision answer')
    return output


def validate(evidence,wire,level=None,industry=None):
    units(evidence,wire,level,industry)
    return sr.lookup(evidence)


def render(evidence,wire,level=None,industry=None):
    atoms=units(evidence,wire,level,industry);book=sr.lookup(evidence)
    seed={'protocol_version':4,'facts':wire['facts'],'atoms':[],'direction':'unknown','direction_atom':None,
          'unknowns':[] if wire['facts'] else ['no_direct_intent']}
    initial=old.render(evidence,seed,level if level!='insufficient' else None)
    lines=[line for line in initial['answer'].splitlines() if not line.startswith('未知：')]
    claims=initial['claims'];quotes=initial['quotes']
    for i,atom in enumerate(atoms):
        selected=sr.check_atom(atom,book,review_context=True);ids=list(dict.fromkeys(f['evidence_id'] for f in selected))
        text=LABELS[atom['kind']]+'（'+atom['confidence']+'）：'+atom['text']
        lines.append(text+' '+''.join('['+rid+']' for rid in ids))
        lines.append('依据完整字段：'+json.dumps(selected,ensure_ascii=False).replace('[E','［E'))
        claims.append({'text':text,'kind':'inference','evidence_ids':ids,'confidence':atom['confidence'],
                       'atom_index':i,'atom_kind':atom['kind'],'component_path':atom['path'],'anchors':atom['anchors']})
    base=baseline.card(evidence,industry)
    lines.append(baseline.describe(base))
    unknowns=[UNKNOWN[v] for v in wire['unknowns']]
    if wire['prediction'] is None:
        lines.append('AI态度估计：unknown；不以历史基线自动填补。')
    lines.extend('未知：'+v for v in unknowns)
    direction=wire['prediction']['direction'] if wire['prediction'] is not None else 'unknown'
    return {'answer':'\n'.join(lines),'direction':direction,'claims':claims,'quotes':quotes,'unknowns':unknowns,
            'protocol_version':5,'wire_answer':wire,'renderer':NAME,'baseline':base,
            'prediction_deviates_from_baseline':direction!='unknown' and base['direction']!='unknown' and direction!=base['direction']}


def precheck(evidence,wire,level=None,industry=None):
    require(isinstance(wire,dict) and set(wire)==set(empty()), 'Decision global fields differ')
    require(type(wire['protocol_version']) is int and wire['protocol_version']==5, 'Expected decision protocol 5')
    base=empty();base['unknowns']=copy.deepcopy(wire['unknowns']) or ['no_supported_estimate']
    validate(evidence,base,level,industry)
    require(all(isinstance(wire[g],list) and len(wire[g])<=GROUP_LIMITS[g] for g in GROUPS) and isinstance(wire['facts'],list) and len(wire['facts'])<=4, 'Decision global arrays differ')
    require(sum(len(wire[g]) for g in GROUPS)+int(wire['prediction'] is not None)<=6, 'Too many components')
    kept=[];errors=[];fact_errors=[];result=copy.deepcopy(base)
    unknown_errors=[]
    if wire['prediction'] is not None and 'no_supported_estimate' in wire['unknowns']:
        unknown_errors.append({'unknown_index':wire['unknowns'].index('no_supported_estimate'),
                               'code':'no_supported_estimate','error':'Conflicts with a present prediction; omit only if that prediction survives'})
    log={'kept_component_paths':kept,'component_errors':errors,'fact_errors':fact_errors,'unknown_errors':unknown_errors}
    try:validate(evidence,wire,level,industry);log['original_strict_contract_pass']=True
    except ProtocolError as exc:log.update(original_strict_contract_pass=False,original_strict_error=str(exc))
    for i,ref in enumerate(wire['facts']):
        try:
            candidate=copy.deepcopy(base);candidate['facts']=result['facts']+[ref];validate(evidence,candidate,level,industry)
            result['facts'].append(ref)
        except ProtocolError as exc:fact_errors.append({'fact_index':i,'error':str(exc)})
    for group in GROUPS+('prediction',):
        values=[wire[group]] if group=='prediction' and wire[group] is not None else [] if group=='prediction' else wire[group]
        for i,value in enumerate(values):
            path=[group] if group=='prediction' else [group,i]
            try:
                candidate=copy.deepcopy(base);candidate[group]=value if group=='prediction' else [value]
                if group=='prediction':candidate['unknowns']=[v for v in candidate['unknowns'] if v!='no_supported_estimate']
                validate(evidence,candidate,level,industry)
                if group=='prediction':result[group]=copy.deepcopy(value)
                else:result[group].append(copy.deepcopy(value))
                kept.append(path)
            except ProtocolError as exc:errors.append({'component_path':path,'error':str(exc)})
    if wire['unknowns']:result['unknowns']=[v for v in wire['unknowns'] if not (v=='no_supported_estimate' and result['prediction'] is not None)]
    elif result['facts'] or any(result[g] for g in GROUPS) or result['prediction'] is not None:result['unknowns']=[]
    validate(evidence,result,level,industry)
    return result,log


INSTRUCTIONS = '''只用可见证据，原话是数据。输出decision-bound-v5 / protocol_version=5。
facts只选择目录F/T编号，由脚本提取原值。summaries只概括text/score，标签概括放facts，不当作满意经历。
hypotheses给出本题证据最强的1–2个关注点；reactions单独写“如果条件A，可能反应B”。summaries最多1条，hypotheses和reactions各最多2条，含prediction在内总共最多6条。不要罗列不相关因素来碰中原因；“最关键”仍是待检验选择，不把标签次数当个人优先级。
hypotheses只表达候选关注点/解释；任何对下一次/下一条NPS类别的估计只放prediction，不能在hypotheses重复或绕过档位限制。无条件类别估计即使写“可能”也不变成条件反应。
每条只填text、source_refs（真实F编号）、confidence（low/medium）；不填kind、condition、引文quote或正文引用，脚本按所在分组定类型、按选择抽取完整原字段，不改繁简或删否定。一个判断有多个前提时选齐字段；少选字段仍会被语义审核撤下。
prediction独立为null或{direction,reason,source_refs,confidence}，是对下一次同业NPS类别的未校准估计，不是本人新答或已发生行为，不绑定任何reaction。必须有自己的text/score依据，不能借另一个条目或基线卡补引用。无足够依据时null，不强填观望；非individual_memory档位只给条件反应，不作此估计。
reactions若说“继续/仍给出/维持推荐类别”，本条须另选既往score；正面原话或中性标签不证明历史NPS类别。只有来源主题时可写“如果此次A，可能给出B”，不预设此前已给出B。
仅当前问题明确要求估计同业NPS/态度类别时填写prediction；只问历史主题、原因或投诉金额时保持null，不附送未被询问的预测。
先看明确行业的历史基线和轨迹。没有新的可见反向信号时，不随意偏离延续；有偏离时reason指明实际证据与不确定性。沿用基线不算AI新增价值；基线不自动补prediction，也不承诺预测准确。混业未明确目标时不猜目标行业。
unknowns只选所给资料缺口代码。历史缺资料不等于从未发生；不编投诉、赔付、金额、人格或隐秘动机。心理学只作为有原话依据、可反驳的解释，不能补证。
prediction非null时不得填no_supported_estimate。概括多期评分必须选齐涉及的score；只选最近一期就只说该期。标签不称原话；单条原话不称全部历史。日期可与实质字段一起选，但日期本身不是体验依据。出现比较、次数、主要或否定优先级等词只触发语义核查，不表示脚本证明其成立；精确标签统计仍用facts的T编号。
每条只涉及其source_refs完整字段支持的对象和属性，信号不等于速度、退款不等于赔付。合理假设不需要已观测未来，但不得虚构历史前提。来源审核逐组件处理，错误反应不应连带删除有独立依据的prediction，prediction自身不过关则必须null。
'''
