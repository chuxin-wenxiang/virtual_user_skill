"""Descriptive selected-history trajectory and an explicitly separate NPS baseline."""
from collections import defaultdict
import authentic_user as au
import source_registry as sr


def segment(score):
    return 'promoter' if score >= 9 else 'passive' if score >= 7 else 'detractor'


def target_industry(evidence, industry=None):
    if industry is not None:
        if industry not in au.INDUSTRIES:
            raise au.InputError('Unknown baseline industry')
        return industry
    values = {r.get('industry') for r in evidence if r.get('kind') in ('survey','verbatim')}
    return next(iter(values)) if len(values) == 1 else None


def card(evidence, industry=None):
    industry = target_industry(evidence, industry)
    result = {'method':'last_same_industry_v1', 'scope':'selected_visible_history_only',
              'industry':industry, 'status':'ambiguous_industry' if industry is None else 'no_scored_survey',
              'direction':'unknown', 'latest_score':None, 'latest_date':None, 'source_refs':[],
              'trajectory':[], 'category_changes':0, 'conflicting_timestamp_count':0,
              'calibrated':False, 'is_ai_prediction':False,
              'assumption':'Historical category persistence is a baseline estimate, not a new answer or observed future behavior.'}
    if industry is None:
        return result
    book = sr.lookup(evidence)
    refs = {v['evidence_id']:k for k,v in book.items() if k.startswith('F') and v['field']=='score'}
    groups = defaultdict(list)
    for row in evidence:
        if row.get('kind')=='survey' and row.get('industry')==industry and type(row.get('score')) is int and 0<=row['score']<=10:
            groups[au.date_value(row['date'])].append(row)
    for date, rows in sorted(groups.items()):
        scores = sorted({r['score'] for r in rows})
        result['trajectory'].append({'date':date.isoformat(), 'scores':scores,
            'direction':segment(scores[0]) if len(scores)==1 else 'unknown',
            'source_refs':[refs[r['id']] for r in rows]})
        result['conflicting_timestamp_count'] += int(len(scores)>1)
    trail = result['trajectory']
    if trail:
        last = trail[-1]
        result.update(status='available' if len(last['scores'])==1 else 'conflicting_latest_scores',
            direction=last['direction'], latest_score=last['scores'][0] if len(last['scores'])==1 else None,
            latest_date=last['date'], source_refs=last['source_refs'])
        # Ambiguous timestamps break the chain rather than being skipped as if certain.
        result['category_changes'] = sum(a['direction']!='unknown' and b['direction']!='unknown' and a['direction']!=b['direction'] for a,b in zip(trail,trail[1:]))
    return result


def describe(result):
    names={'promoter':'推荐','passive':'观望','detractor':'不推荐','unknown':'未知'}
    if result['status']=='available':
        detail='最近同业调查'+result['latest_date']+'为'+str(result['latest_score'])+'分；延续估计为'+names[result['direction']]
    elif result['status']=='conflicting_latest_scores':
        detail='最近同业调查时点存在不同评分，基线为未知'
    elif result['status']=='ambiguous_industry':
        detail='未明确单一目标行业，基线为未知'
    else:
        detail='所选历史没有可用的同业调查评分，基线为未知'
    sources='；来源字段：'+', '.join(result['source_refs']) if result['source_refs'] else ''
    return '脚本历史延续基线：'+detail+sources+'。此为未校准估计，与AI态度估计分列，不代表本人新回答。'
