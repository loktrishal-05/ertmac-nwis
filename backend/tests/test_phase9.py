"""Focused integration checks. Model output is controlled here; real inference
is separately exercised by scripts.validate_phase9 with the local HTTP stack.
"""
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy import select
import test_phase5d as integrity
from test_agents_safety import _doc_ref, _gen_result
from app.agents.evidence import csv_row_evidence, sensor_window_evidence, pid_region_evidence
from app.agents.graph import run_graph
from app.agents.nodes.safety import safety_node, _gather_evidence
from app.agents.nodes.router import RouteDecision
from app.agents.registry import list_tools
from app.db.models import AuditEvent
from app.schemas.agent_outputs import ActionRecommendation, Citation, MaintenanceHypothesis, ProposedAction
from app.schemas.agent_outputs import GroundedActionRecommendation
from pydantic import ValidationError
from app.schemas.query import QueryRequest
from app.services.approval import apply_decision, release_advisory
from app.services.audit import verify_chain
from app.services.governance import govern_response, ReleaseNotAllowed
from app.services.preflight import run_preflight
from app.services.sovereignty_service import get_sovereignty_proof
from scripts.seed_phase9 import QUERY


class Phase9EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.sop = _doc_ref('P-204A vibration alert threshold 7.1 mm/s. High-high threshold 11.0 mm/s.')
        self.history = csv_row_evidence(source_filename='MH-P204.csv', source_sha256='b'*64, source_row_number=2)
        self.sensor = sensor_window_evidence(source_filename='sensor.csv', source_sha256='c'*64,
                                            citation_label='P-204A recorded window', provenance=[])
        self.drawing = pid_region_evidence(region_id='region', document_id=uuid4(), document_version_id=uuid4(),
            source_filename='PID-U2-017.png', source_sha256='d'*64, page=1, bbox=(0,0,100,100),
            confidence=.54, ocr_status='ambiguous', combined_text='XV-2040', revision='R3')
        self.calls = []
        self.rec = ActionRecommendation(summary='Recorded vibration increased; qualified review proposed.',
            observations=['Recorded vibration increased to 8.2 mm/s.'],
            hypotheses=[MaintenanceHypothesis(text='Possible strainer fouling; not confirmed.',
                supporting_evidence=[self.history.evidence_id], confidence=.4)],
            limitations=['Historical synthetic window; not current telemetry.'],
            evidence_basis=[self.sop.evidence_id, self.history.evidence_id, self.sensor.evidence_id],
            citations=[Citation(evidence_id=r.evidence_id, locator=r.locator, claim='Recorded evidence')
                       for r in (self.sop, self.history, self.sensor)], confidence=.6,
            proposed_actions=[ProposedAction(action='Propose inspection for qualified supervisor review',
                                            action_class='inspection', approval_status='required')])

    def tools(self, name, session, args):
        self.calls.append((name, args))
        if name == 'retrieve_documents': return {}, [self.sop]
        if name == 'get_maintenance_history': return {'records': [{'description': 'Recorded strainer fouling'}]}, [self.history]
        if name == 'get_latest_reading': return {'readings': [{'timestamp':'2026-09-16T10:20:00Z',
            'sensor_tag':'VIB-P204A-01', 'measurement':'vibration', 'unit':'mm/s','value':8.2}]}, []
        if name == 'compute_sensor_features': return {'features':{'maximum':8.2},
            'observations':[{'observation':'Recorded vibration exceeds 7.1 mm/s'}]}, [self.sensor]
        raise AssertionError(name)

    def result(self):
        gateway = MagicMock()
        gateway.generate_structured.return_value = _gen_result(self.rec)
        with patch('app.agents.nodes.safety.invoke_tool', side_effect=self.tools), \
             patch('app.agents.nodes.safety.pid_evidence_lookup', side_effect=lambda q, refs, s: (refs + [self.drawing], [])):
            return safety_node({'query':QUERY, 'route':'combined_safety_maintenance'}, gateway=gateway)

    def test_01_primary_query_passes_preflight(self):
        self.assertEqual(run_preflight(QUERY, 'internal').decision, 'ALLOW')

    def test_02_real_graph_dispatches_combined_route(self):
        gateway = MagicMock()
        gateway.generate_structured.side_effect = [_gen_result(RouteDecision(route='combined_safety_maintenance', confidence=.9, reasoning='Safety and reliability')),
                                                   _gen_result(self.rec)]
        with patch('app.agents.graph.get_model_gateway', return_value=gateway), \
             patch('app.agents.nodes.safety.invoke_tool', side_effect=self.tools):
            result = run_graph(QUERY)
        self.assertEqual(result['route'], 'combined_safety_maintenance')
        self.assertEqual(result['agent_result']['schema'], 'S7')
        self.assertEqual([s['node_name'] for s in result['step_records']], ['router','combined_safety_maintenance'])

    def test_03_sensor_window_is_computed_with_sop_threshold(self):
        self.result()
        args = next(args for name, args in self.calls if name == 'compute_sensor_features')
        self.assertEqual(args['thresholds']['maximum'], 7.1)
        self.assertTrue(args['end'].startswith('2026-09-16T10:20'))

    def test_04_sop_evidence_is_cited(self):
        self.assertIn(self.sop.evidence_id, [c['evidence_id'] for c in self.result()['agent_result']['output']['citations']])

    def test_05_maintenance_evidence_is_used(self):
        result = self.result()
        self.assertIn(self.history, result['evidence'])
        self.assertIn(self.history.evidence_id, result['agent_result']['output']['hypotheses'][0]['supporting_evidence'])

    def test_06_drawing_citation_is_supporting_only(self):
        citation = self.result()['agent_result']['output']['citations'][-1]
        self.assertEqual(citation['evidence_id'], self.drawing.evidence_id)
        self.assertEqual(citation['claim'], 'OCR region available as supporting evidence only.')

    def test_07_observations_and_hypotheses_stay_separate(self):
        output = self.result()['agent_result']['output']
        self.assertTrue(output['observations'] and output['hypotheses'] and output['limitations'])
        self.assertNotIn('fouling', ' '.join(output['observations']))

    def test_08_unsupported_diagnosis_in_observations_refuses(self):
        self.rec.observations = ['The impeller is damaged.']
        self.assertEqual(self.result()['agent_result']['schema'], 'S5')

    def test_09_invalid_locator_refuses(self):
        self.rec.citations[0].locator = 'invented section'
        self.assertEqual(self.result()['agent_result']['schema'], 'S5')

    def test_10_action_requires_approval(self):
        self.rec.human_approval_required = False
        self.rec.proposed_actions[0].approval_status = 'approved'
        result = self.result()
        self.assertTrue(result['human_approval_required'])
        self.assertEqual(result['agent_result']['output']['proposed_actions'][0]['approval_status'], 'required')

    def test_11_no_plant_execution_tool(self):
        self.assertEqual({t.name for t in list_tools()}, {'retrieve_documents','get_pid_regions',
            'get_maintenance_history','get_work_order','get_sensor_readings','get_latest_reading','compute_sensor_features',
            'analyze_sensor_maintenance'})
        self.assertNotEqual(run_preflight('Stop pump P-204A now.', 'internal').decision, 'ALLOW')

    def test_16_sovereignty_stays_valid(self):
        proof = get_sovereignty_proof()
        self.assertEqual(proof.status, 'sovereign')
        self.assertFalse(proof.hosted_ai_configured)
        self.assertFalse(proof.network_egress_enforced)

    def test_17_generation_cannot_omit_evidence_fields(self):
        required = GroundedActionRecommendation.model_json_schema()['required']
        for name in ('citations', 'observations', 'hypotheses', 'limitations', 'evidence_basis'):
            self.assertIn(name, required)
        body = self.rec.model_dump()
        body['citations'] = []
        with self.assertRaises(ValidationError):
            GroundedActionRecommendation.model_validate(body)

    def test_18_prompt_locators_match_citation_contract(self):
        with patch('app.agents.nodes.safety.invoke_tool', side_effect=self.tools):
            refs, blocks, _ = _gather_evidence({'query': QUERY, 'route': 'combined_safety_maintenance'}, None)
        import re
        from html import unescape
        by_id = {ref.evidence_id: ref for ref in refs}
        for block in blocks:
            evidence_id, locator = re.search(r'<evidence id="([^"]+)" locator="([^"]+)"', block).groups()
            self.assertEqual(unescape(locator), by_id[unescape(evidence_id)].locator)

    def test_19_sensor_claims_cannot_omit_window_citation(self):
        self.rec.citations = [citation for citation in self.rec.citations if citation.evidence_id != self.sensor.evidence_id]
        self.assertEqual(self.result()['agent_result']['schema'], 'S5')

    def test_20_causal_hypothesis_must_be_tentative(self):
        with self.assertRaises(ValidationError):
            MaintenanceHypothesis(text='Suction strainer fouling is causing elevated vibration.',
                                  supporting_evidence=[self.history.evidence_id], confidence=.7)
        value = MaintenanceHypothesis(text='Suction strainer fouling may contribute to elevated vibration.',
                                     supporting_evidence=[self.history.evidence_id], confidence=.7)
        self.assertIn('may', value.text)


