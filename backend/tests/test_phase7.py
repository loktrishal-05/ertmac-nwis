"""Locality controls and truthful application-level proof; no hosted requests."""
import unittest
from unittest.mock import patch, MagicMock
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.core.config import settings
from app.core.locality import classify_http_url, classify_database, require_private_resolution
from app.main import app
from app.services.model_gateway import ModelConfigurationError, ModelRuntimeError, ModelUnavailableError
from app.services.model_gateway.ollama_runtime import OllamaRuntime
from app.services.model_gateway.registry import validate_model_url
from app.services.model_gateway.observations import snapshot
from app.services.sovereignty_service import get_sovereignty_proof
from app.services.readiness import runtime_readiness
from test_model_gateway import make_settings


class Phase7Tests(unittest.TestCase):
    def test_cloud_model_tag_rejected_on_local_endpoint(self):
        for name in ('example:cloud','example:large-cloud'):
            with self.assertRaises(ValidationError):
                make_settings(model_name=name)

    def test_hosted_and_public_endpoints_rejected_even_allowlisted(self):
        for host in ('api.openai.com','api.anthropic.com','generativelanguage.googleapis.com',
                     '8.8.8.8','169.254.169.254','0.0.0.0','example.com'):
            with self.subTest(host=host), self.assertRaises(ModelConfigurationError):
                validate_model_url('https://'+host,{host})

    def test_local_private_and_docker_targets(self):
        for host in ('localhost','127.0.0.1','ollama','host.docker.internal','10.2.3.4','172.16.1.2','192.168.4.5','model.company.internal'):
            with self.subTest(host=host):
                self.assertEqual(validate_model_url('http://'+host+':11434',{host}),'http://'+host+':11434')

    def test_lan_settings_require_explicit_allowlist(self):
        make_settings(model_base_url='http://192.168.1.50:11434',model_allowed_hosts='192.168.1.50')
        with self.assertRaises(ValidationError):
            make_settings(model_base_url='http://192.168.1.50:11434')

    def test_endpoint_credentials_and_query_rejected(self):
        for url in ('http://user:secret@localhost:11434','http://localhost?api_key=secret',
                    'http://localhost#api.openai.com','http://localhost:bad','file:///models'):
            self.assertEqual(classify_http_url(url),'invalid')

    def test_public_dns_resolution_fails_closed(self):
        with patch('app.core.locality.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',11434))]):
            with self.assertRaises(ValueError):
                require_private_resolution('http://ollama:11434')

    def test_redirect_never_followed(self):
        requests=[]
        def handler(request):
            requests.append(request)
            return httpx.Response(302,headers={'Location':'https://api.openai.com'})
        runtime=OllamaRuntime(make_settings(),transport=httpx.MockTransport(handler))
        with self.assertRaises(ModelRuntimeError):
            runtime._request('GET','/api/tags',timeout_seconds=1)
        self.assertEqual(len(requests),1)
        runtime._http.close()

    def test_dirty_config_rejected_before_transport(self):
        configured=make_settings()
        configured.model_base_url='https://api.openai.com'
        transport=MagicMock()
        with self.assertRaises(ModelConfigurationError):
            OllamaRuntime(configured,transport=transport)._request('POST','/api/chat',timeout_seconds=1)
        transport.handle_request.assert_not_called()

    def test_dispatch_counter_is_real(self):
        runtime=OllamaRuntime(make_settings(),transport=httpx.MockTransport(lambda r:httpx.Response(200,json={})))
        before=snapshot()
        runtime._request('POST','/api/chat',json_body={},timeout_seconds=1)
        self.assertEqual(snapshot()['local_ai_attempts'],before['local_ai_attempts']+1)
        self.assertEqual(snapshot()['external_ai_calls'],before['external_ai_calls'])
        runtime._http.close()

    def test_proof_reflects_configuration_without_secrets(self):
        with patch.object(settings,'model_base_url','http://10.1.2.3:11434'), \
             patch.object(settings,'model_allowed_hosts','10.1.2.3'), \
             patch.object(settings,'database_url','postgresql+psycopg://private-user:SECRET@192.168.2.3/db'), \
             patch.object(settings,'qdrant_url','http://qdrant:6333'):
            proof=get_sovereignty_proof()
        self.assertEqual(proof.inference_endpoint_classification,'private')
        self.assertEqual(proof.postgresql_classification,'private')
        self.assertEqual(proof.qdrant_classification,'private')
        self.assertNotIn('SECRET',proof.model_dump_json())
        self.assertNotIn('private-user',proof.model_dump_json())
        self.assertFalse(proof.network_egress_enforced)

    def test_invalid_config_never_claims_sovereign(self):
        with patch.object(settings,'model_base_url','https://api.openai.com'):
            proof=get_sovereignty_proof()
        self.assertTrue(proof.hosted_ai_configured)
        self.assertEqual(proof.status,'invalid')

    def test_counter_cannot_be_reset_by_client(self):
        observed=dict(snapshot(),external_ai_calls=3)
        with patch('app.services.sovereignty_service.snapshot',return_value=observed), TestClient(app) as client:
            response=client.get('/sovereignty/proof?external_ai_calls=0&status=sovereign')
            self.assertEqual(response.json()['external_ai_calls'],3)
            self.assertEqual(response.json()['status'],'invalid')
            self.assertEqual(client.post('/sovereignty/proof',json={'external_ai_calls':0}).status_code,405)

    def test_data_endpoint_classification(self):
        for host,expected in (('localhost','local'),('postgres','private'),('10.0.1.2','private'),('db.example.com','invalid')):
            self.assertEqual(classify_database('postgresql+psycopg://user:secret@'+host+'/db'),expected)
            self.assertEqual(classify_http_url('http://'+host+':6333'),expected)
        self.assertEqual(classify_database('postgresql://user@localhost/db?host=8.8.8.8'),'invalid')

    def test_public_data_configuration_rejected(self):
        for values in ({'qdrant_url':'https://cloud.example.com'},
                       {'database_url':'postgresql://user@8.8.8.8/db'}, {'data_root':'s3://bucket/data'}):
            with self.assertRaises(ValidationError):
                make_settings(**values)

    def test_health_never_checks_dependencies(self):
        with patch('app.api.routes.health.runtime_readiness') as ready,TestClient(app) as client:
            self.assertEqual(client.get('/health').status_code,200)
        ready.assert_not_called()

    def test_readiness_ready_and_failure_are_redacted(self):
        with patch('app.services.readiness.check_postgres',return_value=True), \
             patch('app.services.readiness.check_qdrant',return_value=True), \
             patch('app.services.readiness.check_model',return_value=True),TestClient(app) as client:
            self.assertEqual(client.get('/ready').status_code,200)
            with patch('app.services.readiness.check_postgres',side_effect=RuntimeError('PASSWORD')):
                response=client.get('/ready')
                self.assertEqual(response.status_code,503)
                self.assertNotIn('PASSWORD',response.text)

    def test_invalid_config_readiness_makes_no_connections(self):
        with patch.object(settings,'qdrant_url','https://public.example.com'), \
             patch('app.services.readiness.check_postgres') as pg:
            self.assertEqual(runtime_readiness()['status'],'not_ready')
        pg.assert_not_called()

    def test_vllm_placeholder_not_ready(self):
        from app.services.readiness import check_model
        with patch.object(settings,'model_runtime','vllm'),self.assertRaises(NotImplementedError):
            check_model()


if __name__ == '__main__':
    unittest.main()
