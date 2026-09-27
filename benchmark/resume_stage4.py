"""Explicitly authorized one-time infrastructure recovery; frozen runner unchanged."""
import hashlib
import json
import subprocess
import sys
from collections import Counter

from benchmark import stage4 as s

OriginalJournal = s.JournalGateway
TARGET = 'SYN-004'
REMAINING = {TARGET, 'PID-002', 'PID-003', 'PID-004', 'SNS-001', 'SNS-003', 'SNS-004'}


class RecoveryJournal(OriginalJournal):
    def generate_text(self, **kwargs):
        events = [e for e in self.events if e['index'] == self.index]
        authorization = next((e for e in events if e['event'] == 'reconciliation'), None)
        if authorization and not any(e['event'] == 'completed' for e in events):
            assert authorization['retry_authorized'] and authorization['retry_number'] == 1
            serial = {k: [m.model_dump(mode='json') for m in v] if k == 'messages' else v for k, v in kwargs.items()}
            fingerprint = hashlib.sha256(json.dumps(serial, sort_keys=True).encode()).hexdigest()
            assert events[0]['request_sha256'] == fingerprint, 'Frozen request changed'
            # The retry journal refuses another call after any unresolved retry start.
            retry = OriginalJournal(self.gateway, self.path.with_suffix('.retry1.jsonl'))
            result = retry.generate_text(**kwargs)
            self.append({'event': 'completed', 'index': self.index, 'timestamp': s.s.now(),
                         'recovery_retry': 1, 'result': result.model_dump(mode='json')})
            self.index += 1
            return result
        return super().generate_text(**kwargs)


def read_rows():
    return [json.loads(x) for x in (s.RESULTS / 'qwen3_5_9b_blind.jsonl').read_text(encoding='utf-8').splitlines()]


