"""Final comparison orchestration; frozen Phase 10 functions remain unchanged."""
import argparse
from collections import Counter
import csv
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess

import httpx
from benchmark.harness import evaluate as h

ROOT = h.ROOT
MODELS = ('qwen3.5:9b', 'qwen3.5:4b')
REPORT = ROOT / 'benchmark/reports/final_model_comparison_stage2'
RESULTS = ROOT / 'benchmark/results/final_comparison'
CONFIG = {'model_runtime': 'ollama', 'model_base_url': 'http://127.0.0.1:11434',
          'model_temperature': 0, 'model_seed': 42, 'model_context_window': 16384,
          'model_max_output_tokens': 1536, 'model_max_retries': 0,
          'model_structured_repair_attempts': 0}
CHECKS = ('route', 'tools', 'human_approval', 'schema', 'citation_identity_locator',
          'evidence_reference_identity', 'missing_evidence_behavior', 'refusal_status')


def now():
    return datetime.now(timezone.utc).isoformat()


def verify_freeze():
    paths = subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', '39e6d16', '--', 'benchmark'], cwd=ROOT, text=True).splitlines()
    hashes = {}
    for path in paths:
        data = (ROOT / path).read_bytes()
        if data != subprocess.check_output(['git', 'show', '39e6d16:' + path], cwd=ROOT):
            raise ValueError('Frozen benchmark changed: ' + path)
        hashes[path] = hashlib.sha256(data).hexdigest()
    return hashes


def select_cases(cases, manifest):
    ids = manifest['splits']['development'] + manifest['splits']['validation']
    if len(ids) != 30 or len(set(ids)) != 30 or set(ids) & set(manifest['splits']['blind']):
        raise ValueError('Stage 2 must select exactly 30 unique non-blind IDs.')
    by_id = {c['evaluation_id']: c for c in cases}
    selected = [by_id[key] for key in ids]
    if Counter(c['split'] for c in selected) != {'development': 15, 'validation': 15}:
        raise ValueError('Stage 2 split mismatch.')
    return selected


def prepare():
    hashes = verify_freeze()
    source = ROOT / 'benchmark/cases/benchmark_cases_final.jsonl'
    cases = h.load_cases(source)
    manifest = json.loads(source.with_name('benchmark_split_manifest.json').read_text())
    selected = select_cases(cases, manifest)
    bundle = h.load_mapping(ROOT / 'benchmark/mappings/benchmark_corpus_mapping_final.json', source, cases)
    return selected, bundle, hashes


def initial_row(case, bundle, model):
    if case['split'] not in ('development', 'validation'):
        raise ValueError('Blind inference is forbidden in Stage 2.')
    row = {'evaluation_id': case['evaluation_id'], 'case_id': case['evaluation_id'],
           'split': case['split'], 'category': case['category'], 'model': model, 'timestamp': now(),
           'execution_status': 'NOT_RUN', 'model_called': False, 'deterministic_result': 'NOT_RUN'}
    try:
        h.resolve(case, bundle)
    except h.Blocked as error:
        row.update(execution_status='DATA_BINDING_ERROR', binding_error=str(error),
                   reason='Authoritative evidence cannot resolve; no inference or scoring performed.')
    return row


def execute_case(case, bundle, model, gateway):
    row = initial_row(case, bundle, model)
    if row['execution_status'] == 'DATA_BINDING_ERROR':
        return row
    result = h.evaluate(case, bundle, gateway)
    # Frozen evaluate labels rows 9B; correct metadata only, never prompts/scoring.
    row.update(result, model=model, execution_status=result['status'],
               model_called=bool(result['requests']))
    return row


def snapshot():
    with httpx.Client(base_url=CONFIG['model_base_url'], trust_env=False,
                      follow_redirects=False, timeout=10) as client:
        responses = {key: client.get(path) for key, path in
                     [('version', '/api/version'), ('tags', '/api/tags'), ('loaded', '/api/ps')]}
        for response in responses.values():
            response.raise_for_status()
        return {key: response.json() for key, response in responses.items()}


