"""B2 deterministic checks using the existing SQLite structured-data pattern."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event

from app.api.deps import get_optional_current_user
from app.agents.citations import validate_citations
from app.agents.registry import invoke_tool, ToolArgumentError
from app.agents.safety_language import find_authorization_language
from app.core.config import settings
from app.db.models import Equipment, MaintenanceRecord, SensorReading
from app.db.session import get_db
from app.main import app
from app.schemas.maintenance_sensor_intelligence import SensorMaintenanceIntelligenceRequest
from app.services.maintenance_sensor_intelligence import analyze, validate_language
from test_structured import sqlite_session


START = datetime(2026, 1, 10, tzinfo=timezone.utc)


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.session = sqlite_session()
        self.addCleanup(self.session.bind.dispose)
        self.addCleanup(self.session.close)
        self.equipment = Equipment(equipment_tag="P-204", name="Synthetic pump", equipment_type="pump", location="test")
        self.session.add(self.equipment)
        self.session.flush()
        self.row_number = 0

    def readings(self, values, tag="VIB", unit="mm/s", offsets=None, quality="good"):
        for index, value in enumerate(values):
            self.row_number += 1
            self.session.add(SensorReading(
                equipment_id=self.equipment.id, sensor_tag=tag, sensor_type="vibration",
                value=value, unit=unit, quality=quality,
                timestamp=START + timedelta(hours=(offsets or list(range(len(values))))[index]),
                source_filename="b2.csv", source_sha256="a" * 64, source_row_number=self.row_number))
        self.session.commit()

    def maintenance(self, hours):
        self.row_number += 1
        self.session.add(MaintenanceRecord(
            equipment_id=self.equipment.id, raw_equipment_tag="P-204", work_order_id="WO-1",
            maintenance_type="corrective", maintenance_date=START + timedelta(hours=hours),
            source_filename="b2-maintenance.csv", source_sha256="b" * 64,
            source_row_number=self.row_number, raw_row={}))
        self.session.commit()

    def request(self, **changes):
        return SensorMaintenanceIntelligenceRequest.model_validate(dict(
            equipment_tag="P204", start=START, end=START + timedelta(hours=12),
            thresholds={"VIB": {"maximum": 4}, "TEMP": {"maximum": 50}}) | changes)

    def analyze(self, **changes):
        return analyze(self.session, self.request(**changes))[0]

    def test_sustained_vibration_rise_and_statistics(self):
        self.readings([1, 2, 3, 5])
        response = self.analyze()
        channel = response.channels[0]
        self.assertEqual((channel.features.minimum, channel.features.maximum, channel.features.mean), (1, 5, 2.75))
        self.assertAlmostEqual(channel.rate_of_change_per_hour, 4 / 3)
        self.assertEqual(channel.sustained_rise.consecutive_increases, 3)
        self.assertEqual(channel.sustained_rise.duration_minutes, 180)

    def test_transient_spike_is_not_progressive_hypothesis(self):
        self.readings([1, 8, 1])
        response = self.analyze()
        self.assertIsNone(response.channels[0].sustained_rise)
        self.assertEqual(response.channels[0].excursions[0].duration_minutes, 0)
        self.assertEqual(response.hypotheses, [])

    def test_threshold_crossing_and_persistence(self):
        self.readings([4, 5, 6, 4, 5])
        channel = self.analyze().channels[0]
        self.assertEqual(len(channel.threshold_crossings), 2)
        self.assertEqual(channel.threshold_crossings[0].crossed_at, START + timedelta(hours=1))
        self.assertEqual([(e.samples, e.duration_minutes) for e in channel.excursions], [(2, 60), (1, 0)])

    def test_lower_threshold_and_initial_excursion(self):
        self.readings([1, 3, 1])
        channel = self.analyze(thresholds={"VIB": {"minimum": 2}}).channels[0]
        self.assertEqual(len(channel.excursions), 2)
        self.assertEqual(len(channel.threshold_crossings), 1)
        self.assertEqual(channel.threshold_crossings[0].direction, "below_minimum")

    def test_stable_correlated_channels_no_causal_hypothesis(self):
        self.readings([1, 2, 1, 2])
        self.readings([10, 20, 10, 20], "TEMP", "C")
        response = self.analyze()
        self.assertEqual(response.correlations[0].pearson_r, 1)
        self.assertEqual(response.hypotheses, [])
        self.assertIn("does not establish causation", next(o.observation for o in response.observations if o.kind == "trend_correlation"))

    def test_constant_channels_undefined_correlation(self):
        self.readings([2, 2, 2])
        self.readings([20, 20, 20], "TEMP", "C")
        result = self.analyze().correlations[0]
        self.assertIsNone(result.pearson_r)
        self.assertIn("zero variance", result.not_computed_reason)

    def test_conflicting_indicators_and_contradictory_evidence(self):
        self.readings([1, 3, 5])
        self.readings([20, 20, 20], "TEMP", "C")
        response = self.analyze()
        self.assertEqual(len(response.contradicting_evidence), 1)
        self.assertEqual(len(response.contradicting_evidence[0].evidence_ids), 2)
        self.assertTrue(response.hypotheses[0].contradicting_evidence)

    def test_unthresholded_channel_is_not_contradiction(self):
        self.readings([1, 3, 5])
        self.readings([20, 20, 20], "TEMP", "C")
        self.assertEqual(self.analyze(thresholds={"VIB": {"maximum": 4}}).contradicting_evidence, [])

    def test_maintenance_before_anomaly_is_context_only(self):
        self.readings([1, 3, 5])
        self.maintenance(-24)
        response = self.analyze()
        self.assertEqual(response.maintenance_links[0].relation, "before_anomaly")
        record_id = response.maintenance_links[0].evidence_id
        self.assertNotIn(record_id, response.hypotheses[0].supporting_evidence)
        observation = next(o for o in response.observations if o.kind == "maintenance_temporal_relation")
        self.assertEqual(len(observation.evidence_ids), 2)
        self.assertIn("not proof of recurrence", observation.observation)

    def test_maintenance_after_anomaly_is_not_contradiction(self):
        self.readings([1, 3, 5])
        self.maintenance(6)
        response = self.analyze()
        self.assertEqual(response.maintenance_links[0].relation, "after_anomaly")
        self.assertNotIn(response.maintenance_links[0].evidence_id, response.hypotheses[0].contradicting_evidence)

    def test_maintenance_same_timestamp_has_unknown_order(self):
        self.readings([1, 3, 5])
        self.maintenance(0)
        self.assertEqual(self.analyze().maintenance_links[0].relation, "at_anomaly")

    def test_insufficient_window_and_missing_data(self):
        response = self.analyze()
        self.assertEqual(response.sufficiency.state, "INSUFFICIENT")
        self.assertEqual(response.evidence_refs, [])
        self.readings([1])
        response = self.analyze()
        self.assertEqual(response.sufficiency.state, "INSUFFICIENT")
        self.assertIsNone(response.channels[0].rate_of_change_per_hour)

    def test_missing_maintenance_history(self):
        self.readings([1, 2, 3])
        response = self.analyze()
        self.assertEqual(response.sufficiency.state, "PARTIAL")
        self.assertIn("maintenance_history", response.sufficiency.missing_categories)

    def test_observations_hypotheses_citations_and_safe_checks(self):
        self.readings([1, 3, 5])
        response = self.analyze()
        self.assertTrue(response.hypotheses)
        self.assertTrue(response.human_approval_required)
        validate_language(response.observations, response.contradicting_evidence, response.recommended_checks)
        ids = {r.evidence_id for r in response.evidence_refs}
        self.assertTrue(all(set(o.evidence_ids) <= ids for o in response.observations))
        self.assertTrue(validate_citations(emitted=[c.evidence_id for c in response.citations],
            available=response.evidence_refs, citations=response.citations, require_citations=True).valid)
        self.assertTrue(all(not find_authorization_language(c) for c in response.recommended_checks))
        self.assertIn("unverified", response.hypotheses[0].text)
        self.assertEqual(response.hypotheses[0].confidence, 0)

    def test_no_fabricated_threshold_including_empty_object(self):
        self.readings([1, 100, 1])
        for thresholds in ({}, {"VIB": {}}):
            response = self.analyze(thresholds=thresholds)
            self.assertEqual(response.channels[0].excursions, [])
            self.assertEqual(response.channels[0].threshold_crossings, [])
            self.assertIn("supplied_thresholds", response.sufficiency.missing_categories)

    def test_deterministic_sufficiency_and_source_verification(self):
        self.readings([1, 2, 1])
        self.readings([20, 20, 20], "TEMP", "C")
        self.maintenance(-24)
        first = self.analyze()
        self.assertEqual(first.sufficiency.state, "SUFFICIENT")
        self.assertEqual(first.model_dump(), self.analyze().model_dump())
        with patch("app.services.evidence_sufficiency.source_valid", return_value=False):
            result = self.analyze()
        self.assertEqual(result.sufficiency.state, "INSUFFICIENT")
        self.assertIn("invalid_or_unavailable_source", result.sufficiency.issues)

    def test_row_cap_never_sufficient(self):
        self.readings([1, 2, 1])
        with patch.object(settings, "structured_query_max_limit", 3):
            self.assertIn("possibly_truncated_window", self.analyze().sufficiency.missing_categories)

    def test_invalid_channel_data_is_not_combined(self):
        for variant in ("unit", "duplicate", "quality", "nonfinite"):
            with self.subTest(variant=variant):
                self.session.query(SensorReading).delete()
                self.readings([1])
                if variant == "unit": self.readings([2], unit="in/s", offsets=[1])
                if variant == "duplicate": self.readings([2])
                if variant == "quality": self.readings([2], offsets=[1], quality="bad")
                if variant == "nonfinite": self.readings([float("inf")], offsets=[1])
                response = self.analyze()
                self.assertEqual(response.channels, [])
                self.assertEqual(response.sufficiency.state, "INSUFFICIENT")

    def test_unaligned_channels_and_sampling_gap(self):
        self.readings([1, 3, 5], offsets=[0, 4, 8])
        self.readings([20, 21], "TEMP", "C", offsets=[1, 2])
        response = self.analyze(thresholds={"VIB": {"maximum": 4, "expected_interval_minutes": 10}})
        self.assertIsNone(response.correlations[0].pearson_r)
        self.assertIn("sampling_gaps", response.sufficiency.missing_categories)
        self.assertIn("aligned_sensor_window", response.sufficiency.missing_categories)

    def test_channel_identifiers_are_not_diagnostic_prose(self):
        self.readings([1, 2, 3], "bearing_temperature", "C")
        self.assertTrue(self.analyze().channels)

    def test_sampling_interval_without_value_bounds(self):
        self.readings([1, 2, 3], offsets=[0, 4, 8])
        response = self.analyze(thresholds={"VIB": {"expected_interval_minutes": 10}})
        self.assertIn("sampling_gaps", response.sufficiency.missing_categories)
        self.assertIn("supplied_thresholds", response.sufficiency.missing_categories)
        self.assertEqual(response.channels[0].excursions, [])

    def test_unaligned_stable_channel_is_not_contradiction(self):
        self.readings([1, 3, 5])
        self.readings([20, 20, 20], "TEMP", "C", offsets=[6, 7, 8])
        response = self.analyze()
        self.assertEqual(response.contradicting_evidence, [])
        self.assertEqual(response.hypotheses[0].contradicting_evidence, [])

    def test_channel_limit_withholds_analysis(self):
        for index in range(17):
            self.readings([1], tag=f"S-{index}")
        response = self.analyze()
        self.assertEqual(response.channels, [])
        self.assertIn("channel_limit", response.sufficiency.missing_categories)

    def test_partly_insufficient_channel_window(self):
        self.readings([1, 2, 3])
        self.readings([20], "TEMP", "C")
        self.assertEqual(self.analyze().sufficiency.state, "INSUFFICIENT")

    def test_bounds_and_malformed_requests(self):
        for changes in ({"end": START}, {"equipment_tag": " "}, {"bogus": True},
                        {"end": START + timedelta(days=settings.agent_tool_max_window_days + 1)},
                        {"thresholds": {"VIB": {"maximum": float("inf")}}},
                        {"thresholds": {"VIB": {"minimum": 5, "maximum": 4}}}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.request(**changes)
        self.assertEqual(self.request(start=START.replace(tzinfo=None)).start, START)

    def test_real_query_bounds_equipment_and_lookback(self):
        self.readings([99, 1, 2, 99], offsets=[-1, 0, 1, 13])
        self.maintenance(-24 * 31)
        response = self.analyze()
        self.assertEqual(response.channels[0].features.maximum, 2)
        self.assertEqual(response.maintenance_links, [])
        self.assertEqual(self.analyze(equipment_tag="P-999").channels, [])

    def test_registered_tool_matches_api_contract(self):
        self.readings([1, 3, 5])
        payload, refs = invoke_tool("analyze_sensor_maintenance", self.session, self.request().model_dump(mode="json"))
        self.assertEqual(payload, self.analyze().model_dump(mode="json"))
        self.assertTrue(refs)
        with self.assertRaises(ToolArgumentError):
            invoke_tool("analyze_sensor_maintenance", self.session, {"equipment_tag": "P204"})

    def test_analysis_only_reads_database_and_leaves_no_action(self):
        self.readings([1, 3, 5])
        self.maintenance(-24)
        statements = []
        def capture(connection, cursor, statement, parameters, context, many):
            statements.append(statement)
        event.listen(self.session.bind, "before_cursor_execute", capture)
        self.addCleanup(event.remove, self.session.bind, "before_cursor_execute", capture)
        self.analyze()
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql in statements))
        self.assertFalse(self.session.new or self.session.dirty or self.session.deleted)

    def test_api_rbac_malformed_and_missing_database(self):
        app.dependency_overrides[get_db] = lambda: self.session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.addCleanup(app.dependency_overrides.pop, get_optional_current_user, None)
        body = self.request().model_dump(mode="json")
        with TestClient(app) as client:
            for role, status in ((None, 401), ("outsider", 403), ("requester", 200), ("reviewer", 200), ("admin", 200)):
                app.dependency_overrides[get_optional_current_user] = lambda: SimpleNamespace(role=role) if role else None
                self.assertEqual(client.post("/sensors/intelligence", json=body).status_code, status)
            self.assertEqual(client.post("/sensors/intelligence", json={}).status_code, 422)
            with patch("app.api.routes.sensors.analyze", side_effect=RuntimeError("private DB details")):
                result = client.post("/sensors/intelligence", json=body)
                self.assertEqual(result.status_code, 503)
                self.assertNotIn("private DB details", result.text)


if __name__ == "__main__":
    unittest.main()
