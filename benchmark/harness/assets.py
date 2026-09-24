"""Translate the finalized, hash-checked selectors into the existing adapter format."""
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path

DEVELOPMENT = 'RAG-001 SOP-001 TAG-002 MNT-004 SAF-004 TOOL-003 JSON-003 CIT-001 REF-001 INJ-001 HITL-002 OBS-005 SYN-005 PID-005 SNS-002'.split()
PRIVATE = {'injection_test_artifact', 'payload_text', 'payload_class', 'variant_of',
           'harness_note', 'harness_guard', 'referenced_by', 'synthetic_notice',
           'source_file', 'hardening', 'corpus_role'}


def clean(value):
    # Payloads already embedded in text/technician_note/raw_ocr_text stay verbatim.
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in PRIVATE}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def load_mapping(path, source, cases):
    path, source = Path(path).resolve(), Path(source).resolve()
    mapping = json.loads(path.read_text(encoding='utf-8'))
    split = json.loads(source.with_name('benchmark_split_manifest.json').read_text(encoding='utf-8'))
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if sha != mapping['benchmark_sha256'] or sha != split['benchmark_sha256']:
        raise ValueError('Final case hash mismatch.')
    if (path.parent / mapping['benchmark_file']).resolve() != source or (source.parent / split['benchmark_file']).resolve() != source:
        raise ValueError('Final source selector mismatch.')
    if split['splits']['development'] != DEVELOPMENT:
        raise ValueError('STOP: development IDs differ from the authorized split.')
    for name, ids in split['splits'].items():
        if len(ids) != len(set(ids)) or set(ids) != {c['evaluation_id'] for c in cases if c['split'] == name}:
            raise ValueError('Split manifest and cases disagree.')
    for category in {c['category'] for c in cases}:
        if Counter(c['split'] for c in cases if c['category'] == category) != {'development': 1, 'validation': 1, 'blind': 3}:
            raise ValueError('Category split must be 1/1/3.')
    corpus = (path.parent.parent / 'corpus').resolve()
    inventory = {}
    for item in mapping['authoritative_files'] + mapping['authoritative_manifests']:
        file = (path.parent / item['path']).resolve()
        if not file.is_relative_to(corpus):
            raise ValueError('Corpus path escapes the active corpus.')
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != item['sha256'] or item.get('bytes', len(data)) != len(data):
            raise ValueError('Corpus integrity mismatch: ' + item['path'])
        if item in mapping['authoritative_files']:
            inventory[item['path']] = data.decode('utf-8')

    def read(selector):
        if selector not in inventory:
            raise ValueError('Not active evidence: ' + selector)
        return inventory[selector]

    def record(binding):
        artifact = mapping['artifacts'][binding['artifact_key']]
        kind = artifact['artifact_type']
        row = {'evidence_id': binding['evidence_id'], 'ocr_derived': 'ocr_evidence' in kind}
        if binding.get('chunk_selectors'):
            chunks = []
            for selector in binding['chunk_selectors']:
                chunk = json.loads(read(selector['path']).splitlines()[selector['line_1based'] - 1])
                if chunk['evidence_id'] != selector['evidence_id'] or chunk['locator'] != selector['locator']:
                    raise ValueError('Chunk selector mismatch.')
                chunks.append(clean(chunk))
            row.update(tool='qdrant_document_search', locator='; '.join(c['locator'] for c in chunks), content=json.dumps(chunks, ensure_ascii=False))
        elif kind == 'sensor_timeseries_window_family':
            windows = binding.get('window_bindings', [])
            if not windows:
                raise ValueError('No source-assigned bounded sensor window.')
            data, series = [], {}
            for window in windows:
                text = read(window['path'])
                if hashlib.sha256(text.encode('utf-8')).hexdigest() != window['sha256']:
                    raise ValueError('Window hash mismatch.')
                samples = list(csv.DictReader(io.StringIO(text)))
                if len(samples) != window['samples'] or samples[0]['timestamp'] != window['start'] or samples[-1]['timestamp'] != window['end']:
                    raise ValueError('Window bounds mismatch.')
                data.append({'window_id': window['window_id'], 'csv': text})
                for column in samples[0]:
                    if column not in ('timestamp', 'asset_tag'):
                        try:
                            values = [float(s[column]) for s in samples]
                        except ValueError:
                            continue  # Categorical columns remain in raw CSV, never guessed.
                        series[window['window_id'] + ':' + column] = values
            row.update(tool='timeseries_window_fetch', locator='; '.join(w['window_id'] + ' ' + w['start'] + '/' + w['end'] for w in windows), content=json.dumps(data), series=series)
        else:
            files = [f for f in artifact['files'] if f.endswith('.json')]
            if len(files) != 1:
                raise ValueError('Expected one selected JSON artifact.')
            value = json.loads(read(files[0]))
            tool = ('pid_evidence_lookup' if row['ocr_derived'] else 'asset_registry_lookup' if kind == 'asset_instrument_registry' else 'postgres_maintenance_lookup')
            row.update(tool=tool, locator=Path(files[0]).name, content=json.dumps(clean(value), ensure_ascii=False))
        return row

    bindings = {c['evaluation_id']: c for c in mapping['cases']}
    if len(bindings) != 75 or set(bindings) != {c['evaluation_id'] for c in cases}:
        raise ValueError('Incomplete or duplicate case mapping.')
    bundle = {'cases': {}, 'mapping_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    for case in cases:
        binding = bindings[case['evaluation_id']]
        if binding['split'] != case['split']:
            raise ValueError('Mapping split mismatch.')
        selected = list(binding['bindings'])
        for support in binding['contextual_support']:
            a = mapping['artifacts'][support['evidence_id']]
            selected.append({**a, 'artifact_key': support['evidence_id']})
        for window in binding['contextual_sensor_windows']:
            if window['evidence_id'] not in {b['evidence_id'] for b in selected}:
                selected.append({'evidence_id': window['evidence_id'], 'artifact_key': window['evidence_id'], 'window_bindings': [window]})
        entry = {'split': case['split'], 'evidence_ids': [], 'evidence': [],
                 'allow_empty': binding['evidence_status'] == 'no_artifact_required_by_design'}
        try:
            entry['evidence'] = [record(b) for b in selected]
            entry['evidence_ids'] = [r['evidence_id'] for r in entry['evidence']]
        except ValueError as error:
            entry['unresolved'] = str(error)
        bundle['cases'][case['evaluation_id']] = entry
    return bundle
