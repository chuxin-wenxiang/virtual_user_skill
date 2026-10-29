#!/usr/bin/env python3
"""Visible-field catalogue and descriptive counts. No model or private-data access."""
import json
import re
from collections import Counter
import claim_protocol as p

# Lexical review hints only: compound labels, synonyms and negation need semantics.
TOPICS = {
    'price': r'价格|价钱|费用|收费|性价比|便宜|贵|优惠|price|cost',
    'network': r'网络|断网|信号|联网|流量|网速|network',
    'pickup_return': r'取还|取车|还车|送车|接送|pick.?up|drop.?off',
    'service': r'客服|服务|态度|service',
    'cleanliness': r'干净|卫生|清洁|脏|clean',
    'questionnaire': r'问卷|调查|survey|questionnaire',
    'refund': r'退款|退票|退订|refund',
    'compensation': r'赔付|赔偿|补偿|compensation',
    'deposit': r'押金|保证金|deposit',
    'invoice': r'发票|开票|invoice',
    'confirmation': r'确认|出票|confirmation',
    'credit_stay': r'信用住|免押',
    'battery': r'电量|续航|充电|battery',
}
RANKING = re.compile(r'主要|最看重|最关心|最在意|高频|频繁|经常|多次|反复|较多|更多次|最高|最多|最少|排名|占比|频率')

def topics(text):
    return {k for k, pattern in TOPICS.items() if re.search(pattern, text, re.I)}

def catalogue(evidence):
    p.require(isinstance(evidence, list), 'Evidence must be a list')
    fields = []; ids = set(); counts = Counter(); origins = {}
    for row in evidence:
        rid = row.get('id')
        p.require(isinstance(rid, str) and re.fullmatch(r'E\d+', rid) and rid not in ids, 'Invalid or duplicate evidence ID')
        ids.add(rid)
        for field in p.FIELDS:
            if field not in row or row[field] is None:
                continue
            try: value = p.source_value(row, field)
            except p.ProtocolError: continue
            fields.append({'ref': f'F{len(fields)+1:03d}', 'evidence_id': rid,
                           'field': field, 'value': value})
        if row.get('kind') == 'survey':
            for tag in row.get('tags', []):
                counts[tag] += 1; origins.setdefault(tag, []).append(rid)
        elif row.get('kind') == 'historical_tag_summary':
            tag, count = row.get('tag'), row.get('count')
            p.require(isinstance(tag, str) and type(count) is int and count >= 0, 'Invalid visible tag count')
            counts[tag] += count; origins.setdefault(tag, []).append(rid)
    stats = []
    if counts:
        stats.append({'ref': 'T001', 'kind': 'complete_visible_tag_counts',
                      'unit': 'visible survey tag records; multiple labels per survey; not independent events or personal priorities',
                      'values': [{'tag': tag, 'count': count, 'evidence_ids': origins[tag]}
                                 for tag, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]})
    return {'fields': fields, 'statistics': stats}

def lookup(evidence):
    book = catalogue(evidence)
    return {x['ref']: x for group in book.values() for x in group}

def value_text(item):
    value = item['value']
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

def check_atom(atom, book):
    anchors = atom['anchors']; selected = []
    p.require(isinstance(anchors, list) and 1 <= len(anchors) <= 6, 'Atom needs one to six exact field anchors')
    seen = set()
    for a in anchors:
        p.require(isinstance(a, dict) and set(a) == {'ref', 'quote'}, 'Anchor fields differ')
        ref, quote = a['ref'], a['quote']
        p.require(isinstance(ref, str) and ref in book and ref.startswith('F'), 'Unknown field anchor')
        p.require(isinstance(quote, str) and quote.strip() and quote in value_text(book[ref]), 'Anchor quote is not an exact source substring')
        p.require((ref, quote) not in seen, 'Duplicate exact anchor')
        p.require(book[ref]['field'] not in ('date', 'count'), 'Dates and counts alone are not a qualitative premise')
        seen.add((ref, quote))
        if book[ref] not in selected: selected.append(book[ref])
    text = atom['text']
    p.require(not RANKING.search(text), 'Frequency/comparison prose must use script-rendered statistics facts')
    if atom['kind'] == 'source_summary':
        p.require(any(x['field'] in ('text', 'score') for x in selected), 'Self-report summaries require text or score fields')
    return selected

def review_hints(atom, book):
    """Surface lexical differences without certifying or rejecting their meaning."""
    selected = check_atom(atom, book)
    found = topics(atom['text'])
    source_topics = topics(' '.join(value_text(x) for x in selected))
    return {'multiple_topic_keywords': sorted(found) if len(found) > 1 else [],
            'unmatched_topic_keywords': sorted(found - source_topics),
            'semantic_verdict': None}
