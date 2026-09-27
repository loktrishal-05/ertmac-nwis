"""Synthetic authorization and sovereignty regressions; no model inference."""
import os
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from app.api.deps import get_optional_current_user
from app.db.session import get_db
from app.main import app
from app.schemas.query import QueryRequest
from app.schemas.knowledge import RetrieveResponse
from app.services.approval import apply_decision, release_advisory
from app.services.governance import create_revision, replay_request, govern_response, GovernanceConflict, ReleaseNotAllowed
from test_phase5a import state
import test_phase5b


class Phase11SecurityTests(unittest.TestCase):
    def setUp(self):
        test_phase5b.ApprovalServiceTests.setUp(self)
        app.dependency_overrides[get_db] = lambda: self.session
        self.addCleanup(app.dependency_overrides.pop, get_db)

    def actor(self, user):
        app.dependency_overrides[get_optional_current_user] = lambda: user
        self.addCleanup(app.dependency_overrides.pop, get_optional_current_user, None)

    def test_anonymous_cannot_read_or_mutate_company_data(self):
        endpoints = [('POST', '/query'), ('POST', '/knowledge/retrieve'),
            ('POST', '/documents/ingest'), ('POST', '/documents/pid/process'),
            ('POST', f'/documents/pid/{uuid4()}/index'), ('POST', '/data/maintenance/ingest'),
            ('POST', '/data/sensors/ingest'), ('GET', '/maintenance/history'),
            ('GET', '/maintenance/work-orders/example'), ('GET', '/sensors/readings'),
            ('GET', '/sensors/latest'), ('POST', '/sensors/features')]
        with TestClient(app) as client, patch('app.api.routes.query.run_graph') as graph:
            for method, path in endpoints:
                with self.subTest(path=path):
                    self.assertEqual(client.request(method, path, json={} if method == 'POST' else None).status_code, 401)
            graph.assert_not_called()

    def test_ingestion_requires_admin(self):
        self.actor(self.requester)
        with TestClient(app) as client:
            for path in ('/documents/ingest', '/documents/pid/process', '/data/maintenance/ingest', '/data/sensors/ingest'):
                self.assertEqual(client.post(path, json={}).status_code, 403)
        app.dependency_overrides[get_optional_current_user] = lambda: self.admin
        with TestClient(app) as client:
            self.assertEqual(client.post('/documents/ingest', json={}).status_code, 422)

    def test_retrieval_scope_is_server_bounded(self):
        self.actor(self.requester)
        result = RetrieveResponse(query='synthetic pump', results=[], detected_identifiers={})
        with TestClient(app) as client, patch('app.api.routes.knowledge.retrieve', return_value=result) as retrieve:
            self.assertEqual(client.post('/knowledge/retrieve', json={'query': 'synthetic pump', 'filters': {'access_scope': 'restricted'}}).status_code, 403)
            retrieve.assert_not_called()
            self.assertEqual(client.post('/knowledge/retrieve', json={'query': 'synthetic pump'}).status_code, 200)
            self.assertEqual(retrieve.call_args.args[0].filters.access_scope, 'internal')

    def test_replay_and_racing_creation_bind_authenticated_identity(self):
        request = QueryRequest(query='Review synthetic pump recommendation', request_id=uuid4())
        candidate = state()
        revision = create_revision(self.session, request, candidate, requester_user_id=self.requester.id)
        self.session.commit()
        self.assertEqual(replay_request(self.session, request, requester_user_id=self.requester.id).action_revision_id, revision.id)
        for operation in (lambda: replay_request(self.session, request, requester_user_id=self.reviewer.id),
                          lambda: create_revision(self.session, request, candidate, requester_user_id=self.reviewer.id),
                          lambda: govern_response(self.session, request, candidate, requester_user_id=self.reviewer.id)):
            with self.assertRaises(GovernanceConflict):
                operation()

    def test_legacy_unowned_binding_cannot_be_claimed(self):
        request = QueryRequest(query="Review synthetic pump recommendation", request_id=uuid4())
        create_revision(self.session, request, state())
        self.session.commit()
        for operation in (replay_request, create_revision):
            with self.subTest(operation=operation.__name__), self.assertRaises(GovernanceConflict):
                args = (self.session, request, state()) if operation is create_revision else (self.session, request)
                operation(*args, requester_user_id=self.requester.id)

    def test_release_denies_unrelated_requester_and_forged_role(self):
        revision = create_revision(self.session, QueryRequest(query='Review synthetic pump recommendation'), state(), requester_user_id=self.requester.id)
        self.session.commit()
        apply_decision(self.session, revision_id=revision.id, reviewer=self.reviewer, decision='approve')
        self.session.commit()
        from app.db.models import User
        other = User(username='unrelated', role='requester')
        self.session.add(other)
        self.session.commit()
        revision_id = revision.id
        other.role = 'admin'
        with self.assertRaises(ReleaseNotAllowed):
            release_advisory(self.session, revision_id, actor=other)
        self.session.rollback()
        self.assertEqual(release_advisory(self.session, revision.id, actor=self.requester)['governance_status'], 'RELEASED')


if __name__ == '__main__':
    unittest.main()