def main():
    rows = read_rows()
    assert Counter(r['execution_status'] for r in rows) == {
        'COMPLETED': 32, 'STRUCTURAL_ERROR': 4, 'DATA_BINDING_ERROR': 2, 'STARTED': 1, 'NOT_RUN': 6}
    assert {r['evaluation_id'] for r in rows if r['execution_status'] not in s.TERMINAL} == REMAINING
    preserved = {r['evaluation_id']: r for r in rows if r['execution_status'] in s.TERMINAL}
    journals = {p.name: p.read_bytes() for p in s.RESULTS.glob('*.requests.jsonl')}
    assert not list(s.RESULTS.glob('*.tmp')), 'Investigate temporary results'
    assert not list(s.RESULTS.glob('*.retry1.jsonl')), 'Recovery already attempted'
    for case_id in REMAINING - {TARGET}:
        assert case_id + '.requests.jsonl' not in journals
    check = subprocess.check_output(['powershell', '-NoProfile', '-Command',
        "@{python=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'python' } | Select-Object ProcessId,ParentProcessId,CommandLine); connections=@(Get-NetTCPConnection -LocalPort 11434 -State Established -ErrorAction SilentlyContinue)} | ConvertTo-Json -Depth 4"], text=True)
    process_state = json.loads(check)
    import os
    assert all(p['ProcessId'] in (os.getpid(), os.getppid()) for p in process_state['python']), process_state
    assert not process_state['connections'], 'Active Ollama connection'
    _, _, _, stage3 = s.prepare()
    health = s.preflight(stage3)
    metadata = json.loads((s.RESULTS / 'metadata.json').read_text(encoding='utf-8'))
    assert s.digest(s.ROOT / 'benchmark/stage4.py') == metadata['runner_sha256']
    assert all(s.digest(s.ROOT / p) == v for p, v in metadata['protected_sha256'].items())
    subprocess.run([sys.executable, '-B', '-m', 'unittest', 'benchmark.test_stage4', 'benchmark.test_resume_stage4', '-q'], check=True)
    path = s.RESULTS / (TARGET + '.requests.jsonl')
    journal = OriginalJournal(None, path)
    pending = [e for e in journal.events if e['event'] == 'started' and not any(
        x['index'] == e['index'] and x['event'] in ('completed', 'error') for x in journal.events)]
    assert len(pending) == 1 and pending[0]['index'] == 1
    assert not any(e['event'] == 'reconciliation' for e in journal.events)
    record = {'event': 'reconciliation', 'index': pending[0]['index'], 'evaluation_id': TARGET,
        'timestamp': s.s.now(), 'original_request_start_timestamp': pending[0]['timestamp'],
        'request_sha256': pending[0]['request_sha256'], 'no_active_stage4_process': True,
        'no_active_ollama_connection': True, 'no_recoverable_response': True,
        'classification': 'INFRASTRUCTURE_INTERRUPTED_UNRECOVERABLE',
        'retry_authorized': True, 'retry_number': 1, 'reason': 'infrastructure recovery only',
        'disclosure': 'An earlier request may have reached the model but no response was persisted or recoverable.',
        'possible_unobserved_prior_completed_response': 'UNKNOWN'}
    journal.append(record)
    metadata['infrastructure_anomalies'].append(record)
    metadata['authorized_recovery'] = {'prior_terminal_ids': sorted(preserved.keys() - {'JSON-004', 'HITL-003'}),
        'unfinished_ids': sorted(REMAINING), 'preflight': health,
        'original_journal_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in journals.items()},
        'prior_records_sha256': {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest() for k, v in preserved.items()}}
    s.atomic(s.RESULTS / 'metadata.json', json.dumps(metadata, indent=2) + '\n')
    s.JournalGateway = RecoveryJournal
    sys.argv = ['benchmark.stage4', '--execute']
    s.main()
    final = read_rows()
    assert all(r['execution_status'] in s.TERMINAL for r in final)
    assert sum(r['model_called'] for r in final) == 43
    assert all(next(r for r in final if r['evaluation_id'] == k) == v for k, v in preserved.items())
    for name, content in journals.items():
        actual = (s.RESULTS / name).read_bytes()
        assert actual.startswith(content) if name == path.name else actual == content
    starts = []
    for p in s.RESULTS.glob('*.requests*.jsonl'):
        events = [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()]
        starts.extend(e for e in events if e['event'] == 'started')
        if p.name.startswith(tuple(REMAINING - {TARGET})):
            counts = Counter((e['index'], e['event']) for e in events)
            assert all(v == 1 for v in counts.values())
            assert sum(e['event'] == 'started' for e in events) == sum(e['event'] == 'completed' for e in events)
    assert all(e['model'] == s.MODEL for e in starts)
    retry_events = [json.loads(x) for x in path.with_suffix('.retry1.jsonl').read_text(encoding='utf-8').splitlines()]
    assert Counter(e['event'] for e in retry_events) == {'started': 1, 'completed': 1}
    subprocess.run([sys.executable, '-B', '-m', 'unittest', 'benchmark.test_stage4', 'benchmark.test_resume_stage4', '-q'], check=True)
    subprocess.run(['git', 'diff', '--check'], check=True)
    s.prepare()
    metadata = json.loads((s.RESULTS / 'metadata.json').read_text(encoding='utf-8'))
    assert all(s.digest(s.ROOT / p) == v for p, v in metadata['protected_sha256'].items())
    metadata['recovery_final_integrity'] = {'prior_completed_not_rerun': 32, 'prior_structural_errors_not_rerun': 4,
        'prior_terminal_cases_rerun': 0, 'new_terminal_cases': 7, 'known_recovery_retries': 1,
        'new_physical_request_starts': len(starts) - sum(json.loads(x)['event'] == 'started' for v in journals.values() for x in v.decode('utf-8').splitlines()),
        'SYN-004_logical_completed_evaluations': 1, 'possible_unobserved_prior_completed_response': 'UNKNOWN',
        'six_not_run_cases_executed_once': True, 'original_journals_preserved': True,
        'relevant_tests_passed': True, 'frozen_and_protected_files_unchanged': True, 'git_diff_check_passed': True}
    s.atomic(s.RESULTS / 'metadata.json', json.dumps(metadata, indent=2) + '\n')
    s.report(final, metadata)


if __name__ == '__main__':
    main()
