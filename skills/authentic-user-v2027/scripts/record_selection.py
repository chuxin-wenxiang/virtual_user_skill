#!/usr/bin/env python3
"""Question-ranked records with explicit recent context, never event matching."""
import authentic_user as au

NAME = 'question_recent_context_v1'
LEGACY = 'question_token_overlap_then_recency'
POLICIES = (NAME, LEGACY)


def select(records, question, max_records, max_chars):
    query = au.tokens(question)
    def rank(row):
        text = row.get('text', '')+' '.join(row.get('tags', []))+row['industry_cn']
        return (len(query & au.tokens(text)), au.date_value(row['date']), row['kind'], row['source_record_sha256'])
    ordered = sorted(records, key=rank, reverse=True)
    groups = {}
    for row in ordered:
        if row['kind'] == 'survey':
            groups.setdefault((row['industry'], au.date_value(row['date'])), []).append(row)
    chosen, blocked = {}, set()
    used = 0

    def unit(row):
        return groups[(row['industry'], au.date_value(row['date']))] if row['kind'] == 'survey' else [row]

    def add(rows):
        nonlocal used
        pending = [r for r in rows if r['source_record_sha256'] not in chosen]
        cost = sum(len(au.canonical(r)) for r in pending)
        if len(chosen)+len(pending) > max_records or used+cost > max_chars:
            return False
        for r in pending:
            chosen[r['source_record_sha256']] = r
        used += cost
        return True

    seed = next((row for row in ordered if add(unit(row))), None)
    reservation = {'status': 'no_selected_anchor', 'industry': None, 'selected_evidence_ids': []}
    recent = []
    if seed:
        industry = seed['industry']
        surveys = [r for r in ordered if r['industry'] == industry and r['kind'] == 'survey']
        if surveys:
            last = max(au.date_value(r['date']) for r in surveys)
            recent = groups[(industry, last)]
            kept = add(recent)
            reservation.update(status='selected' if kept else 'budget_excluded', industry=industry)
            if not kept:
                blocked.update(r['source_record_sha256'] for r in recent)
        else:
            reservation.update(status='no_eligible_survey', industry=industry)
        quotes = [r for r in ordered if r['industry'] == industry and r['kind'] == 'verbatim']
        if quotes:
            # One most recent text record is context, not a linked event or a complete-day claim.
            add([max(quotes, key=lambda r: (au.date_value(r['date']), rank(r)))])
    for row in ordered:
        if row['source_record_sha256'] not in blocked:
            add(unit(row))
    selected = sorted((dict(r) for r in chosen.values()), key=lambda r: (au.date_value(r['date']), r['kind'], r['source_record_sha256']))
    for i, row in enumerate(selected, 1):
        row['id'] = f'E{i:03d}'
    recent_hashes = {r['source_record_sha256'] for r in recent}
    reservation['selected_evidence_ids'] = [r['id'] for r in selected if r['source_record_sha256'] in recent_hashes]
    return selected, {'latest_survey_context': reservation, 'selected_records': len(selected),
                      'selected_record_chars': used,
                      'scope': 'Filtered local pre-cutoff pool only; same-time survey rows stay separate. Context is not an event match, causal evidence or semantic support.'}
