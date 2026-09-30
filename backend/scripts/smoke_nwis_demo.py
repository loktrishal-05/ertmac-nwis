"""Real HTTP golden scenario. Run only against your isolated synthetic demo runtime."""
import argparse
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4
import httpx
from app.schemas import nwis as schema
from app.schemas.audit import AuditEventResponse
from app.schemas.auth import UserPublic


def run(base_url, username, password, output, hybrid=False):
    timings = {}
    checks = []
    with httpx.Client(base_url=base_url, timeout=180, trust_env=False) as client:
        def call(method, path, model=None, expected=200, label=None, **kwargs):
            start = perf_counter()
            response = client.request(method, path, **kwargs)
            timings.setdefault(label or path.split('?')[0], []).append((perf_counter()-start)*1000)
            assert response.status_code == expected, (method, path, response.status_code, response.text[:500])
            data = response.json()
            if model:
                model.model_validate(data)
            if expected >= 400:
                assert 'detail' in data
            checks.append(f'{method} {path}: {expected}')
            return data

        ready = call('GET', '/ready')
        assert ready['status'] == 'ready' and all(ready['checks'].values()), ready
        call('GET', '/api/wells', expected=401)
        actor = call('POST', '/auth/login', UserPublic, json={'username': username, 'password': password})
        assert actor['role'] == 'reviewer'
        call('GET', '/auth/me')
        call('GET', '/api/terms', schema.TermsOut)
        call('POST', '/api/terms/accept', schema.TermsOut, json={'version': 'nwis-advisory-v1', 'accepted': True})
        # Rewind only the existing synthetic well; never fabricate fresh telemetry.
        call('POST', '/api/wells/ACTIVE-01/replay', schema.WellOut, json={'as_of': '2026-09-29T16:00:00Z'})
        wells = call('GET', '/api/wells', schema.Page[schema.WellOut])
        assert len(wells['items']) == 12 and not wells['has_more']
        assert all(w['dataset_origin'] == 'synthetic_demo' for w in wells['items'])
        active = call('GET', '/api/wells/ACTIVE-01', schema.WellOut)
        assert active['current_md'] == 2450 and active['field'] == 'SYNTHETIC-ASSAM-DEMO'
        nearby = call('GET', '/api/wells/ACTIVE-01/nearby', schema.Page[schema.MatchOut])['items']
        assert nearby == call('GET', '/api/wells/ACTIVE-01/nearby', schema.Page[schema.MatchOut])['items']
        closest = min(nearby, key=lambda x: x['distance_m'])
        assert closest['offset_well_id'] == 'OFF-01'
        assert [x['offset_well_id'] for x in nearby[:4]] == ['OFF-04', 'OFF-02', 'OFF-03', 'OFF-09']
        correlation = call('GET', '/api/wells/ACTIVE-01/correlation?lookahead_m=100', schema.CorrelationOut)
        assert correlation['lookahead_window']['end']['md'] == 2550
        events = call('GET', '/api/events?type=stuck_pipe&formation=TIPAM_A&depth_basis=tvd&depth_min=2450&depth_max=2550', schema.Page[schema.EventOut])['items']
        risk = call('GET', '/api/wells/ACTIVE-01/risk?lookahead_m=100', schema.RiskOut)
        hazard = next(h for h in risk['hazards'] if h['type'] == 'stuck_pipe')
        fixture = json.loads((Path(__file__).resolve().parents[2]/'docs/nwis/golden_demo_fixture.json').read_text(encoding='utf-8'))
        for key in ('probability', 'confidence', 'historical_exposure', 'live_anomaly_contribution'):
            assert math.isclose(hazard[key], fixture['hazard'][key], rel_tol=0, abs_tol=1e-12), key
        for key in ('supporting_offset_wells', 'evidence_ids', 'top_factors'):
            assert hazard[key] == fixture['hazard'][key], key
        assert math.isclose(closest['distance_m'], fixture['closest']['distance_m'], rel_tol=0, abs_tol=1e-6)
        assert not risk['calibrated'] and risk['advisory_only']
        assert hazard['probability'] >= .6 and hazard['confidence'] >= .5
        assert {'OFF-04', 'OFF-09'} <= set(hazard['supporting_offset_wells'])
        telemetry = call('GET', '/api/wells/ACTIVE-01/telemetry', schema.TelemetryPage)
        assert telemetry['source_mode'] == 'replay'
        assert all(c['state'] == 'fresh' for c in telemetry['channels'])
        existing = call('GET', '/api/advisories', schema.Page[schema.AdvisoryOut])['items']
        emitted = []
        for index, stamp in enumerate(('15:58', '15:59', '16:00')):
            call('POST', '/api/wells/ACTIVE-01/replay', schema.WellOut, json={'as_of': f'2026-09-29T{stamp}:00Z'})
            assessment = call('POST', '/api/wells/ACTIVE-01/assess?lookahead_m=100', schema.AssessmentOut)
            emitted.append(len(assessment['advisories']))
            if not existing and index < 2:
                assert not assessment['advisories'], 'Transient condition emitted an alert'
        if not existing:
            assert emitted[-1] > 0, 'Persistent condition failed to emit'
        duplicate = call('POST', '/api/wells/ACTIVE-01/assess?lookahead_m=100', schema.AssessmentOut)
        assert not duplicate['advisories']
        detail = call('GET', '/api/assessments/'+hazard['assessment_id'], schema.AssessmentDetail)
        assert {e['event']['id'] for e in detail['evidence']} == set(hazard['evidence_ids'])
        for link in detail['evidence']:
            assert link['event'] == link['event_at_assessment']
            assert link['event']['verification_state'] == 'unverified'
            assert link['source_sha256'] == link['source_sha256_at_assessment']
            assert link['source_url'].endswith('#page='+str(link['event']['source_page']))
            source = client.get(link['source_url'].split('#')[0])
            assert source.status_code == 200 and source.headers['content-type'] == 'application/pdf'
            assert hashlib.sha256(source.content).hexdigest() == link['source_sha256']
        def query(**overrides):
            body = dict(mode='nwis_evidence', request_id=str(uuid4()), well_id='ACTIVE-01',
                        query='show stuck-pipe incidents in Tipam between 2400-2700 m TVD',
                        type='stuck_pipe', lookahead_m=100, retrieval='hybrid' if hybrid else 'structured')
            body.update(overrides)
            return call('POST', '/api/query', schema.QueryOut, label='knowledge_query', json=body)
        answer = query()
        assert answer['evidence'] and answer['dataset_origin'] == 'synthetic_demo'
        assert all(e['id'] in answer['answer'] for e in answer['evidence'])
        exact = query(query='OFF-04 TIPAM_A stuck_pipe 2470 m', formation='TIPAM_A', offset_limit=1)
        assert exact['evidence'] and all(e['well_id'] == 'OFF-04' and e['formation'] == 'TIPAM_A' for e in exact['evidence'])
        advisory = next(a for a in call('GET', '/api/advisories', schema.Page[schema.AdvisoryOut])['items'] if a['assessment_id'] == hazard['assessment_id'])
        review_body = {'status': 'acknowledged', 'reason': 'Reviewed synthetic source pages; advisory only, no rig control'}
        if advisory['status'] == 'pending_review':
            advisory = call('POST', '/api/advisories/'+advisory['id']+'/review', schema.AdvisoryOut, json=review_body)
        assert advisory['reviewer'] == actor['id'] and advisory['reviewed_at']
        call('POST', '/api/advisories/'+advisory['id']+'/review', expected=409, json=review_body)
        audit = call('GET', '/api/audit?limit=100', schema.Page[AuditEventResponse])['items']
        assert all(e['actor_id'] == actor['id'] for e in audit)
        assert any(e['payload'].get('advisory_id') == advisory['id'] and e['payload']['action'] == 'advisory_review' for e in audit)
        # Error/empty contracts, without changing the canonical dataset.
        for operation in ('risk', 'correlation', 'assess'):
            call('POST' if operation == 'assess' else 'GET', f'/api/wells/ACTIVE-01/{operation}?lookahead_m=75', expected=422)
        call('POST', '/api/query', expected=422, json={'mode': 'unsupported', 'query': 'test', 'request_id': str(uuid4())})
        call('GET', '/api/wells/UNKNOWN', expected=404)
        empty = query(radius_km=.001)
        assert not empty['evidence'] and 'Insufficient' in empty['answer']
        no_analogs = call('GET', '/api/wells/ACTIVE-01/risk?radius_km=0.001', schema.RiskOut)
        assert all(h['probability'] is None for h in no_analogs['hazards'])
        missing_depth = call('GET', '/api/events?depth_basis=tvdss&depth_min=0', schema.Page[schema.EventOut])
        assert not missing_depth['items']
        stale = call('GET', '/api/wells/ACTIVE-01/telemetry?channels=torque&to=2026-09-29T16:06:00Z', schema.TelemetryPage)
        assert stale['channels'][0]['state'] == 'stale'
        call('POST', '/api/ingest/report?well_id=ACTIVE-01&type=DDR&dataset_origin=synthetic_demo', expected=403, content=b'%PDF-demo', headers={'content-type': 'application/pdf'})
        # Three warm observations per endpoint; fresh query IDs force real execution.
        measured = {}
        for name, path, model in (
            ('wells', '/api/wells', schema.Page[schema.WellOut]),
            ('nearby', '/api/wells/ACTIVE-01/nearby', schema.Page[schema.MatchOut]),
            ('correlation', '/api/wells/ACTIVE-01/correlation?lookahead_m=100', schema.CorrelationOut),
            ('risk', '/api/wells/ACTIVE-01/risk?lookahead_m=100', schema.RiskOut),
            ('assessment', '/api/assessments/'+hazard['assessment_id'], schema.AssessmentDetail),
            ('telemetry', '/api/wells/ACTIVE-01/telemetry', schema.TelemetryPage)):
            for _ in range(3):
                call('GET', path, model, label='latency_'+name)
            measured[name] = round(median(timings['latency_'+name]), 2)
        for _ in range(3):
            query()
        measured['knowledge_query'] = round(median(timings['knowledge_query'][-3:]), 2)
        call('POST', '/auth/logout')
        call('POST', '/api/advisories/'+advisory['id']+'/review', expected=401, json=review_body)
        result = dict(dataset_origin='synthetic_demo', readiness=ready, active=active,
                      closest=closest, top_analogs=nearby[:4], nearby=nearby,
                      risk=risk, historical_events=events, evidence_chain=detail['evidence'],
                      telemetry={k: telemetry[k] for k in ('source_mode', 'freshness_reference', 'channels')},
                      retrieval='hybrid' if hybrid else 'structured', query_evidence=answer['evidence'],
                      exact_identifier_evidence=exact['evidence'], alert_emissions=emitted,
                      advisory=advisory, audit_actions=sorted({e['payload']['action'] for e in audit}),
                      latency_median_ms=measured, checks=checks, check_count=len(checks))
        Path(output).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'http_checks': len(checks), 'latency_median_ms': measured, 'output': str(output)}, indent=2))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', default='data/nwis_c2_smoke.json')
    parser.add_argument('--hybrid', action='store_true')
    args = parser.parse_args()
    password = os.getenv('NWIS_DEMO_PASSWORD') or getpass.getpass('Demo reviewer password: ')
    run(args.base_url, os.getenv('NWIS_DEMO_USER', 'nwis_demo_reviewer'), password, args.output, args.hybrid)


if __name__ == '__main__':
    main()
