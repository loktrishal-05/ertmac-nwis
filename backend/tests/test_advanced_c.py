"""Local adapter contracts and real SQLite governance/BI/webhook integration."""
import base64
import json
import time
import unittest
from uuid import uuid4
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.api.deps import get_optional_current_user
from app.core.config import settings
from app.db.session import get_db
from app.db.models import AutomationReceipt, AuditEvent, IncidentReport, ApprovalDecision
from app.schemas.product import AutomationInput
from app.schemas.query import QueryRequest
from app.services import local_voice as voice, industrial_bi as bi, product_integration as integration
from app.services.audit import verify_chain
from app.services.approval import apply_decision
from app.services.sovereignty_service import get_sovereignty_proof
import test_advanced_b
from test_phase5a import state


def wav_bytes(seconds=0.1):
    """A synthetic silent WAV, built in memory; never real plant audio."""
    import io, wave
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
        out.writeframes(b'\0\0' * int(16000 * seconds))
    return buffer.getvalue()


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.f = test_advanced_b.OperationalTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.session = self.f.session
        AutomationReceipt.__table__.create(self.f.f.f.engine)
        from app.db.models.durable_execution import DurableExecution
        DurableExecution.__table__.create(self.f.f.f.engine)
        app.dependency_overrides[get_db] = lambda: self.session
        app.dependency_overrides[get_optional_current_user] = lambda: self.f.actor
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.audio = base64.b64encode(wav_bytes()).decode()
        self.patches = [patch.object(settings, 'stt_url', ''), patch.object(settings, 'tts_url', ''),
            patch.object(settings, 'automation_secret', 'test-only-' * 4),
            patch.object(settings, 'automation_user_id', str(self.f.reviewer.id))]
        for p in self.patches: p.start(); self.addCleanup(p.stop)

    def hook(self, **changes):
        body = AutomationInput(nonce=uuid4(), timestamp=int(time.time()), kind='audit_summary').model_copy(update=changes)
        return body, integration.signature(body, settings.automation_secret)

    def send_hook(self, body, signature):
        return self.client.post('/automation/webhook', json=body.model_dump(mode='json'), headers={'X-Workbench-Signature': signature})

    def test_text_mode_with_voice_disabled(self):
        status = self.client.get('/product/status').json()
        self.assertTrue(status['text_mode']); self.assertEqual(status['stt'], 'unavailable')
        with patch('app.api.routes.query.run_graph', return_value=state('S1', answer='Original explanation')):
            response = self.client.post('/query', json={'query': 'Show maintenance history for P-204A.'})
        self.assertEqual(response.status_code, 200, response.text)

    def test_missing_stt_retains_text_mode_and_no_audio_audit(self):
        response = self.client.post('/voice/transcribe', json={'audio_base64': self.audio, 'mime_type': 'audio/wav', 'input_language':'hi'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'unavailable')
        event = self.session.scalars(select(AuditEvent).where(AuditEvent.event_type == 'PRODUCT_INTEGRATION_EVENT')).one()
        self.assertEqual(event.payload['kind'], 'stt')
        self.assertNotIn(self.audio, json.dumps(event.payload))
        self.assertTrue(verify_chain(self.session)['valid'])

    def test_missing_tts_safe_fallback(self):
        response = self.client.post('/voice/synthesize', json={'text':'P-204A requires human review'})
        self.assertEqual(response.json()['status'], 'unavailable')
        self.assertNotIn('audio_base64', response.json())

    def test_runtime_outage_safe_fallback(self):
        with patch.object(voice, 'exchange', side_effect=httpx.ConnectError('offline')):
            self.assertEqual(voice.transcribe(self.audio, 'audio/wav', 'en')['status'], 'unavailable')
            self.assertEqual(voice.synthesize('Original', 'en')['status'], 'unavailable')

    def test_transcript_exact_identifiers_and_confirmation(self):
        text = 'P-204A XV-2040 SOP-P204-001 की जानकारी'
        with patch.object(voice, 'exchange', return_value={'text':text}):
            result = voice.transcribe(self.audio, 'audio/wav', 'hi')
        self.assertEqual(result['text'], text)
        self.assertTrue(result['confirmation_required'])

    def test_invalid_audio_rejected(self):
        response = self.client.post('/voice/transcribe', json={'audio_base64':'not base64!', 'mime_type':'audio/wav'})
        self.assertEqual(response.status_code, 422)

    def test_cloud_or_redirect_adapter_rejected(self):
        with patch.object(voice.httpx, 'Client') as client:
            with self.assertRaises(ValueError): voice.exchange('https://speech.example.com', {})
            client.assert_not_called()
        with patch.object(voice, 'exchange', side_effect=httpx.HTTPStatusError('redirect', request=httpx.Request('POST','http://localhost'), response=httpx.Response(302))):
            self.assertEqual(voice.transcribe(self.audio, 'audio/wav', 'en')['status'], 'unavailable')

    def test_tts_keeps_original_text_and_adds_advisory_boundary(self):
        with patch.object(voice, 'exchange', return_value={'audio_base64':self.audio,'mime_type':'audio/wav'}) as adapter:
            result = voice.synthesize('P-204A XV-2040', 'ta')
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(adapter.call_args.args[1]['text'].endswith('P-204A XV-2040'))
        self.assertIn('No permission', adapter.call_args.args[1]['text'])

    def test_speech_auth_required(self):
        app.dependency_overrides[get_optional_current_user] = lambda: None
        self.assertEqual(self.client.post('/voice/synthesize', json={'text':'hello'}).status_code, 401)
        self.assertEqual(self.client.post('/voice/transcribe', json={'audio_base64':self.audio,'mime_type':'audio/wav'}).status_code, 401)

    def test_voice_uses_preflight_and_has_no_plant_route(self):
        with patch('app.api.routes.query.run_graph') as graph:
            response = self.client.post('/query', json={'query':'Start P-204A now.', 'input_channel':'voice'})
        self.assertEqual(response.status_code, 200, response.text)
        graph.assert_not_called()
        self.assertEqual(response.json()['agent_result']['schema'], 'S5')

    def test_voice_cannot_skip_hitl(self):
        with patch('app.api.routes.query.run_graph', return_value=state()):
            response = self.client.post('/query', json={'query':'Review maintenance history for P-204A.', 'input_channel':'voice'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['governance_status'], 'PENDING_REVIEW')
        self.assertTrue(response.json()['human_approval_required'])

    def test_voice_query_auth_before_replay(self):
        app.dependency_overrides[get_optional_current_user] = lambda: None
        with patch('app.api.routes.query.replay_request') as replay:
            response = self.client.post('/query', json={'query':'Show P-204A history', 'input_channel':'voice'})
        self.assertEqual(response.status_code,401); replay.assert_not_called()

    def test_unsupported_language_preserves_original(self):
        self.assertEqual(voice.language('xx')['effective'], 'und')
        text = 'P-204A / XV-2040 / SOP-123'
        request = QueryRequest(query=text, input_language='xx')
        self.assertEqual(request.query, text)
        for lang in ('en','hi','ta','hi-IN'): self.assertTrue(voice.language(lang)['supported'])

    def test_language_and_channel_bind_governed_replay(self):
        from app.services.governance import _request_payload
        request = QueryRequest(query='P-204A history')
        self.assertNotEqual(_request_payload(request), _request_payload(request.model_copy(update={'input_language':'ta'})))

    def test_bi_missing_data_is_unknown(self):
        result = bi.snapshot(self.session)
        self.assertIsNone(result['metrics']['open_incidents'])
        self.assertIsNone(result['metrics']['mean_query_latency_ms'])
        self.assertIsNone(result['metrics']['knowledge_gaps_in_sample'])

    def test_bi_counts_stored_records_and_pending_review(self):
        self.f.note()
        self.session.add(IncidentReport(title='Recorded', description='Recorded incident', severity='medium', equipment_id=self.f.asset.id))
        self.session.commit()
        result = bi.snapshot(self.session)
        self.assertEqual(result['metrics']['recorded_incidents'],1)
        self.assertEqual(result['metrics']['operator_notes'],1)
        self.assertEqual(result['metrics']['pending_human_approvals'],1)
        from app.db.models import OperatorNote
        note = self.session.scalar(select(OperatorNote))
        apply_decision(self.session, revision_id=note.approval_revision_id, reviewer=self.f.reviewer, decision='approve')
        self.session.commit()
        self.assertEqual(bi.snapshot(self.session)['metrics']['pending_human_approvals'],0)

    def test_bi_distributions_from_execution_metadata(self):
        with patch('app.api.routes.query.run_graph', return_value=state()):
            self.client.post('/query', json={'query':'Review maintenance history for P-204A.', 'input_channel':'voice'})
        result = bi.snapshot(self.session)
        self.assertEqual(result['metadata_runs'],1)
        self.assertEqual(result['execution_paths'], {'EXISTING_AGENTIC_PATH':1})
        self.assertEqual(result['evidence_sufficiency'], {'INSUFFICIENT':1})
        self.assertGreater(result['metrics']['knowledge_gaps_in_sample'],0)

    def test_bi_generated_counts_use_audit_events_not_note_routes(self):
        self.f.note()
        self.assertEqual(bi.snapshot(self.session)['metrics']['generated_handovers'], 0)
        from app.api.routes.operational import environmental_compliance
        from app.schemas.operational import ComplianceInput
        environmental_compliance(ComplianceInput(reading_id=self.f.reading.id), self.f.actor, self.session)
        self.assertEqual(bi.snapshot(self.session)['metrics']['environmental_assessments'], 1)

    def test_sensitive_bi_rbac(self):
        self.assertEqual(self.client.get('/bi/operational').status_code,403)
        app.dependency_overrides[get_optional_current_user] = lambda: self.f.reviewer
        response = self.client.get('/bi/operational')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_webhook_valid_and_replay_rejected_durably(self):
        body, signature = self.hook()
        response = self.send_hook(body,signature)
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['delivery_performed'])
        self.session.expire_all()
        self.assertEqual(self.send_hook(body,signature).status_code,409)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(AutomationReceipt)),1)
        self.assertTrue(verify_chain(self.session)['valid'])

    def test_webhook_invalid_expired_and_tampered_rejected(self):
        body, signature = self.hook()
        self.assertEqual(self.send_hook(body,'0'*64).status_code,401)
        self.assertEqual(self.send_hook(body.model_copy(update={'kind':'report_delivery'}),signature).status_code,401)
        body, signature = self.hook(timestamp=int(time.time())-301)
        self.assertEqual(self.send_hook(body,signature).status_code,401)

    def test_webhook_disabled_and_role_revocation(self):
        body, signature = self.hook()
        with patch.object(settings,'automation_secret',''):
            self.assertEqual(self.send_hook(body,signature).status_code,503)
        with patch.object(settings,'automation_user_id',str(self.f.actor.id)):
            self.assertEqual(self.send_hook(body,signature).status_code,403)

    def test_webhook_cannot_request_plant_actions_or_approval(self):
        body, signature = self.hook()
        for extra in ({'kind':'start_pump'},{'query':'Start P-204A'},{'decision':'approve'},{'destination':'http://external.example'}):
            payload = body.model_dump(mode='json') | extra
            self.assertEqual(self.client.post('/automation/webhook',json=payload,headers={'X-Workbench-Signature':signature}).status_code,422)
        before = self.session.scalar(select(func.count()).select_from(ApprovalDecision))
        self.assertEqual(self.send_hook(body,signature).status_code,200)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(ApprovalDecision)),before)

    def test_automation_secret_is_not_a_human_session(self):
        app.dependency_overrides[get_optional_current_user] = lambda: None
        self.assertEqual(self.client.get('/approvals',headers={'Authorization':'Bearer '+settings.automation_secret}).status_code,401)

    def test_cloud_speech_configuration_invalidates_proof(self):
        with patch.object(settings,'stt_url','https://speech.example.com'):
            self.assertEqual(get_sovereignty_proof().status,'invalid')


if __name__ == '__main__': unittest.main()
