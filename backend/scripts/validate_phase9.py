"""Real HTTP demo validation. No mocked inference or prebuilt recommendations."""
import argparse
import json
from pathlib import Path
from uuid import uuid4, UUID

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.db.models import AgentRunStep
from app.db.session import SessionLocal
from scripts.seed_phase9 import QUERY, DEMO_USERS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', default=QUERY)
    parser.add_argument('--output', type=Path, default=settings.data_root / 'processed/phase9-live.json')
    args = parser.parse_args()
    report = {'query': args.query, 'synthetic_only': True}
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')

    try:
        with httpx.Client(base_url='http://localhost:8000', timeout=2100, trust_env=False) as requester, \
             httpx.Client(base_url='http://localhost:8000', timeout=2100, trust_env=False) as reviewer:
            for endpoint in ('health', 'ready', 'sovereignty/proof', 'agents/status'):
                response = requester.get('/' + endpoint)
                report[endpoint] = response.json()
                response.raise_for_status()
            proof = report['sovereignty/proof']
            assert proof['status'] == 'sovereign' and proof['local_model'] == 'qwen3.5:9b'
            assert not proof['hosted_ai_configured'] and not proof['cloud_ai_enabled']
            for client, (username, password, _) in zip((requester, reviewer), DEMO_USERS):
                client.post('/auth/login', json={'username': username, 'password': password}).raise_for_status()
            for decision in ('approve', 'reject'):
                request_id = str(uuid4())
                report[decision] = {'request_id': request_id}
                save()
                print('Submitting', decision, request_id, flush=True)
                response = requester.post('/query', json={'query': args.query, 'request_id': request_id})
                report[decision].update({'http_status': response.status_code, 'query_response': response.json()})
                save()
                response.raise_for_status()
                result = response.json()
                with SessionLocal() as session:
                    report[decision]['trace'] = [
                        {'node': step.node_name, 'tool': step.tool_name, 'evidence_ids': step.evidence_ids, 'timings': step.timings}
                        for step in session.scalars(select(AgentRunStep).where(AgentRunStep.run_id == UUID(result['run_id']))
                                                    .order_by(AgentRunStep.step_index))]
                assert result['agent_result']['schema'] != 'S5', 'Model returned a refusal; see captured response'
                assert result['route'] == 'combined_safety_maintenance', 'Expected combined safety/maintenance triage'
                output = result['agent_result']['output']
                assert output.get('observations') and output.get('hypotheses') and output.get('limitations')
                assert output.get('citations') and result['human_approval_required']
                cited = {c['evidence_id'] for c in output['citations']}
                refs = result['evidence']
                for filename in ('SOP-P204-001-demo-v1.pdf', 'MH-P204-demo-v1.csv', 'SENSOR-P204-A-demo-v1.csv'):
                    assert any(r['source_filename'] == filename and r['evidence_id'] in cited for r in refs), filename
                assert any(r['kind'] == 'sensor_window' for r in refs)
                assert any(r['kind'] == 'pid_region' and r['evidence_id'] in cited for r in refs)
                revision = result['action_revision_id']
                response = reviewer.post(f'/approvals/{revision}/decision', json={
                    'decision': decision, 'expected_revision_id': revision, 'reviewer_comment': 'Synthetic Phase 9 validation; advisory only.'})
                report[decision]['decision'] = response.json()
                response.raise_for_status()
                released = reviewer.get(f'/approvals/{revision}/release')
                report[decision]['release'] = {'status': released.status_code, 'body': released.json()}
                assert released.status_code == (200 if decision == 'approve' else 403)
                if decision == 'approve':
                    assert released.json()['governance_status'] == 'RELEASED'
                    revoked = reviewer.post(f'/approvals/{revision}/decision', json={'decision': 'revoke', 'expected_revision_id': revision})
                    revoked.raise_for_status()
                    report[decision]['revoke'] = revoked.json()
                    assert reviewer.get(f'/approvals/{revision}/release').status_code == 403
                save()
                print(decision, revision, 'validated', flush=True)
            report['audit'] = reviewer.get('/audit/log?limit=100').json()
            for decision in ('approve', 'reject'):
                revision = report[decision]['query_response']['action_revision_id']
                events = {event['event_type'] for event in report['audit'] if event['action_revision_id'] == revision}
                required = {'GOVERNED_REVISION_CREATED', 'APPROVAL_DECISION_' + decision.upper()}
                if decision == 'approve':
                    required |= {'ADVISORY_RELEASE_SUCCESS', 'APPROVAL_DECISION_REVOKE'}
                assert required <= events, f'Missing audit events for {revision}: {required - events}'
            report['audit_verify'] = reviewer.get('/audit/verify').json()
            assert report['audit_verify']['valid']
            report['final_proof'] = reviewer.get('/sovereignty/proof').json()
            assert report['final_proof']['external_ai_calls'] == 0
            for client in (requester, reviewer):
                client.post('/auth/logout').raise_for_status()
            report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['failure'] = str(error)
        # Preserve independent safety observations even when the model refuses.
        try:
            with httpx.Client(base_url='http://localhost:8000', timeout=30, trust_env=False) as client:
                username, password, _ = DEMO_USERS[1]
                client.post('/auth/login', json={'username': username, 'password': password}).raise_for_status()
                for key, endpoint in [('audit', '/audit/log?limit=100'), ('audit_verify', '/audit/verify'),
                                      ('final_proof', '/sovereignty/proof')]:
                    response = client.get(endpoint)
                    response.raise_for_status()
                    report[key] = response.json()
                client.post('/auth/logout').raise_for_status()
        except Exception as snapshot_error:
            report['snapshot_error'] = str(snapshot_error)
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
