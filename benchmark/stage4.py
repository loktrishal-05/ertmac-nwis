"""One-time BLIND orchestration around the unchanged frozen evaluator."""
import argparse
from collections import Counter
import csv
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess

import httpx
from benchmark import stage2 as s
from app.services.model_gateway import GenerationResult

ROOT = s.ROOT
MODEL = 'qwen3.5:9b'
RESULTS = ROOT / 'benchmark/results/final_blind'
REPORT = ROOT / 'benchmark/reports/final_blind_evaluation_stage4'
TERMINAL = {'COMPLETED', 'STRUCTURAL_ERROR', 'DATA_BINDING_ERROR'}
INFRA = ('ModelUnavailableError:', 'ModelTimeoutError:', 'ModelRuntimeError:',
         'TimeoutError:', 'ConnectError:')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, text):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def save(rows):
    atomic(RESULTS / 'qwen3_5_9b_blind.jsonl', ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    import io
    output = io.StringIO(newline='')
    fields = sorted({k for r in rows for k in r})
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    atomic(RESULTS / 'qwen3_5_9b_blind.csv', output.getvalue())


def initial(case, bundle):
    if case['split'] != 'blind':
        raise ValueError('Only BLIND is authorized.')
    row = {k: case[k] for k in ('evaluation_id', 'category', 'category_id', 'split')}
    row.update(model=MODEL, execution_status='NOT_RUN', model_called=False,
               deterministic_result='NOT_RUN', timestamp=s.now())
    try:
        s.h.resolve(case, bundle)
    except s.h.Blocked as error:
        row.update(execution_status='DATA_BINDING_ERROR', binding_error=str(error))
    return row


def prepare():
    stage3 = json.loads((ROOT / 'benchmark/reports/final_model_selection_stage3.json').read_text(encoding='utf-8'))
    assert stage3['roles']['primary_company_server_model'] == MODEL
    config = stage3['stage4_configuration']
    assert (config['model_temperature'], config['model_seed'], config['model_context_window']) == (0, 42, 16384)
    assert all(config[k] == v for k, v in s.CONFIG.items())
    hashes = s.verify_freeze()
    assert hashes == stage3['frozen_file_sha256']
    assert digest(ROOT / 'benchmark/stage2.py') == config['stage2_runner_sha256']
    for name, expected in stage3['source_artifact_sha256'].items():
        assert digest(ROOT / name) == expected, name
    source = ROOT / 'benchmark/cases/benchmark_cases_final.jsonl'
    # Only the program consumes case definitions; never print prompts or expectations.
    cases = s.h.load_cases(source)
    manifest = json.loads(source.with_name('benchmark_split_manifest.json').read_text(encoding='utf-8'))
    ids = manifest['splits']['blind']
    assert len(ids) == len(set(ids)) == 45
    assert not set(ids) & set(manifest['splits']['development'] + manifest['splits']['validation'])
    by_id = {c['evaluation_id']: c for c in cases}
    selected = [by_id[key] for key in ids]
    assert Counter(c['category_id'] for c in selected) == dict.fromkeys('ABCDEFGHIJKLMNO', 3)
    bundle = s.h.load_mapping(ROOT / 'benchmark/mappings/benchmark_corpus_mapping_final.json', source, cases)
    rows = [initial(c, bundle) for c in selected]
    assert {r['evaluation_id'] for r in rows if r['execution_status'] == 'DATA_BINDING_ERROR'} == {'JSON-004', 'HITL-003'}
    assert sum(r['execution_status'] == 'NOT_RUN' for r in rows) == 43
    return selected, bundle, rows, stage3


def power():
    class Status(ctypes.Structure):
        _fields_ = [('ac', ctypes.c_ubyte), ('flag', ctypes.c_ubyte), ('percent', ctypes.c_ubyte),
                    ('reserved', ctypes.c_ubyte), ('life', ctypes.c_ulong), ('full', ctypes.c_ulong)]
    status = Status()
    assert ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)) and status.ac == 1, 'AC power required'
    return {'ac_connected': True, 'battery_percent': status.percent}


def preflight(stage3):
    postgres = subprocess.check_output(['docker', 'compose', '-f', 'infra/docker-compose.yml', 'exec', '-T',
                                        'postgres', 'pg_isready', '-U', 'postgres', '-d', 'sovereign_workbench'], cwd=ROOT, text=True)
    with httpx.Client(trust_env=False, timeout=15) as client:
        qdrant = client.get('http://127.0.0.1:6333/healthz')
        qdrant.raise_for_status()
    runtime = s.snapshot()
    candidate = next(x for x in runtime['tags']['models'] if x['name'] == MODEL)
    assert candidate['digest'] == stage3['stage4_configuration']['model_digest']
    assert runtime['version'] == stage3['stage4_configuration']['runtime_version']
    return {'postgres': postgres.strip(), 'qdrant': qdrant.text, 'ollama': runtime, 'power': power()}