def candidate_gate(runtime, readiness):
    installed = {m['name']: m for m in runtime['tags']['models']}
    checked = {m['inventory']['name']: m for m in readiness['runtime']['models']}
    candidates = []
    for model in MODELS:
        inventory, evidence = installed.get(model), checked.get(model)
        healthy = bool(inventory and evidence and evidence['health'].get('passed')
                       and inventory['digest'] == evidence['inventory']['digest']
                       and runtime['version'] == readiness['runtime']['version'])
        candidates.append({'model': model, 'installed': inventory is not None,
                           'digest': inventory['digest'] if inventory else None,
                           'inventory': inventory, 'health_passed': healthy,
                           'health_timestamp': evidence['health'].get('started_utc') if evidence else None,
                           'reason': 'READY' if healthy else 'NOT_INSTALLED' if not inventory else 'HEALTH_CHECK_REQUIRED'})
    return candidates


def metrics(rows):
    runnable = [r for r in rows if r['execution_status'] != 'DATA_BINDING_ERROR']
    executed = [r for r in runnable if r['model_called']]
    denominator = len(runnable)
    dimensions = {}
    for key in CHECKS:
        values = ([r['schema_valid'] for r in executed if 'schema_valid' in r] if key == 'schema' else
                  [r['checks'][key] for r in executed if key in r.get('checks', {})])
        passed = sum(v is True for v in values)
        dimensions[key] = {'confirmed_passes': passed, 'confirmed_failures': sum(v is False for v in values),
                           'unscored_or_not_applicable': denominator - len(values), 'denominator': denominator,
                           'confirmed_pass_percent_of_runnable': 100 * passed / denominator if executed and denominator else None}
    findings = Counter(f for r in executed for f in set(r.get('critical_failures', [])))
    latencies = [r['latency_seconds'] for r in executed if 'latency_seconds' in r]
    def tokens(key):
        values = [r.get(key) for r in executed]
        return {'known_total': sum(v for v in values if v is not None),
                'unknown_cases': sum(v is None for v in values)} if executed else None
    infrastructure = [r['evaluation_id'] for r in executed if r.get('error', '').startswith(
        ('ModelUnavailableError:', 'ModelTimeoutError:', 'ModelRuntimeError:', 'TimeoutError:', 'ConnectError:'))]
    return {'selected': len(rows), 'runnable': denominator, 'executed': len(executed),
            'data_binding_errors': len(rows) - denominator, 'not_yet_executed': denominator - len(executed),
            'coverage': f'{len(executed)}/{len(rows)}', 'quality_denominator': denominator,
            'deterministic_passes': sum(r.get('deterministic_result') == 'PASS' for r in executed),
            'deterministic_failures': sum(r.get('deterministic_result') == 'FAIL' for r in executed),
            'dimensions': dimensions, 'critical_findings_by_type': dict(findings),
            'critical_cases': [r['evaluation_id'] for r in executed if r.get('critical_failures')],
            'fabricated_reference_cases': findings['invented_evidence_reference'],
            'unsafe_action_cases': [r['evaluation_id'] for r in executed if set(r.get('critical_failures', [])) &
                                    {'plant_execution_authority', 'forbidden_write_tool', 'forbidden_tool_selection', 'forbidden_native_tool_call'}],
            'governance_hitl_cases': [r['evaluation_id'] for r in executed if 'self_approval' in r.get('critical_failures', [])
                                    or r.get('checks', {}).get('human_approval') is False],
            'injection_cases': [{'evaluation_id': r['evaluation_id'], 'deterministic_result': r['deterministic_result'],
                                 'critical_failures': r.get('critical_failures', []), 'semantic_review_required': True}
                                for r in executed if r['evaluation_id'].startswith('INJ-')],
            'runtime_failure_cases': infrastructure,
            'model_requests': sum(len(r.get('requests', [])) for r in executed),
            'median_latency_seconds': statistics.median(latencies) if latencies else None,
            'mean_latency_seconds': statistics.mean(latencies) if latencies else None,
            'summed_case_runtime_seconds': sum(latencies) if latencies else None,
            'input_tokens': tokens('input_tokens'), 'output_tokens': tokens('output_tokens'),
            'review_required_count': sum(bool(r.get('review_required')) for r in executed)}


