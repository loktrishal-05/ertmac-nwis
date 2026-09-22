"""Phase 6 integration: existing OCR artifacts, existing agents, existing integrity gate."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import test_phase5d as integrity_tests
from test_agents_safety import _doc_ref, _recommendation, _gen_result
from test_pid import page_info
from app.core.config import settings
from app.agents.evidence import document_chunk_evidence
from app.agents.graph import run_graph
from app.agents.nodes.knowledge import knowledge_node
from app.agents.nodes.safety import safety_node
from app.agents.nodes.maintenance import maintenance_node
from app.agents.tools.knowledge import get_pid_regions, GetPIDRegionsArguments
from app.schemas.pid import OCRDetection, PIDManifest
from app.schemas.query import QueryRequest
from app.services.pid_regions import group_regions
from app.services.pid_evidence import load_pid_evidence
from app.services.governance import govern_response, EvidenceIntegrityFailure
from app.services.approval import apply_decision, release_advisory
from app.services.evidence_integrity import verify_manifest


class Phase6Tests(unittest.TestCase):
    def setUp(self):
        integrity_tests.EvidenceIntegrityTests.setUp(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        root_patch = patch.object(settings, 'data_root', self.root)
        root_patch.start(); self.addCleanup(root_patch.stop)
        self.raw_path = self.root / 'raw/pids/source/drawing.png'
        self.raw_path.parent.mkdir(parents=True)
        self.raw_path.write_bytes(b'phase6 synthetic drawing source')
        v = self.document_version
        v.source_sha256 = hashlib.sha256(self.raw_path.read_bytes()).hexdigest()
        v.ingestion_metadata = {'kind':'pid', 'request':{'revision':'R3','access_scope':'internal'}}
        self.document.document_type = 'pid'
        self.session.commit()
        self.detection = OCRDetection(text='XV-2040', normalized_text='XV-204D', confidence=.54,
            bbox=(10,10,80,35), polygon=[(10,10),(80,10),(80,35),(10,35)], page=1,
            source_image='processed/pids/page_images/test/rendered.png', image_width=200,image_height=100,
            category='valve_tag',identified_tags={'valve_tags':['XV-204D']})
        self.region = group_regions([self.detection],v.id)[0]
        self.region_path = self.root / f'processed/pids/regions/{v.id}.json'
        self.write_regions()
        manifest = PIDManifest(document_id=self.document.id,document_version_id=v.id,
            source_filename='drawing.png',source_uri='raw/pids/source/drawing.png',source_sha256=v.source_sha256,
            page_count=1,render_dpi=None,ocr_model=['PP-OCRv5_server_rec'],processed_at=datetime.now(timezone.utc),
            synthetic=True,warnings=[],pages=[page_info()],ocr_json_uri='processed/pids/ocr_json/test.json',
            region_json_uri=self.region_path.relative_to(self.root).as_posix(),ocr_detections=1,regions=1,
            equipment_tags=[],instrument_tags=[])
        manifest_path=self.root/f'processed/pids/manifests/{v.id}.json'
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(manifest.model_dump_json(),encoding='utf-8')

    def write_regions(self):
        self.region_path.parent.mkdir(parents=True,exist_ok=True)
        self.region_path.write_text(json.dumps({'document_id':str(self.document.id),
            'document_version_id':str(self.document_version.id),'source_sha256':self.document_version.source_sha256,
            'regions':[self.region.model_dump(mode='json')]}),encoding='utf-8')

    def refs(self):
        return load_pid_evidence(self.session,self.document_version.id)

    def retrieved(self):
        return document_chunk_evidence(chunk_id='drawing-chunk',document_id=self.document.id,
            document_version_id=self.document_version.id,source_filename='drawing.png',
            source_sha256=self.document_version.source_sha256,section_path=[],page_start=1,page_end=1,
            bounding_boxes=[],quote='XV-2040',ocr_derived=True,ocr_confidence=.54,ocr_status='ambiguous')

    def knowledge(self,query='Extract OCR tags on the P&ID drawing'):
        gateway=MagicMock()
        with patch('app.agents.nodes.knowledge.invoke_tool',return_value=({'results':[{'score':1.0}]},[self.retrieved()])):
            result=knowledge_node({'query':query},gateway=gateway,session=self.session)
        gateway.generate_structured.assert_not_called()
        return result

    def approved_revision(self):
        response=govern_response(self.session,QueryRequest(query='Review pump drawing',request_id=uuid4()),
            integrity_tests._state([r.model_dump(mode='json') for r in self.refs()]),requester_user_id=self.requester.id)
        apply_decision(self.session,revision_id=response.action_revision_id,reviewer=self.reviewer,decision='approve')
        self.session.commit()
        return response.action_revision_id

    def test_high_confidence_tag_is_not_verified(self):
        self.region.text_items[0].confidence=.98
        self.region.text_items[0].status='unverified'
        self.write_regions()
        result=self.knowledge()
        self.assertEqual(result['agent_result']['output']['tags'][0]['status'],'unverified')

    def test_low_confidence_stays_uncertain(self):
        self.assertEqual(self.knowledge()['agent_result']['output']['tags'][0]['status'],'ambiguous')

    def test_raw_ocr_preserved(self):
        self.assertEqual(self.refs()[0].text_items[0].text,'XV-2040')
        self.assertEqual(self.knowledge()['agent_result']['output']['tags'][0]['raw_text'],'XV-2040')

    def test_candidate_is_separate(self):
        tag=self.knowledge()['agent_result']['output']['tags'][0]
        self.assertEqual(tag['normalized_tag'],'XV-204D')
        self.assertNotEqual(tag['raw_text'],tag['normalized_tag'])

    def test_drawing_citation_locator(self):
        ref=self.refs()[0]
        for part in (str(self.document.id),'drawing.png','R3','page 1',str(self.region.region_id)):
            self.assertIn(part,ref.locator)
        self.assertTrue(ref.ocr_derived)
        self.assertEqual(ref.bbox,self.region.bbox)

    def test_unreadable_line_size_refuses(self):
        self.assertEqual(self.knowledge('What line size is on this P&ID?')['agent_result']['schema'],'S5')

    def test_valve_list_never_claims_completeness(self):
        result=self.knowledge('List every valve on the drawing')
        self.assertIn('not a complete valve list',result['agent_result']['output']['warnings'][0])

    def test_cannot_prove_isolation(self):
        self.assertEqual(self.knowledge('Does the P&ID prove isolation?')['agent_result']['schema'],'S5')

    def test_cannot_prove_valve_state(self):
        self.assertEqual(self.knowledge('Is the valve open on the drawing?')['agent_result']['schema'],'S5')

    def test_knowledge_consumes_real_region_lookup(self):
        result=self.knowledge()
        self.assertEqual(result['agent_result']['schema'],'S3')
        self.assertEqual(result['evidence'][0].kind,'pid_region')
        self.assertTrue(result['evidence'][0].ocr_region_hash)

    def test_graph_preserves_drawing_evidence_and_tool_trace(self):
        with patch('app.agents.graph.get_model_gateway',return_value=MagicMock()), \
             patch('app.agents.graph.router_node',return_value={'route':'knowledge'}), \
             patch('app.agents.nodes.knowledge.invoke_tool',return_value=({'results':[{'score':1.0}]},[self.retrieved()])):
            state = run_graph('Extract OCR tags on the P&ID drawing',session=self.session)
        self.assertEqual(state['agent_result']['schema'],'S3')
        self.assertEqual(state['evidence'][0].kind,'pid_region')
        self.assertEqual(state['tool_invocations'][0]['tool_name'],'get_pid_regions')
        self.assertIn(state['evidence'][0].evidence_id,state['step_records'][-1]['evidence_ids'])

    def test_missing_or_malformed_artifact_fails_closed(self):
        for value in ('{}','not json'):
            self.region_path.write_text(value)
            payload,refs=get_pid_regions(self.session,GetPIDRegionsArguments(document_version_id=self.document_version.id))
            self.assertEqual(refs,[])
            self.assertTrue(payload['warnings'])

    def test_safety_ocr_alone_cannot_authorize(self):
        gateway=MagicMock()
        with patch('app.agents.nodes.safety.invoke_tool',return_value=({},[self.retrieved()])):
            result=safety_node({'query':'Review isolation using the P&ID','route':'safety'},gateway=gateway,session=self.session)
        self.assertEqual(result['agent_result']['schema'],'S5')
        gateway.generate_structured.assert_not_called()

    def test_safety_procedure_retains_hitl_and_drawing_citation(self):
        sop=_doc_ref()
        gateway=MagicMock()
        gateway.generate_structured.return_value=_gen_result(_recommendation(sop.evidence_id,action_class='isolation',approval_status='approved'))
        with patch('app.agents.nodes.safety.invoke_tool',return_value=({},[sop,self.retrieved()])):
            result=safety_node({'query':'Review isolation using the P&ID','route':'safety'},gateway=gateway,session=self.session)
        self.assertEqual(result['agent_result']['schema'],'S7')
        self.assertTrue(result['human_approval_required'])
        self.assertEqual(result['agent_result']['output']['proposed_actions'][0]['approval_status'],'required')
        self.assertIn('R3',result['agent_result']['output']['citations'][-1]['locator'])

    def test_maintenance_ocr_is_not_diagnosis(self):
        gateway=MagicMock()
        def tools(name,*args):
            return ({},[self.retrieved()]) if name=='retrieve_documents' else ({},[])
        with patch('app.agents.nodes.maintenance.invoke_tool',side_effect=tools):
            result=maintenance_node({'query':'Assess P-101A using the drawing'},gateway=gateway,session=self.session)
        self.assertEqual(result['agent_result']['schema'],'S5')
        gateway.generate_structured.assert_not_called()

    def test_manifest_binds_ocr_and_releases_valid_revision(self):
        rid=self.approved_revision()
        self.assertTrue(verify_manifest(self.session,rid)['valid'])
        self.assertEqual(release_advisory(self.session,rid,actor=self.reviewer)['governance_status'],'RELEASED')

    def test_mutated_ocr_candidate_denies_release(self):
        rid=self.approved_revision()
        self.region.text_items[0].normalized_text='XV-OTHER'
        self.write_regions()
        self.assertFalse(verify_manifest(self.session,rid)['valid'])
        with self.assertRaises(EvidenceIntegrityFailure):
            release_advisory(self.session,rid,actor=self.reviewer)

    def test_mutated_source_bytes_denies_release(self):
        rid=self.approved_revision()
        self.raw_path.write_bytes(b'changed source')
        with self.assertRaises(EvidenceIntegrityFailure):
            release_advisory(self.session,rid,actor=self.reviewer)

    def test_substituted_region_artifact_denies_release(self):
        rid=self.approved_revision()
        artifact=json.loads(self.region_path.read_text())
        artifact['document_version_id']=str(uuid4())
        self.region_path.write_text(json.dumps(artifact))
        with self.assertRaises(EvidenceIntegrityFailure):
            release_advisory(self.session,rid,actor=self.reviewer)

    def test_non_drawing_query_does_not_lookup_regions(self):
        with patch('app.agents.nodes.knowledge.invoke_tool',return_value=({'results':[]},[])), patch('app.agents.pid_evidence.invoke_tool') as lookup:
            knowledge_node({'query':'What does SOP-17 say about inspection?'},gateway=MagicMock(),session=self.session)
        lookup.assert_not_called()

    def test_drawing_identifier_miss_still_refuses(self):
        payload = {'results':[{'score':1.0}], 'warnings':['No lexical evidence matched ZZQ-99999']}
        with patch('app.agents.nodes.knowledge.invoke_tool',return_value=(payload,[self.retrieved()])), patch('app.agents.pid_evidence.invoke_tool') as lookup:
            result = knowledge_node({'query':'Show ZZQ-99999 on the drawing'},gateway=MagicMock(),session=self.session)
        self.assertEqual(result['agent_result']['schema'],'S5')
        lookup.assert_not_called()
