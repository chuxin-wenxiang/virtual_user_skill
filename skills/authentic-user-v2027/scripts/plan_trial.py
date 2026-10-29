#!/usr/bin/env python3
"""Serial frozen trial execution through the explicitly authorized ChatGPT plan."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import time

import authentic_user as au
import chatgpt_plan as cp
import validation_workflow as vw
import claim_protocol as typed
import attribution_protocol as field_typed
import atomic_protocol as atomic


def execute(run_dir, credential_dir, consent_file):
    # Exclusive creation prevents two processes from racing over the same grid.
    lock = Path(run_dir).expanduser().resolve() / '.plan-trial.lock'
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise cp.PlanStop('Another runner or an unreviewed stale execution lock exists') from None
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'pid': os.getpid(), 'started_unix': time.time()}, stream)
        return _execute(run_dir, credential_dir, consent_file)
    finally:
        lock.unlink(missing_ok=True)


def _execute(run_dir, credential_dir, consent_file):
    directory, run, calls, prompts = vw.load_run(run_dir)
    config = run['model_config']
    vw.require(config['provider'] == 'openai-chatgpt-plan' and not config['synthetic'], 'Real plan config required')
    consent = au.read_object(consent_file)
    vw.require(consent.get('run_sha256') == run['run_sha256'] and consent.get('approved') is True and
               consent.get('destination') == cp.API + '/responses' and
               consent.get('subscription_only') is True and bool(consent.get('human_authorization')), 'Explicit run-bound data transmission consent required')
    transport = config['transport']
    sources=transport.get('execution_sources_sha256',{})
    allowed_sources={'authentic_user.py','claim_protocol.py','chatgpt_plan.py','validation_prep.py','validation_workflow.py','plan_trial.py','trial_audit.py','attribution_protocol.py','attribution_review.py','plan_review.py','source_registry.py','atomic_protocol.py','atomic_review.py'}
    vw.require(isinstance(sources,dict) and set(sources)<=allowed_sources,'Invalid frozen source list')
    def check_sources():
        for name,expected in sources.items():
            vw.require(hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()==expected,'Executing source changed after freeze')
    check_sources()
    output_schema = atomic.schema() if transport.get('response_protocol')=='atomic-bound-v4' else field_typed.schema() if transport.get('response_protocol')=='field-bound-v3' else typed.schema() if transport.get('response_protocol')=='typed-source-v2' else cp.answer_schema()
    vw.require(transport.get('output_schema_sha256') == vw.digest(output_schema), 'Frozen schema differs')
    vw.require(transport.get('concurrency') == 1 and transport.get('automatic_retries') == 0 and
               transport.get('execution_order') == 'paired_interleaved_v1', 'Unsupported execution schedule')
    root = directory.parent
    for name in ('attempts', 'provider-events', 'incoming', 'receipt-index'):
        (root / name).mkdir(exist_ok=True, mode=0o700)
    state_file = root / 'live-status.json'
    state = au.read_object(state_file) if state_file.exists() else {
        'run_sha256': run['run_sha256'], 'planned_calls': len(calls), 'provider_completed': 0,
        'valid_imports': 0, 'structural_failures': 0, 'transport_failures': 0,
        'input_tokens': 0, 'output_tokens': 0, 'paid_fallback_used': False}
    vw.require(state['run_sha256'] == run['run_sha256'], 'Progress belongs to another run')
    client = cp.PlanClient(credential_dir)
    pairs = {}
    for key, call in calls.items():
        pairs.setdefault((call['case'], call['question_id'], call['run']), []).append(key)
    order = []
    for index, pair in enumerate(sorted(pairs, key=lambda p: vw.digest([run['run_sha256'], p]))):
        order.extend(sorted(pairs[pair], reverse=bool(index % 2)))
    state['status'] = 'running'
    cp.atomic_private(state_file, state)
    for key in order:
        check_sources()
        attempt_path = root / 'attempts' / (key + '.json')
        if attempt_path.exists():
            previous = au.read_object(attempt_path)
            vw.require(previous.get('status') in ('imported', 'structural_failure'), 'Uncertain/failed attempt requires review; no automatic retry')
            continue
        call = calls[key]
        attempt = {'call_id': key, 'run_sha256': run['run_sha256'], 'status': 'started', 'started_unix': time.time()}
        # Exclusive attempt and receipt creation are a second barrier after the run lock.
        for pending in (root / 'provider-events' / (key + '.json'), root / 'incoming' / (key + '.json')):
            vw.require(not pending.exists(), 'Existing raw evidence requires review; never overwrite a receipt')
        au.write_new(attempt_path, json.dumps(attempt, ensure_ascii=False, indent=2) + '\n')
        try:
            result = client.respond(config['model'], vw.safe_path(Path(run['input_dir']), call['prompt']).read_text(encoding='utf-8'), transport['adapter_instructions'],
                                    schema=output_schema, max_input_chars=transport['max_input_characters'],
                                    max_output_chars=transport['max_output_characters'])
        except Exception as exc:
            state['transport_failures'] += 1
            state.update(status='stopped_transport', stop_reason=str(exc) if isinstance(exc, au.InputError) else type(exc).__name__)
            attempt.update(status='transport_failure', error=state['stop_reason'])
            if isinstance(exc, cp.PlanStop) and exc.diagnostic:
                cp.atomic_private(root / 'provider-events' / (key + '.json'), exc.diagnostic)
            cp.atomic_private(attempt_path, attempt)
            cp.atomic_private(state_file, state)
            print(json.dumps(state), flush=True)
            return state
        au.write_new(root / 'provider-events' / (key + '.json'), json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        state['provider_completed'] += 1
        usage = result['response'].get('usage', {})
        for field in ('input_tokens', 'output_tokens'):
            state[field] += usage.get(field, 0)
        try:
            envelope = {'call_id': key, 'run_sha256': run['run_sha256'], 'prompt_sha256': call['prompt_sha256'],
                        'model_config_sha256': run['model_config_sha256'], 'origin': 'provider_response',
                        'provider_request_id': result['response']['id'], 'provider_request_id_kind': 'response_id',
                        'model': result['response']['model'], 'revision': config['revision'], 'seed': None,
                        'usage': {k: usage.get(k) for k in ('input_tokens', 'output_tokens')},
                        'answer': json.loads(result['text']), 'live_transport': 'official_siwc_responses',
                        'request_body_sha256': result['request_body_sha256']}
            target = root / 'incoming' / (key + '.json')
            if transport.get('response_protocol') in ('typed-source-v2','field-bound-v3','atomic-bound-v4'):
                wire = envelope['answer']
                try:
                    renderer=atomic if transport.get('response_protocol')=='atomic-bound-v4' else field_typed if transport.get('response_protocol')=='field-bound-v3' else typed
                    envelope['answer'] = renderer.render(prompts[call['prompt']]['payload']['user_context']['evidence'], wire)
                except typed.ProtocolError as exc:
                    envelope['answer'] = {'protocol_version':wire.get('protocol_version'),'wire_answer':wire}
                    envelope['render_error'] = str(exc)
            au.write_new(target, json.dumps(envelope, ensure_ascii=False, indent=2) + '\n')
            index={'call_id':key,'run_sha256':run['run_sha256'],
                   'provider_response_id':result['response']['id'],
                   'receipt_sha256':hashlib.sha256((root/'provider-events'/(key+'.json')).read_bytes()).hexdigest(),
                   'envelope_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
            au.write_new(root/'receipt-index'/(key+'.json'),json.dumps(index,ensure_ascii=False,indent=2)+'\n')
            vw.ingest(directory, target)
            state['valid_imports'] += 1
            attempt['status'] = 'imported'
        except (au.InputError, ValueError, KeyError) as exc:
            state['structural_failures'] += 1
            attempt.update(status='structural_failure', error=str(exc))
        attempt['finished_unix'] = time.time()
        cp.atomic_private(attempt_path, attempt)
        if any(type(usage.get(k)) is not int or usage[k] > limit for k, limit in
               (('input_tokens', config['input_token_limit']), ('output_tokens', transport['reported_output_token_guard']))):
            state.update(status='stopped_usage_guard', stop_reason='Reported token guard exceeded; no new calls')
            cp.atomic_private(state_file, state)
            print(json.dumps(state), flush=True)
            return state
        cp.atomic_private(state_file, state)
        if state['provider_completed'] % 8 == 0:
            print(json.dumps(state), flush=True)
    state['status'] = 'completed' if not state['structural_failures'] else 'completed_with_structural_failures'
    cp.atomic_private(state_file, state)
    print(json.dumps(state), flush=True)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--credential-dir', required=True)
    parser.add_argument('--consent-file', required=True)
    args = parser.parse_args()
    try:
        result = execute(args.run_dir, args.credential_dir, args.consent_file)
        return 0 if result['status'] == 'completed' else 2
    except (au.InputError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'stopped_preflight', 'error': str(exc) if isinstance(exc, au.InputError) else type(exc).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