class JournalGateway:
    """Durable per-request responses allow crash recovery without resampling completed calls."""
    def __init__(self, gateway, path):
        self.gateway, self.path, self.index = gateway, path, 0
        self.events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

    def append(self, event):
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        self.events.append(event)

    def generate_text(self, **kwargs):
        index = self.index
        self.index += 1
        serial = {k: [m.model_dump(mode='json') for m in v] if k == 'messages' else v for k, v in kwargs.items()}
        fingerprint = hashlib.sha256(json.dumps(serial, sort_keys=True).encode()).hexdigest()
        existing = [e for e in self.events if e['index'] == index]
        if existing:
            assert existing[0]['request_sha256'] == fingerprint, 'Frozen request changed'
            done = [e for e in existing if e['event'] == 'completed']
            if done:
                return GenerationResult.model_validate(done[-1]['result'])
            # An interrupted call may have completed server-side. Never silently repeat it.
            raise RuntimeError('Unfinished journal request requires explicit infrastructure investigation; no automatic retry.')
        self.append({'event': 'started', 'index': index, 'timestamp': s.now(), 'model': MODEL, 'request_sha256': fingerprint})
        try:
            result = self.gateway.generate_text(**kwargs)
        except Exception as error:
            self.append({'event': 'error', 'index': index, 'timestamp': s.now(), 'error': f'{type(error).__name__}: {error}'})
            raise
        self.append({'event': 'completed', 'index': index, 'timestamp': s.now(), 'result': result.model_dump(mode='json')})
        return result


def references(value):
    found = []
    for item in s.h.walk(value):
        if 'evidence_id' in item:
            found.append(item['evidence_id'])
        for key in ('supporting_evidence', 'contradicting_evidence', 'evidence_basis'):
            if isinstance(item.get(key), list):
                found.extend(item[key])
    return found


def metrics(rows):
    result = s.metrics(rows)
    executed = [r for r in rows if r['model_called']]
    result['critical_failure_count'] = len(result['critical_cases'])
    result['schema_failures'] = sum(r.get('schema_valid') is False for r in executed)
    result['citation_reference_failures'] = sum(r.get('citation_reference_valid') is False for r in executed)
    result['unsupported_ocr_safety_proof_cases'] = [r['evaluation_id'] for r in executed if set(r.get('critical_failures', [])) &
                                                  {'ocr_claimed_verified', 'ocr_proof_of_field_state', 'unsupported_valve_state_from_ocr'}]
    result['fabricated_safety_citation_cases'] = [r['evaluation_id'] for r in executed if r['category_id'] in ('E', 'K') and
        any(c['evidence_id'] not in {e['evidence_id'] for es in r.get('tool_results', {}).values() for e in es}
            for c in r.get('output', {}).get('citations', []))]
    result['injection_sentinel_failures'] = sum('injection_sentinel_compliance' in r.get('critical_failures', []) for r in executed)
    result['injection_deterministic_failures'] = sum(r['deterministic_result'] == 'FAIL' for r in executed if r['category_id'] == 'J')
    return result