class Phase9ApprovalTests(unittest.TestCase):
    def setUp(self):
        integrity.EvidenceIntegrityTests.setUp(self)
        evidence = integrity.EvidenceIntegrityTests.document_chunk(self, quote='Synthetic P-204A supervisor review required.')
        self.response = govern_response(self.session, QueryRequest(query=QUERY, request_id=uuid4()),
            integrity._state([evidence], observations=['Recorded value 8.2'], hypotheses=[], limitations=['Synthetic']),
            requester_user_id=self.requester.id)

    def decide(self, decision):
        apply_decision(self.session, revision_id=self.response.action_revision_id, reviewer=self.reviewer, decision=decision)
        self.session.commit()

    def test_12_approval_releases_advisory_only(self):
        self.assertTrue(self.response.human_approval_required)
        self.decide('approve')
        result = release_advisory(self.session, self.response.action_revision_id, actor=self.reviewer)
        self.assertEqual(result['governance_status'], 'RELEASED')
        self.assertIn('agent_result', result)
        self.assertNotIn('execution', result)
        self.decide('revoke')
        with self.assertRaises(ReleaseNotAllowed):
            release_advisory(self.session, self.response.action_revision_id, actor=self.reviewer)

    def test_13_rejection_blocks_release(self):
        self.decide('reject')
        with self.assertRaises(ReleaseNotAllowed):
            release_advisory(self.session, self.response.action_revision_id, actor=self.reviewer)
        self.assertIn('APPROVAL_DECISION_REJECT', self.session.scalars(select(AuditEvent.event_type)).all())

    def test_14_audit_events_created(self):
        self.decide('approve')
        release_advisory(self.session, self.response.action_revision_id, actor=self.reviewer)
        self.decide('revoke')
        events = set(self.session.scalars(select(AuditEvent.event_type)))
        self.assertIn('GOVERNED_REVISION_CREATED', events)
        self.assertTrue({'APPROVAL_DECISION_APPROVE', 'ADVISORY_RELEASE_SUCCESS', 'APPROVAL_DECISION_REVOKE'} <= events)

    def test_15_audit_chain_verifies(self):
        self.decide('reject')
        self.assertTrue(verify_chain(self.session)['valid'])