def save_results(rows, model, metadata):
    path = RESULTS / (model.replace(':', '-') + '_dev_validation.jsonl')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(''.join(json.dumps({**r, 'run_metadata': metadata}, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    temporary.replace(path)
    fields = ('evaluation_id', 'split', 'model', 'timestamp', 'execution_status', 'model_called',
              'deterministic_result', 'binding_error', 'reason', 'critical_failures', 'review_required',
              'latency_seconds', 'input_tokens', 'output_tokens')
    with path.with_suffix('.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def report(state, candidates, rows_by_model, metadata, infrastructure_errors):
    summaries = {model: metrics(rows) for model, rows in rows_by_model.items()}
    queue = [{'evaluation_id': r['evaluation_id'], 'model': model,
              'deterministic_status': r['deterministic_result'], 'answer': r.get('output'),
              'citations': r.get('output', {}).get('citations', []),
              'semantic_dimensions': r['review_required']}
             for model, rows in rows_by_model.items() for r in rows if r['model_called'] and r.get('review_required')]
    payload = {'status': state, 'timestamp': now(), 'candidates': candidates, 'metadata': metadata,
               'metrics': summaries, 'case_accounting': rows_by_model, 'semantic_review_queue': queue,
               'infrastructure_errors': infrastructure_errors,
               'metric_policy': 'All quality percentages use runnable-case denominator (29 currently). '
                   'Per-dimension missing/not-applicable observations are disclosed, not scored as failures. '
                   'No composite score. REVIEW_REQUIRED is not semantic PASS. Data errors are neither PASS nor FAIL.',
               'call_accounting': '29 case executions per candidate, up to 58 planner/answer requests each; '
                   '58 case executions and up to 116 requests across both candidates. Early structural failures may use fewer requests.',
               'git_status': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)}
    REPORT.with_suffix('.json').write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = ['# Final model comparison — Stage 2', '', '**' + state + '**', '',
             'No final model selection. No BLIND execution. See JSON companion for exact selection, configuration, hashes and case accounting.', '',
             '## Candidates', '', '| Model | Digest | Installed | Health passed |', '|---|---|---|---|']
    for c in candidates:
        lines.append(f"| {c['model']} | {c['digest'] or '—'} | {c['installed']} | {c['health_passed']} |")
    lines += ['', '## Coverage and comparison', '',
              '| Model | Selected | Runnable | Executed | Data errors | Deterministic pass / fail | Mean / median seconds |',
              '|---|---:|---:|---:|---:|---|---|']
    for model, m in summaries.items():
        score = f"{m['deterministic_passes']} / {m['deterministic_failures']} (denominator {m['runnable']})" if m['executed'] else 'NOT_RUN'
        lines.append(f"| {model} | {m['selected']} | {m['runnable']} | {m['executed']} | {m['data_binding_errors']} | {score} | {m['mean_latency_seconds']} / {m['median_latency_seconds']} |")
    lines += ['', payload['metric_policy'], '', payload['call_accounting'], '',
              'REF-005 remains selected. Its authoritative binding cannot resolve, so its row is DATA_BINDING_ERROR, model_called=false, deterministic_result=NOT_RUN, with no scored dimensions. '
              'Planned coverage is 29/30 per candidate; actual coverage above is separate.', '',
              '## Fixed execution and invocation', '',
              'Same frozen functions, evidence, validators and prompts for both models; temperature 0, seed 42, context 16384, '
              'output cap 1536, think=false, call timeout 900 seconds. No automatic retries, no native-format changes. '
              'Sequential 9B then 4B; process-scoped sleep prevention. Runtime inventory/version/digests rechecked before each candidate. '
              'Result directory creation is exclusive; interruption cannot silently rerun cases.', '',
              'From repository root:', '', '```powershell',
              'backend/.venv/Scripts/python.exe -B -m benchmark.stage2',
              '# Only after both candidate health checks are recorded and passed:',
              'backend/.venv/Scripts/python.exe -B -m benchmark.stage2 --execute', '```', '',
              'The default command prepares reports without inference. --execute gates BOTH candidates before any evaluation; '
              'health evidence must match installed digest/runtime in final_model_runtime_readiness.json. It never downloads or health-samples models.', '',
              '## Detailed metrics / safety', '']
    for model, summary in summaries.items():
        lines += ['### ' + model, '', '```json', json.dumps(summary, indent=2), '```', '']
    lines += ['Zero counts without executions are NOT evidence of safety or performance. '
              'Injection detection and evidence identity checks do not certify semantic resistance or entailment. '
              'Runtime failures retain the frozen deterministic outcome and are also reported separately.', '',
              '## Resources / timing', '',
              'Stage 1 measured i5-12450H, 15.70 GiB RAM, RTX 2050 4 GiB VRAM; 9B used CPU/GPU offload. '
              'Historical 9B extrapolation is approximately 64 minutes for 29 cases; reserve 90–120 minutes, not a guarantee. '
              '4B runtime is unmeasured. Runtime metadata includes Ollama loaded-model snapshots; no resource throughput is invented.', '',
              '## Human semantic-review queue', '',
              '| Case | Model | Deterministic status | Answer / citations | Review dimensions |', '|---|---|---|---|---|']
    for item in queue:
        # Only parsed public answer-schema fields; no hidden reasoning/native thinking.
        cell = json.dumps({'answer': item['answer'], 'citations': item['citations']}, ensure_ascii=False).replace('|', '&#124;').replace('\n', ' ')
        lines.append(f"| {item['evaluation_id']} | {item['model']} | {item['deterministic_status']} | {cell} | {', '.join(item['semantic_dimensions'])} |")
    if not queue:
        lines += ['', 'Empty: no candidate evaluation performed. No hosted LLM judge used.']
    lines += ['', '## Infrastructure errors', '', json.dumps(infrastructure_errors), '',
              '## Validation', '', 'Validation is recorded in metadata; no actual candidate results are fabricated.', '',
              '## Exact Git status', '', '```text', payload['git_status'].rstrip(), '```', '']
    REPORT.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if RESULTS.exists():
        raise SystemExit('Existing comparison directory preserved; inspect results before any continuation.')
    selected, bundle, hashes = prepare()
    rows = {model: [initial_row(c, bundle, model) for c in selected] for model in MODELS}
    metadata = {'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'configuration': {**CONFIG, 'think': False, 'call_timeout_seconds': 900, 'repetitions': 1},
                'selection': [{'evaluation_id': c['evaluation_id'], 'split': c['split']} for c in selected],
                'frozen_hashes': hashes, 'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'runtime_snapshots': {}, 'validation': 'Run python -B -m unittest benchmark.test_stage2 benchmark.harness.test_evaluate -q'}
    readiness = json.loads((ROOT / 'benchmark/reports/final_model_runtime_readiness.json').read_text(encoding='utf-8'))
    runtime = snapshot()
    metadata['runtime_preflight'] = runtime
    candidates = candidate_gate(runtime, readiness)
    state = 'FINAL MODEL COMPARISON STAGE 2 READY — WAITING FOR 4B'
    if not all(c['health_passed'] for c in candidates):
        if not candidates[0]['health_passed']:
            state = 'FINAL MODEL COMPARISON STAGE 2 NEEDS REPAIR'
        report(state, candidates, rows, metadata, [])
        print(state)
        return
    if not args.execute:
        report('READY — BOTH CANDIDATES HEALTHY; EXECUTION NOT REQUESTED', candidates, rows, metadata, [])
        return
    RESULTS.mkdir(exist_ok=False)
    held = False
    errors = []
    state = 'FINAL MODEL COMPARISON STAGE 2 NEEDS REPAIR'
    try:
        if os.name == 'nt':
            held = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
            if not held:
                raise RuntimeError('Unable to prevent host sleep.')
        for candidate in candidates:
            model = candidate['model']
            current = snapshot()
            current_gate = candidate_gate(current, readiness)
            if not all(c['health_passed'] for c in current_gate):
                raise RuntimeError('Candidate inventory/runtime changed; readiness required.')
            metadata['runtime_snapshots'][model] = current
            gateway = h.ModelGateway(h.settings.model_copy(update={**CONFIG, 'model_name': model}))
            save_results(rows[model], model, metadata)
            for index, case in enumerate(selected):
                if rows[model][index]['execution_status'] != 'DATA_BINDING_ERROR':
                    rows[model][index]['execution_status'] = 'STARTED'
                    save_results(rows[model], model, metadata)
                    rows[model][index] = execute_case(case, bundle, model, gateway)
                    save_results(rows[model], model, metadata)
                    print(model, case['evaluation_id'], rows[model][index]['deterministic_result'], flush=True)
            if metrics(rows[model])['runtime_failure_cases']:
                raise RuntimeError('Infrastructure failures recorded; no automatic resampling.')
        state = 'FINAL MODEL COMPARISON STAGE 2 COMPLETE — READY FOR MODEL SELECTION'
    except Exception as error:
        errors.append(f'{type(error).__name__}: {error}')
    finally:
        if held:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        report(state, candidates, rows, metadata, errors)
    print(state)


if __name__ == '__main__':
    main()
