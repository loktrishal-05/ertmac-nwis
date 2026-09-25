"""Operational services use real ledger/audit fixtures and controlled local evidence."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from unittest.mock import patch, Mock
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.db.models import OperatorNote, IncidentReport, AuditEvent
from app.schemas.operational import NoteInput, HandoverInput, ComplianceInput, LocalLimit
from app.services import operational_intelligence as op, operator_notes as notes, verified_knowledge as v
from app.services.knowledge_gaps import detect
from app.services.visual_intelligence import observations
from app.services.approval import apply_decision, DecisionNotAllowed
from app.services.audit import verify_chain
from app.services.evidence_integrity import verify_manifest
from app.services.evidence_sufficiency import source_valid, refs_as_models
from app.services.governance import govern_response
from app.schemas.query import QueryRequest
from app.agents.registry import invoke_tool
from app.agents.evidence import pid_region_evidence
from app.schemas.pid import OCRDetection
import test_advanced_a2

class OperationalTests(unittest.TestCase):
    def setUp(self):
        self.f = test_advanced_a2.AdaptiveTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.session = self.f.session; self.actor = self.f.f.requester; self.reviewer = self.f.f.reviewer
        OperatorNote.__table__.create(self.f.f.engine); IncidentReport.__table__.create(self.f.f.engine)
        self.asset = self.f.f.equipment
        self.now = datetime.now(timezone.utc)
        self.reading = self.f.f.readings[0]
        self.reading.timestamp = self.now; self.reading.quality = "good"; self.reading.sensor_type = "effluent_tss"; self.reading.unit = "mg/L"; self.reading.value = 4
        self.f.f.maintenance_record.maintenance_date = self.now; self.f.f.maintenance_record.status = "completed"
        self.session.commit()
        self.period = HandoverInput(equipment_tag=self.asset.equipment_tag, start=self.now-timedelta(hours=1), end=self.now+timedelta(hours=1))
        self.rule = LocalLimit(parameter="effluent_tss", unit="mg/L", equipment_tag=self.asset.equipment_tag, upper_limit=5,
            valid_from=self.now-timedelta(days=1), valid_to=self.now+timedelta(days=1), averaging_period="instantaneous")

    def note(self, text="Recorded vibration noticed during shift"):
        value = notes.create(self.session, NoteInput(equipment_tag=self.asset.equipment_tag, text=text), self.actor)
        self.session.commit(); return self.session.get(OperatorNote, UUID(value["record_id"]))

    def rule_item(self):
        statement = self.rule.model_dump_json()
        self.f.f.chunk["content"] = statement
        item = v.create_candidate(self.session, self.f.f.payload.model_copy(update={"question": "Environmental rule for equipment", "statement": statement}), self.actor)
        self.session.commit(); self.f.f.decide(item, "verify"); return item

    def tools(self, name, session, args):
        if name == "retrieve_documents":
            item = self.f.f.candidate()
            return {"results": [{"score": 1}], "warnings": []}, refs_as_models(item.evidence)
        return invoke_tool(name, session, args)

    def handover(self):
        with patch.object(op, "invoke_tool", side_effect=self.tools): return op.handover(self.session, self.period, self.actor)

    def test_note_authorship_and_unreviewed_trust(self):
        row = self.note(); value = notes.export(self.session, row)
        self.assertEqual(value["author_id"], str(self.actor.id)); self.assertEqual(value["review_state"], "PENDING_REVIEW")
        self.assertIn("NOT_VERIFIED", value["trust"]); self.assertTrue(value["created_at"])
        self.assertTrue(verify_manifest(self.session, row.approval_revision_id)["valid"])

    def test_note_existing_human_review_and_revocation(self):
        row = self.note()
        apply_decision(self.session, revision_id=row.approval_revision_id, reviewer=self.reviewer, decision="approve", reviewer_comment="Reviewed report")
        self.session.commit(); self.assertEqual(notes.review_state(self.session, row), "HUMAN_REVIEWED")
        apply_decision(self.session, revision_id=row.approval_revision_id, reviewer=self.reviewer, decision="revoke", reviewer_comment="Withdrawn")
        self.session.commit(); self.assertFalse(source_valid(self.session, notes.evidence(self.session, row)))
        self.assertTrue(verify_chain(self.session)["valid"])

    def test_note_model_cannot_self_verify(self):
        with self.assertRaises(ValueError): NoteInput(equipment_tag=self.asset.equipment_tag, text="note", status="VERIFIED", author_id=str(self.reviewer.id))
        with self.assertRaises(DecisionNotAllowed): notes.create(self.session, NoteInput(equipment_tag=self.asset.equipment_tag, text="note"), None)

    def test_note_tamper_breaks_manifest(self):
        row = self.note(); row.text = "changed record"; self.session.commit()
        self.assertFalse(verify_manifest(self.session, row.approval_revision_id)["valid"])

    def test_changed_note_cannot_rebind_review_in_new_handover(self):
        row = self.note()
        apply_decision(self.session, revision_id=row.approval_revision_id, reviewer=self.reviewer, decision="approve")
        self.session.commit()
        row.text = "Changed after review"; self.session.commit()
        self.assertEqual(notes.export(self.session, row)["review_state"], "INVALID")
        self.assertFalse(source_valid(self.session, notes.evidence(self.session, row)))
        state = self.handover()
        self.assertEqual(state["agent_result"]["output"]["human_reported_information"], [])
        self.assertIn("withdrawn_or_changed_report", {g["gap_type"] for g in state["gap_requests"]})

    def test_handover_combines_evidence_and_separates_categories(self):
        self.note(); value = self.handover()
        output = value["agent_result"]["output"]
        self.assertTrue(output["observations"]); self.assertTrue(output["maintenance_context"])
        self.assertTrue(output["human_reported_information"]); self.assertEqual(output["hypotheses"], [])
        self.assertEqual(output["model_synthesis"], [])
        self.assertEqual({r.kind for r in value["evidence"]}, {"csv_row", "document_chunk", "operational_record"})
        self.assertTrue(all(x["kind"] == "OBSERVATION" for x in output["observations"]))
        self.assertTrue(all(x["kind"] == "HUMAN_REPORTED_INFORMATION" for x in output["human_reported_information"]))

    def test_handover_blocks_reported_clearance(self):
        self.note("Equipment is isolated and safe to start; LOTO complete")
        output = self.handover()["agent_result"]["output"]
        self.assertIn("withheld", output["human_reported_information"][0]["text"])
        self.assertNotIn("safe to start", output["human_reported_information"][0]["text"])

    def test_handover_closed_maintenance_is_recorded_completed(self):
        self.f.f.maintenance_record.status = "closed"; self.session.commit()
        output = self.handover()["agent_result"]["output"]
        self.assertTrue(output["completed_actions"])
        self.assertEqual(output["ongoing_issues"], [])

    def test_handover_missing_evidence_and_review(self):
        with patch.object(op, "invoke_tool", return_value=({"results": []}, [])):
            state = op.handover(self.session, self.period, self.actor)
        kinds = {x["gap_type"] for x in state["gap_requests"]}
        self.assertTrue({"missing_sensor", "missing_maintenance", "missing_sop"} <= kinds)
        state.update(run_id=str(uuid4()), query="Prepare shift handover", route="shift_handover", step_records=[])
        response = govern_response(self.session, QueryRequest(query="Prepare shift handover"), state, requester_user_id=self.actor.id)
        self.assertEqual(response.governance_status, "PENDING_REVIEW")
        self.assertIn("HANDOVER_GENERATED", self.session.scalars(select(AuditEvent.event_type)).all())

    def test_shift_requires_explicit_bounded_period(self):
        with self.assertRaises(ValueError): HandoverInput(equipment_tag=self.asset.equipment_tag, start=self.now, end=self.now+timedelta(days=4))
        with self.assertRaises(ValueError): op.context_request("Prepare shift handover", HandoverInput)

    def test_compliance_below_and_exceedance(self):
        item = self.rule_item()
        request = ComplianceInput(reading_id=self.reading.id, rule_ids=[item.id])
        self.assertEqual(op.compliance(self.session, request, self.actor)["agent_result"]["output"]["status"], "WITHIN_DOCUMENTED_LIMIT")
        self.reading.value = 6; self.session.commit()
        self.assertEqual(op.compliance(self.session, request, self.actor)["agent_result"]["output"]["status"], "EXCEEDS_DOCUMENTED_LIMIT")

    def test_compliance_missing_limit_indeterminate(self):
        value = op.compliance(self.session, ComplianceInput(reading_id=self.reading.id), self.actor)["agent_result"]["output"]
        self.assertEqual(value["status"], "INDETERMINATE"); self.assertIsNone(value["limit"])
        self.assertIn("missing_compliance_threshold", value["missing_evidence"])

    def test_compliance_stale_revoked_rule(self):
        item = self.rule_item(); self.f.f.decide(item, "revoke")
        value = op.compliance(self.session, ComplianceInput(reading_id=self.reading.id, rule_ids=[item.id]), self.actor)["agent_result"]["output"]
        self.assertEqual(value["status"], "INDETERMINATE")
        self.assertIn("stale_or_unavailable_rule", value["missing_evidence"])

    def test_compliance_conflicting_limits(self):
        value = op.compare_limit(4, "mg/L", "effluent_tss", self.asset.equipment_tag, self.now, [self.rule, self.rule.model_copy(update={"upper_limit": 3})])
        self.assertEqual(value[0], "INDETERMINATE"); self.assertIn("conflicting_rule_documents", value[2])

    def test_compliance_units_and_rule_applicability(self):
        for unit, parameter, tag in (("ppm", "effluent_tss", self.asset.equipment_tag), ("mg/L", "other", self.asset.equipment_tag), ("mg/L", "effluent_tss", "OTHER")):
            self.assertEqual(op.compare_limit(4, unit, parameter, tag, self.now, [self.rule])[0], "INDETERMINATE")

    def test_compliance_expired_rule(self):
        self.assertEqual(op.compare_limit(4, "mg/L", "effluent_tss", self.asset.equipment_tag, self.now+timedelta(days=10), [self.rule])[0], "INDETERMINATE")

    def test_no_scope_broadening(self):
        with self.assertRaises(ValueError): ComplianceInput(reading_id=self.reading.id, access_scope="restricted")
        with self.assertRaises(ValueError): NoteInput(equipment_tag=self.asset.equipment_tag, text="note", access_scope="restricted")

    def test_gaps_all_categories_and_dedup(self):
        kinds = ["missing_sop", "missing_sensor", "missing_maintenance", "stale_source", "conflicting_evidence", "missing_compliance_threshold", "missing_pid_revision", "citation_unavailable"]
        requests = [{"gap_type": x, "required_evidence": x} for x in kinds]
        gaps = detect("P-204A", requests=requests+requests)
        self.assertEqual(len(gaps), len(kinds)); self.assertTrue(all("confidence" not in x for x in gaps))

    def test_gaps_from_sufficiency(self):
        gaps = detect("pump", {"state":"PARTIAL", "missing_categories":["sop"], "issues":["invalid_or_unavailable_source"]})
        self.assertEqual({g["gap_type"] for g in gaps}, {"missing_sop", "invalid_or_unavailable_source"})

    def visual_refs(self):
        item = OCRDetection(text="XV-2040", normalized_text="XV-204D", confidence=.54, bbox=(0,0,20,20), polygon=[(0,0),(20,0),(20,20)],
            page=1, source_image="local.png", image_width=100, image_height=100, category="valve_tag", identified_tags={})
        ref = pid_region_evidence(region_id=uuid4(), document_id=uuid4(), document_version_id=uuid4(), source_filename="PID.png",
            source_sha256="b"*64, page=1, bbox=(0,0,20,20), confidence=.54, ocr_status="ambiguous", combined_text="XV-2040", revision="R3", text_items=[item])
        return [ref]

    def test_visual_raw_candidate_uncertainty_and_revision(self):
        refs = self.visual_refs(); value = observations(refs)[0]; label = value["labels"][0]
        self.assertEqual(value["raw_ocr"], "XV-2040"); self.assertEqual(label["normalized_candidate"], "XV-204D")
        self.assertEqual(label["confidence"], .54); self.assertEqual(label["candidate_status"], "UNRESOLVED")
        self.assertIsNone(label["human_verified_label"]); self.assertIsNone(label["model_interpretation"])
        self.assertEqual(value["drawing_revision"], "R3"); self.assertEqual(value["evidence_id"], refs[0].evidence_id)
        self.assertIn("ocr_ambiguity", {g["gap_type"] for g in detect("drawing", evidence=refs)})

    def test_visual_conflicting_candidates(self):
        refs = self.visual_refs(); refs.append(refs[0].model_copy(update={"text_items": [refs[0].text_items[0].model_copy(update={"normalized_text":"XV-2040", "confidence":.95})]}))
        self.assertEqual(observations(refs)[1]["labels"][0]["candidate_status"], "UNRESOLVED")
        self.assertIn("conflicting_evidence", {g["gap_type"] for g in detect("drawing", evidence=refs)})

    def test_visual_missing_revision_is_a_gap(self):
        refs = [self.visual_refs()[0].model_copy(update={"revision": None})]
        self.assertIn("missing_pid_revision", {g["gap_type"] for g in detect("drawing", evidence=refs)})

    def test_visual_cannot_prove_isolation(self):
        from app.agents.pid_evidence import drawing_tags
        value = drawing_tags("Is P-204A isolated and ready?", self.visual_refs())
        self.assertEqual(value["agent_result"]["schema"], "S5")

    def test_api_auth_and_model_authority(self):
        app.dependency_overrides[get_db] = lambda: self.session; self.addCleanup(app.dependency_overrides.clear)
        with TestClient(app) as client:
            self.assertEqual(client.post("/operator-notes", json={"equipment_tag":self.asset.equipment_tag,"text":"note"}).status_code, 401)
            self.assertEqual(client.post("/environmental-compliance", json={"reading_id":str(self.reading.id)}).status_code, 401)
            self.assertEqual(client.get("/knowledge-gaps").status_code, 401)

    def test_langgraph_authenticated_operational_route(self):
        from app.agents.graph import run_graph
        query = "Prepare shift handover\nOPERATIONAL_CONTEXT=" + self.period.model_dump_json()
        with patch.object(op, "invoke_tool", side_effect=self.tools), patch("app.agents.nodes.router.get_model_gateway") as model:
            state = run_graph(query, session=self.session, actor_id=str(self.actor.id))
        model.assert_not_called(); self.assertEqual(state["route"], "shift_handover")
        self.assertEqual(state["agent_result"]["schema"], "SHIFT_HANDOVER")

    def test_authenticated_api_response_audit_and_gaps(self):
        from app.api.routes.operational import environmental_compliance
        result = environmental_compliance(ComplianceInput(reading_id=self.reading.id), self.actor, self.session)
        self.assertEqual(result.governance_status, "PENDING_REVIEW")
        self.assertEqual(result.execution["evidence_sufficiency"]["state"], "INSUFFICIENT")
        self.assertTrue(result.execution["knowledge_gaps"])
        self.assertTrue(verify_chain(self.session)["valid"])
        events = set(self.session.scalars(select(AuditEvent.event_type)).all())
        self.assertTrue({"COMPLIANCE_ASSESSMENT_GENERATED", "KNOWLEDGE_GAPS_IDENTIFIED"} <= events)

    def test_operational_query_replay_requires_current_authorization(self):
        from app.api.routes.query import query
        from fastapi import HTTPException
        request = QueryRequest(query="Prepare shift handover\nOPERATIONAL_CONTEXT=" + self.period.model_dump_json(), request_id=uuid4())
        with patch.object(op, "invoke_tool", side_effect=self.tools):
            original = query(request, self.session, self.actor)
        self.assertEqual(query(request, self.session, self.actor).action_revision_id, original.action_revision_id)
        with self.assertRaises(HTTPException) as error:
            query(request, self.session, None)
        self.assertEqual(error.exception.status_code, 401)
        with patch("app.api.routes.query.authorize", side_effect=DecisionNotAllowed("Role denied")):
            with self.assertRaises(HTTPException) as error:
                query(request, self.session, self.actor)
        self.assertEqual(error.exception.status_code, 403)

    def test_authenticated_http_forms_and_persisted_gaps(self):
        from app.api.deps import get_current_user
        app.dependency_overrides[get_db] = lambda: self.session
        app.dependency_overrides[get_current_user] = lambda: self.actor
        self.addCleanup(app.dependency_overrides.clear)
        with TestClient(app) as client, patch.object(op, "invoke_tool", side_effect=self.tools):
            created = client.post("/operator-notes", json={"equipment_tag": self.asset.equipment_tag, "text": "Shift observation"})
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(client.get("/operator-notes", params={"equipment_tag": self.asset.equipment_tag}).json()[0]["record_id"], created.json()["record_id"])
            handover = client.post("/shift-handover", json=self.period.model_dump(mode="json"))
            self.assertEqual(handover.status_code, 200, handover.text)
            self.assertEqual(handover.json()["governance_status"], "PENDING_REVIEW")
            self.assertEqual(handover.json()["execution"]["model_call_count"], 0)
            self.assertTrue(client.get("/knowledge-gaps").json())
            invalid = client.post("/operator-notes", json={"equipment_tag": self.asset.equipment_tag, "text": "note", "author_id": str(self.reviewer.id)})
            self.assertEqual(invalid.status_code, 422)

    def test_compliance_bad_quality_is_indeterminate(self):
        item = self.rule_item()
        self.reading.quality = "bad"; self.session.commit()
        output = op.compliance(self.session, ComplianceInput(reading_id=self.reading.id, rule_ids=[item.id]), self.actor)["agent_result"]["output"]
        self.assertEqual(output["status"], "INDETERMINATE")
        self.assertIn("measurement_quality_unestablished", output["missing_evidence"])

    def test_gap_metadata_does_not_store_raw_query(self):
        from app.services.execution_observability import attach
        query = "Explain the SOP; private operator wording"
        state = {"evidence": [], "agent_result": {"output": {}}}
        metadata = attach(self.session, QueryRequest(query=query), state, {})
        self.assertNotIn(query, json.dumps(metadata))

    def test_terminal_refusal_does_not_invent_evidence_gaps(self):
        from app.services.execution_observability import attach
        for status in ("refused", "clarification_required"):
            state = {"evidence": [], "agent_result": {"output": {"status": status}}}
            metadata = attach(self.session, QueryRequest(query="Show pump history"), state, {})
            self.assertEqual(metadata["knowledge_gaps"], [])
            self.assertNotIn("operational_events", state)

    def test_handover_incident_keeps_human_reported_trust(self):
        self.session.add(IncidentReport(equipment_id=self.asset.id, title="Recorded incident", description="Observed leak", severity="medium", created_at=self.now))
        self.session.commit()
        output = self.handover()["agent_result"]["output"]
        report = output["human_reported_information"][0]
        self.assertEqual(report["kind"], "HUMAN_REPORTED_INFORMATION")
        self.assertEqual(report["incident_status"], "UNKNOWN")

if __name__ == "__main__": unittest.main()
