#!/usr/bin/env python3
"""Read-only execution inventory and held-out Q2 baselines. Never calls a model."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import authentic_user as au
import validation_workflow as vw
import validation_prep as vp


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(path, index_path, model, ids):
    saved, index = au.read_object(path), au.read_object(index_path)
    response = saved.get('response', {})
    rid = response.get('id')
    expected_id = index.get('response_id', index.get('provider_response_id'))
    vw.require(isinstance(rid, str) and rid and rid == expected_id and rid not in ids,
               'Missing, mismatched or duplicate saved response ID')
    vw.require(index.get('receipt_sha256') == sha(path), 'Saved receipt differs from initial index')
    vw.require(response.get('status') == 'completed' and response.get('model') == model and
               saved.get('paid_fallback_used') is False, 'Unexpected receipt status/model/billing marker')
    usage = response.get('usage', {})
    vw.require(all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('input_tokens', 'output_tokens')),
               'Missing valid saved usage; do not silently count it as zero')
    ids.add(rid)
    return saved, index, {k: usage[k] for k in ('input_tokens', 'output_tokens')}


def inventory(run_dir):
    directory, run, calls, prompts = vw.load_run(run_dir)
    root = directory.parent
    ids, generation, source = set(), Counter(), Counter()
    usage = Counter(input_tokens=0, output_tokens=0)
    for folder in ('attempts', 'provider-events', 'incoming', 'receipt-index'):
        vw.require({p.stem for p in (root/folder).glob('*.json')} <= set(calls), 'Unexpected generation artifact')
    for cid in calls:
        paths = {f: root/f/(cid+'.json') for f in ('attempts', 'provider-events', 'incoming', 'receipt-index')}
        if not paths['attempts'].exists():
            vw.require(not any(p.exists() for f, p in paths.items() if f != 'attempts'), 'Receipt without attempt')
            generation['not_attempted'] += 1
            continue
        attempt = au.read_object(paths['attempts'])
        vw.require(attempt.get('call_id') == cid and attempt.get('run_sha256') == run['run_sha256'], 'Attempt binding differs')
        if not paths['provider-events'].exists():
            vw.require(not paths['incoming'].exists() and not paths['receipt-index'].exists(), 'Envelope/index without receipt')
            generation['request_state_unknown'] += 1
            continue
        if not paths['receipt-index'].exists() or not paths['incoming'].exists():
            generation['response_saved_unverified'] += 1
            continue
        saved, index, used = receipt(paths['provider-events'], paths['receipt-index'], run['model_config']['model'], ids)
        envelope = au.read_object(paths['incoming'])
        vw.validate_response(run, calls, prompts, envelope, check_answer=False)
        vw.require(index.get('call_id') == cid and index.get('run_sha256') == run['run_sha256'] and
                   index.get('envelope_sha256') == sha(paths['incoming']) and
                   envelope.get('provider_request_id') == saved['response']['id'], 'Envelope binding differs')
        vw.require(attempt.get('status') in ('imported', 'structural_failure'), 'Indexed response has unfinished local handling')
        generation['indexed_'+attempt['status']] += 1
        usage.update(used)

    dest = root/'source-review'
    finals, source_batches, pending_atoms = set(), Counter(), 0
    if not (dest/'plan.json').exists():
        vw.require(not any(dest.glob('*.final.json')), 'Final answers without source plan')
        source['not_planned'] = len(calls)
    else:
        plan, key = au.read_object(dest/'plan.json'), au.read_object(dest/'private-key.json')
        tasks = plan.get('tasks')
        vw.require(plan.get('run_sha256') == run['run_sha256'] and isinstance(tasks, list) and plan.get('batch_size') == 4,
                   'Invalid source plan binding or batch size')
        vw.require(plan.get('candidate_count') == len(tasks) and plan.get('total_candidates') == len(calls) and
                   plan.get('batches') == (len(tasks)+3)//4, 'Source plan counts differ')
        review_ids = [t.get('review_id') for t in tasks]
        vw.require(all(isinstance(r, str) for r in review_ids) and len(set(review_ids)) == len(review_ids) and set(key) == set(review_ids), 'Source task/key coverage differs')
        assigned = [key[r]['call_id'] for r in review_ids]
        rejected = set(plan.get('structural_rejections', {}))
        vw.require(len(set(assigned)) == len(assigned) and not (set(assigned) & rejected) and
                   set(assigned) | rejected == set(calls), 'Source candidate partition differs')
        source['structural_rejection'] = len(rejected)
        expected_batches = {f'B{i//4+1:03d}' for i in range(0, len(tasks), 4)}
        for suffix in ('.attempt.json', '.receipt.json', '.index.json'):
            vw.require({p.name[:-len(suffix)] for p in dest.glob('*'+suffix)} <= expected_batches, 'Unexpected source batch artifact')
        vw.require({p.name[:-len('.final.json')] for p in dest.glob('*.final.json')} <= set(assigned), 'Unexpected final candidate')
        for suffix in ('.assessment.json', '.review-rejected.json'):
            vw.require({p.name[:-len(suffix)] for p in dest.glob('*'+suffix)} <= set(assigned), 'Unexpected source candidate artifact')
        for offset in range(0, len(tasks), 4):
            batch, bid = tasks[offset:offset+4], f'B{offset//4+1:03d}'
            ap, rp, ip = (dest/(bid+s) for s in ('.attempt.json', '.receipt.json', '.index.json'))
            if not ap.exists():
                vw.require(not rp.exists() and not ip.exists(), 'Source receipt without attempt')
                state = 'not_attempted'
            else:
                vw.require(au.read_object(ap).get('run_sha256') == run['run_sha256'], 'Source attempt binding differs')
                if not rp.exists():
                    vw.require(not ip.exists(), 'Source index without receipt')
                    state = 'request_state_unknown'
                elif not ip.exists():
                    state = 'response_saved_unverified'
                else:
                    _, _, used = receipt(rp, ip, plan['model'], ids)
                    usage.update(used)
                    state = 'indexed_response'
            source_batches[state] += 1
            for task in batch:
                cid = key[task['review_id']]['call_id']
                fp, rejected_path = dest/(cid+'.final.json'), dest/(cid+'.review-rejected.json')
                vw.require(not (fp.exists() and rejected_path.exists()), 'Final and rejected artifacts conflict')
                if state != 'indexed_response':
                    vw.require(not fp.exists() and not rejected_path.exists(), 'Final/rejection without indexed receipt')
                    source[state] += 1
                elif fp.exists():
                    final = au.read_object(fp)
                    vw.require(final.get('call_id') == cid and final.get('candidate_sha256') == task['wire_sha256'], 'Final candidate binding differs')
                    source['final_saved'] += 1
                    pending_atoms += len(final.get('review_contract_errors', []))
                    finals.add(cid)
                elif rejected_path.exists():
                    vw.require(au.read_object(rejected_path).get('call_id') == cid, 'Rejected candidate binding differs')
                    source['review_contract_rejection'] += 1
                else:
                    source['indexed_response_without_final'] += 1
    generation_complete = generation['indexed_imported'] + generation['indexed_structural_failure'] == len(calls)
    # Inventory is deliberately weaker than the complete receipt/body/reproducibility audits.
    return {'run_sha256': run['run_sha256'], 'planned_generation': len(calls),
            'generation': dict(generation), 'generation_response_grid_complete': generation_complete,
            'source_review_candidates': dict(source), 'source_review_batches': dict(source_batches),
            'source_review_pending_atoms': pending_atoms,
            'final_answers_saved': len(finals), 'missing_final_answers': len(calls)-len(finals),
            'final_file_grid_complete': len(finals) == len(calls), 'known_indexed_usage': dict(usage),
            'unknown_request_usage': None, 'unique_indexed_response_ids': len(ids),
            'synthetic_run': run['model_config']['synthetic'], 'automatic_model_calls': 0,
            'automatic_resume_allowed': False, 'provider_verified': False,
            'full_integrity_audit_performed': False, 'effectiveness_verified': False,
            'scope': 'Read-only artifact inventory and receipt binding checks; not transmitted-body, semantic, service-state or billing certification. Run the full audits separately.'}


def persistence(evidence, industry, cutoff):
    rows = [r for r in evidence if r.get('kind') == 'survey' and r.get('industry') == industry and
            type(r.get('score')) is int and 0 <= r['score'] <= 10 and au.date_value(r['date']) < cutoff]
    if not rows:
        return 'unknown'
    newest = max(au.date_value(r['date']) for r in rows)
    scores = {r['score'] for r in rows if au.date_value(r['date']) == newest}
    # With conflicting same-time scores there is no defensible unique "last" record.
    return vp.segment(next(iter(scores))) if len(scores) == 1 else 'unknown'


def direction_result(payload, answer, response_protocol=None):
    if answer is None:
        return 'missing', 'unknown'
    try:
        vw.check_common_answer(payload, answer, response_protocol)
    except au.InputError:
        return 'invalid', 'unknown'
    direction = answer['direction']
    return ('abstained' if direction == 'unknown' else 'classified'), direction


def rates(rows):
    counts = Counter(r['state'] for r in rows)
    correct = sum(r['hit'] for r in rows)
    per_user = {}
    for row in rows:
        per_user.setdefault(row['case'], []).append(row['hit'])
    means = [sum(v)/len(v) for v in per_user.values()]
    return {'planned_positions': len(rows), 'users': len(per_user), 'states': dict(counts),
            'correct_positions': correct, 'classified_positions': counts['classified'],
            'coverage': counts['classified']/len(rows) if rows else None,
            'end_to_end_hit_rate': sum(means)/len(means) if means else None,
            'hit_given_classification': correct/counts['classified'] if counts['classified'] else None,
            'per_user_hit_rates': {k: sum(v)/len(v) for k, v in sorted(per_user.items())}}


def attitude(run_dir, judge_dir, phase='original', *, model_phases_ended=False):
    vw.require(phase in ('original', 'source-final'), 'Unknown analysis phase')
    vw.require(model_phases_ended is True, 'Explicit model-phases-ended acknowledgement required before reading hidden outcomes')
    directory, run, calls, prompts = vw.load_run(run_dir)
    vw.require(not (directory/'.plan-trial.lock').exists() and not (directory.parent/'source-review/.lock').exists(), 'Active or stale model lock must be resolved before outcome analysis')
    _, judges = vw.load_judges(judge_dir, run)
    rows = {'individual_memory': []} if run.get('comparison_kind') == vp.MEMORY_COMPARISON else {'individual_memory': [], 'historical_tag_baseline': []}
    baselines = {name: [] for name in ('last_same_industry', 'constant_promoter', 'constant_passive', 'constant_detractor')}
    root = directory.parent
    for cid, call in calls.items():
        if call['question_id'] != 'Q2':
            continue
        case, hidden = call['case'], judges[call['case']]
        cutoff, target = au.date_value(hidden['cutoff_exclusive']), hidden['hidden_segment']
        vw.require(au.date_value(hidden['holdout']['date']) == cutoff, 'Hidden date differs from cutoff')
        vw.require(type(hidden['holdout']['score']) is int and 0 <= hidden['holdout']['score'] <= 10 and
                   target == vp.segment(hidden['holdout']['score']), 'Hidden segment/score mismatch')
        label = next(k for k, v in hidden['condition_map'].items() if v == 'individual_memory')
        history = prompts[f'{case}/{label}/Q2.txt']['payload']['user_context']['evidence']
        vw.require(all(au.date_value(r['date']) < cutoff for r in history), 'Visible Q2 record violates cutoff')
        payload = prompts[call['prompt']]['payload']
        path = root/('incoming' if phase == 'original' else 'source-review')/(cid+('.json' if phase == 'original' else '.final.json'))
        answer = None
        if path.exists():
            envelope = au.read_object(path)
            if phase == 'original':
                vw.validate_response(run, calls, prompts, envelope, check_answer=False)
            else:
                vw.require(envelope.get('call_id') == cid and envelope.get('origin') == 'derived_source_review', 'Unexpected final answer binding')
            answer = envelope.get('answer')
        state, direction = ('invalid', 'unknown') if path.exists() and answer is None else direction_result(payload, answer, run['model_config'].get('transport', {}).get('response_protocol'))
        condition = hidden['condition_map'][call['condition']]
        rows[condition].append({'case': case, 'state': state, 'hit': int(state == 'classified' and direction == target)})
        if condition == 'individual_memory':
            predictions = {'last_same_industry': persistence(history, hidden['holdout']['industry'], cutoff),
                           **{'constant_'+v: v for v in ('promoter', 'passive', 'detractor')}}
            for name, value in predictions.items():
                baselines[name].append({'case': case, 'state': 'abstained' if value == 'unknown' else 'classified', 'hit': int(value == target)})
    results = {k: rates(v) for k, v in (rows | baselines).items()}
    comparisons = {}
    for name, baseline in baselines.items():
        values = {}
        for r in baseline:
            values.setdefault((r['case'], 'historical_tag_baseline'), []).append(r['hit'])
        for r in rows['individual_memory']:
            values.setdefault((r['case'], 'individual_memory'), []).append(r['hit'])
        comparisons[name] = vw.paired_summary(values)
    return {'phase': phase, 'analysis_origin': 'posthoc_descriptive', 'metrics': results,
            'memory_vs_simple_baselines': comparisons, 'automatic_model_calls': 0,
            'synthetic_run': run['model_config']['synthetic'], 'independent_human_review': False,
            'interpretation': 'Strict delivery hits count missing/invalid/unknown as zero. Coverage and conditional hits are separate. Missing finals are not proof about predictive ability. Bootstrap resamples users, not repeats. No efficacy verdict.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('status', 'attitude'))
    p.add_argument('--run-dir', required=True)
    p.add_argument('--judge-dir')
    p.add_argument('--phase', choices=('original', 'source-final'), default='original')
    p.add_argument('--model-phases-ended', action='store_true', help='Acknowledge model phases ended before opening local outcomes')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    try:
        vw.require(args.command != 'attitude' or args.judge_dir, 'Attitude analysis requires local judge material after model phases end')
        result = inventory(args.run_dir) if args.command == 'status' else attitude(args.run_dir, args.judge_dir, args.phase, model_phases_ended=args.model_phases_ended)
        au.write_new(args.output, json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'saved': True, 'automatic_model_calls': 0}))
        return 0
    except (au.InputError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, au.InputError) else type(exc).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