def report(rows, metadata):
    complete = all(r['execution_status'] in TERMINAL for r in rows)
    summary = metrics(rows) if complete else None
    queue, critical = [], []
    if complete:
        for row in rows:
            if row.get('review_required'):
                queue.append({'evaluation_id': row['evaluation_id'], 'category': row['category'],
                    'deterministic_result': row['deterministic_result'], 'final_answer': row.get('output', row.get('answer_raw_response')),
                    'references': row.get('evidence_references', []), 'semantic_dimensions': row['review_required'],
                    'reference_note': 'Parsed output references only; schema failures may require inspection of raw answer.'})
            if row.get('critical_failures'):
                supplied = {e['evidence_id'] for es in row.get('tool_results', {}).values() for e in es}
                invalid = [ref for ref in row.get('evidence_references', []) if ref not in supplied]
                critical.append({'evaluation_id': row['evaluation_id'], 'category': row['category'], 'classification': 'MODEL_BEHAVIOR',
                    'failure_types': row['critical_failures'], 'what_happened': {'invalid_reference_values': invalid,
                    'frozen_detector_findings': row['critical_failures'], 'final_answer': row.get('output', row.get('answer_raw_response'))},
                    'evidence_available_to_model': bool(supplied), 'supplied_evidence_ids': sorted(supplied),
                    'route': row.get('route'), 'tools': row.get('tools')})
    categories = {key: {'category': next(r['category'] for r in rows if r['category_id'] == key),
                       **metrics([r for r in rows if r['category_id'] == key])} for key in 'ABCDEFGHIJKLMNO'} if complete else {}
    state = 'STAGE 4 ONE-TIME BLIND EVALUATION COMPLETE' if complete else 'STAGE 4 INCOMPLETE — RESUME ONLY UNFINISHED CASES'
    payload = {'status': state, 'metadata': metadata, 'coverage': {'selected': len(rows), 'runnable': 43,
        'executed': sum(r['model_called'] for r in rows), 'data_binding_errors': 2}, 'metrics': summary,
        'category_results': categories, 'critical_failure_analysis': critical, 'semantic_review_queue': queue,
        'data_binding_errors': [r for r in rows if r['execution_status'] == 'DATA_BINDING_ERROR'],
        'infrastructure_anomalies': metadata.get('infrastructure_anomalies', []),
        'metric_policy': 'Frozen deterministic outcomes only. REVIEW_REQUIRED is never semantic PASS. Missing dimension checks remain unscored/N/A. '
            'Critical counts are affected cases. Empty evidence IDs retain frozen invented-reference findings. '
            'Safety counters are detector observations, not semantic certification; fabricated safety citations counts invalid citation IDs in E/K cases. '
            'Approval mismatches include both missing and unnecessary approval. Injection case failures are distinct from sentinel compliance. '
            'Runtime is summed case latency, not elapsed wall time. No hosted judge or post-BLIND tuning.',
        'files_created': ['benchmark/stage4.py', 'benchmark/test_stage4.py', *[str(p.relative_to(ROOT)).replace('\\', '/') for p in sorted(RESULTS.rglob('*')) if p.is_file()],
                          'benchmark/reports/final_blind_evaluation_stage4.md', 'benchmark/reports/final_blind_evaluation_stage4.json']}
    REPORT.with_suffix('.md').touch(exist_ok=True)
    REPORT.with_suffix('.json').touch(exist_ok=True)
    payload['exact_git_status'] = subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)
    atomic(REPORT.with_suffix('.json'), json.dumps(payload, indent=2, ensure_ascii=False) + '\n')
    lines = ['# One-time BLIND evaluation — Stage 4', '', '**' + state + '**', '', payload['metric_policy'], '',
             'JSON-004 and HITL-003: DATA_BINDING_ERROR, model_called=false, deterministic_result=NOT_RUN. No bounded source window was invented.', '',
             '## Runtime provenance and integrity', '', '```json', json.dumps(metadata, indent=2), '```', '',
             '## Coverage and deterministic/safety/runtime metrics', '', '```json', json.dumps(summary, indent=2), '```', '',
             '## Category results', '', '| Category | Selected | Executed | Data errors | PASS | FAIL | Critical | Review |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key, m in categories.items():
        lines.append(f"| {key}. {m['category']} | {m['selected']} | {m['executed']} | {m['data_binding_errors']} | {m['deterministic_passes']} | {m['deterministic_failures']} | {m['critical_failure_count']} | {m['review_required_count']} |")
    for title, data in [('Critical failures (separate safety evidence)', critical), ('Semantic review queue', queue),
                        ('Infrastructure anomalies', payload['infrastructure_anomalies']), ('Exact files created', payload['files_created'])]:
        lines += ['', '## ' + title, '', '```json', json.dumps(data, indent=2, ensure_ascii=False), '```']
    lines += ['', '## Exact Git status', '', '```text', payload['exact_git_status'].rstrip(), '```', '']
    atomic(REPORT.with_suffix('.md'), '\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--report', action='store_true')
    args = parser.parse_args()
    cases, bundle, rows, stage3 = prepare()
    if args.report:
        metadata = json.loads((RESULTS / 'metadata.json').read_text(encoding='utf-8'))
        rows = [json.loads(line) for line in (RESULTS / 'qwen3_5_9b_blind.jsonl').read_text(encoding='utf-8').splitlines()]
        report(rows, metadata)
        return
    health = preflight(stage3)
    print('Preflight passed: 45 selected, 43 runnable, JSON-004/HITL-003 binding errors; services healthy; AC connected.', flush=True)
    if not args.execute:
        return
    subprocess.run([str(ROOT / 'backend/.venv/Scripts/python.exe'), '-B', '-m', 'unittest',
                    'benchmark.test_stage2', 'benchmark.harness.test_evaluate', 'benchmark.test_stage4', '-q'], cwd=ROOT, check=True)
    protected = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / 'benchmark/results').rglob('*') if p.is_file() and not p.is_relative_to(RESULTS)}
    protected.update({str(p.relative_to(ROOT)): digest(p) for p in (ROOT / 'benchmark/reports').glob('final_model*stage[23].*')})
    if RESULTS.exists():
        metadata = json.loads((RESULTS / 'metadata.json').read_text(encoding='utf-8'))
        assert metadata['runner_sha256'] == digest(Path(__file__)), 'Runner changed after starting BLIND'
        assert metadata['protected_sha256'] == protected
        rows = [json.loads(line) for line in (RESULTS / 'qwen3_5_9b_blind.jsonl').read_text(encoding='utf-8').splitlines()]
        assert [r['evaluation_id'] for r in rows] == [c['evaluation_id'] for c in cases]
        assert not any(r['execution_status'] == 'INFRASTRUCTURE_ERROR' for r in rows), 'Investigate recorded infrastructure failure before resume'
    else:
        RESULTS.mkdir(exist_ok=False)
        metadata = {'started_utc': s.now(), 'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                    'benchmark_sha256': stage3['stage2_benchmark_sha256'], 'configuration': stage3['stage4_configuration'],
                    'model': MODEL, 'digest': stage3['stage4_configuration']['model_digest'], 'preflight': health,
                    'runner_sha256': digest(Path(__file__)), 'protected_sha256': protected, 'infrastructure_anomalies': []}
        atomic(RESULTS / 'metadata.json', json.dumps(metadata, indent=2) + '\n')
        save(rows)
    gateway = s.h.ModelGateway(s.h.settings.model_copy(update={**s.CONFIG, 'model_name': MODEL}))
    held = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
    assert held, 'Sleep prevention unavailable'
    try:
        for index, case in enumerate(cases):
            if rows[index]['execution_status'] in TERMINAL:
                continue
            power()
            rows[index]['execution_status'] = 'STARTED'
            save(rows)
            journal = JournalGateway(gateway, RESULTS / (case['evaluation_id'] + '.requests.jsonl'))
            result = s.h.evaluate(case, bundle, journal)
            result.update(execution_status=result['status'], model_called=bool(result['requests']),
                          parsed_plan={'route': result['route'], 'tools': result['tools']} if 'route' in result else None,
                          parsed_final_answer=result.get('output'), evidence_references=references(result.get('output')),
                          runtime_metadata={'model': MODEL, 'digest': metadata['digest'], 'configuration': metadata['configuration']})
            rows[index].update(result)
            if result.get('error', '').startswith(INFRA) or 'Unfinished journal request' in result.get('error', ''):
                rows[index]['execution_status'] = 'INFRASTRUCTURE_ERROR'
                metadata['infrastructure_anomalies'].append({'evaluation_id': case['evaluation_id'], 'classification': 'RUNTIME_ERROR', 'error': result['error']})
            save(rows)
            atomic(RESULTS / 'metadata.json', json.dumps(metadata, indent=2) + '\n')
            if rows[index]['execution_status'] == 'INFRASTRUCTURE_ERROR':
                raise RuntimeError('Infrastructure failure checkpointed; no automatic retry.')
            count = sum(r['model_called'] for r in rows)
            if count % 10 == 0 or count == 43:
                print(f'Checkpoint: {count}/43 runnable cases persisted; no outcomes exposed.', flush=True)
        assert sum(r['model_called'] for r in rows) == 43
        assert all(r['model'] == MODEL for r in rows)
        assert all(digest(ROOT / p) == value for p, value in protected.items())
        assert s.verify_freeze() == stage3['frozen_file_sha256']
        subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
        metadata.update(completed_utc=s.now(), final_integrity={'frozen_files_unchanged': True,
            'dev_validation_and_stage2_stage3_unchanged': True, 'only_9b_blind_calls': True,
            '4b_blind_calls': 0, 'relevant_tests_passed_before_inference': True, 'git_diff_check_passed': True,
            'no_post_blind_tuning': True, 'no_completed_case_rerun': True})
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        atomic(RESULTS / 'metadata.json', json.dumps(metadata, indent=2) + '\n')
        report(rows, metadata)
    print('STAGE 4 ONE-TIME BLIND EVALUATION COMPLETE', flush=True)


if __name__ == '__main__':
    main()
