"""Phase 3C maintenance/sensor structured-data tests. No diagnostic inference is ever asserted true."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as ORMSession
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.models.equipment import Equipment
from app.db.models.maintenance_record import MaintenanceRecord
from app.db.models.sensor_reading import SensorReading
from app.db.models.structured_data_source import StructuredDataSource
from app.db.session import get_db
from app.main import app
from app.schemas.structured import MaintenanceIngestRequest, SensorIngestRequest, SensorFeatureRequest, SensorFeatureThresholds
from app.services.equipment_tags import normalize_equipment_tag, find_or_create_equipment
from app.services.structured_paths import resolve_structured_source, read_csv_source, decode_csv
from app.services.maintenance_data import parse_maintenance_csv, ingest_maintenance
from app.services.sensor_data import parse_sensor_csv, ingest_sensor
from app.services.sensor_features import compute_features, detect_anomalies
from app.services.structured_queries import (
    maintenance_history, work_order_lookup, sensor_readings_query, sensor_latest, sensor_features_query,
)
from app.services.ingestion import IngestionConflict

FORBIDDEN_WORDS = ("bearing", "failure", "damage", "cavitation", "diagnos", "impeller")


class StructuredMemorySession:
    """Only persistence is replaced; exercises the real ingestion/API code (mirrors test_pid.MemorySession)."""
    def __init__(self):
        self.equipment = {}
        self.sources = {}
        self.records = {}

    def _table(self, entity):
        return {Equipment: self.equipment, StructuredDataSource: self.sources}[entity]

    def scalar(self, statement, params=None):
        if params is not None:
            return True  # PostgreSQL advisory lock exercised separately by live validation.
        entity = statement.column_descriptions[0]["entity"]
        table = self._table(entity)
        compiled = statement.compile().params
        value = next(iter(compiled.values()))
        attribute = next(iter(compiled.keys())).rsplit("_", 1)[0]
        return next((row for row in table.values() if getattr(row, attribute) == value), None)

    def get(self, model, identifier):
        return self.equipment.get(identifier) or self.sources.get(identifier)

    def add(self, record):
        if isinstance(record, Equipment):
            self.equipment[record.id] = record
        elif isinstance(record, StructuredDataSource):
            self.sources[record.id] = record
        else:
            self.records[record.id] = record

    def flush(self):
        pass

    def commit(self):
        pass


def sqlite_session():
    # TestClient dispatches requests on a worker thread; StaticPool keeps every
    # thread on the SAME in-memory connection instead of each getting a private,
    # empty :memory: database (SQLAlchemy's default SingletonThreadPool behavior).
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Equipment.__table__, MaintenanceRecord.__table__, SensorReading.__table__])
    return ORMSession(engine)


class StructuredPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.patch = patch.object(settings, "data_root", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.root / "raw/maintenance").mkdir(parents=True)
        (self.root / "raw/sensors").mkdir(parents=True)

    def test_path_traversal_and_format_restrictions(self):
        path = self.root / "raw/maintenance/work_orders.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("equipment_tag\nP-204\n", encoding="utf-8")
        self.assertEqual(resolve_structured_source("work_orders.csv", "maintenance"), path.resolve())
        for name in ("../../.env", "../work_orders.csv", str(path), "C:\\Windows\\file.csv",
                     "https://host/x.csv", "work_orders.txt", "work_orders.csv:stream"):
            with self.assertRaises(ValueError, msg=name):
                resolve_structured_source(name, "maintenance")
        with self.assertRaises(ValueError):
            resolve_structured_source("work_orders.csv", "sensors")

    def test_size_and_encoding_validation(self):
        path = self.root / "raw/sensors/readings.csv"
        path.write_bytes("timestamp\n2026-01-01T00:00:00Z\n".encode("utf-8"))
        with patch.object(settings, "structured_csv_max_bytes", 2):
            with self.assertRaises(ValueError):
                read_csv_source(path)
        source = read_csv_source(path)
        self.assertIn("timestamp", decode_csv(source))
        with self.assertRaises(ValueError):
            decode_csv(b"\xff\xfe\x00not-utf8")

    def test_symlink_escape_is_rejected(self):
        outside = self.root / "outside.csv"
        outside.write_text("equipment_tag\nP-204\n", encoding="utf-8")
        link = self.root / "raw/maintenance/link.csv"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Host does not permit creating symlinks")
        with self.assertRaises(ValueError):
            resolve_structured_source("link.csv", "maintenance")


class EquipmentTagTests(unittest.TestCase):
    def test_bare_tag_dash_insertion_is_conservative(self):
        self.assertEqual(normalize_equipment_tag("P204"), "P-204")
        self.assertEqual(normalize_equipment_tag("P-204"), "P-204")
        self.assertEqual(normalize_equipment_tag("p-204"), "P-204")
        self.assertEqual(normalize_equipment_tag("p204"), "P-204")
        self.assertEqual(normalize_equipment_tag("P101A"), "P-101A")
        # Ambiguous spellings are never forced into a known shape.
        self.assertEqual(normalize_equipment_tag("PUMP-204-MAIN"), "PUMP-204-MAIN")
        self.assertEqual(normalize_equipment_tag("XP101"), "XP101")

    def test_find_or_create_deduplicates_variant_spellings(self):
        session = StructuredMemorySession()
        first = find_or_create_equipment(session, "P204")
        second = find_or_create_equipment(session, "P-204")
        third = find_or_create_equipment(session, "p-204")
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.id, third.id)
        self.assertEqual(first.equipment_tag, "P-204")
        self.assertEqual(len(session.equipment), 1)
        other = find_or_create_equipment(session, "E-101")
        self.assertNotEqual(other.id, first.id)
        self.assertEqual(len(session.equipment), 2)


class MaintenanceCSVTests(unittest.TestCase):
    def test_missing_required_header_rejected(self):
        with self.assertRaises(ValueError):
            parse_maintenance_csv("work_order_id\nWO-1\n")

    def test_parsing_normalization_and_row_rules(self):
        text = (
            "equipment_tag,work_order_id,maintenance_type,maintenance_date,downtime_hours,status,description\n"
            "P-204,WO-7712,corrective,2026-04-12,4.5,closed,Bearing investigation\n"
            "P204,WO-7713,PREVENTIVE,2026-05-03,1.0,closed,Coupling aligned\n"
            ",WO-9999,inspection,2026-05-04,0.5,open,Missing tag row\n"
            "P-204,WO-7714,mystery_type,not-a-date,not-a-number,open,Bad fields retained\n"
            "P-204,WO-7712,corrective,2026-04-12,4.5,closed,Bearing investigation\n"
        )
        rows, warnings, rejected = parse_maintenance_csv(text)
        self.assertEqual(len(rows), 3)  # 5 lines - 1 missing tag - 1 exact duplicate
        self.assertEqual(rejected, 2)
        self.assertEqual(rows[0]["maintenance_type"], "corrective")
        self.assertEqual(rows[1]["maintenance_type"], "preventive")  # lowercased
        self.assertEqual(rows[2]["maintenance_type"], "mystery_type")
        self.assertIsNone(rows[2]["maintenance_date"])
        self.assertIsNone(rows[2]["downtime_hours"])
        self.assertTrue(any("missing equipment_tag" in w for w in warnings))
        self.assertTrue(any("duplicate record skipped" in w for w in warnings))
        self.assertTrue(any("unrecognized maintenance_type" in w for w in warnings))
        self.assertTrue(any("invalid maintenance_date" in w for w in warnings))
        self.assertTrue(any("invalid downtime_hours" in w for w in warnings))
        self.assertEqual(rows[0]["source_row_number"], 2)


class SensorCSVTests(unittest.TestCase):
    def test_missing_required_headers_rejected(self):
        with self.assertRaises(ValueError):
            parse_sensor_csv("equipment_tag,sensor_tag\nP-204,VIB-01\n")

    def test_parsing_and_row_rejection(self):
        text = (
            "timestamp,equipment_tag,sensor_tag,measurement,value,unit,quality\n"
            "2026-09-16T10:00:00Z,P-204,VIB-P204-01,vibration,3.1,mm/s,good\n"
            "2026-09-16T10:05:00Z,P204,VIB-P204-01,vibration,3.3,mm/s,\n"
            "2026-09-16T10:10:00Z,P-204,VIB-P204-01,,3.4,mm/s,good\n"
            "not-a-timestamp,P-204,VIB-P204-01,vibration,3.5,mm/s,good\n"
            "2026-09-16T10:20:00Z,P-204,VIB-P204-01,vibration,not-a-number,mm/s,good\n"
            "2026-09-16T10:00:00Z,P-204,VIB-P204-01,vibration,3.1,mm/s,good\n"
            "2026-09-16T10:25:00Z,P-204,VIB-P204-01,vibration,9.9,mm/s,good\n"
            "2026-09-16T10:25:00Z,P-204,VIB-P204-01,vibration,1.1,mm/s,good\n"
        )
        rows, warnings, rejected = parse_sensor_csv(text)
        self.assertEqual(len(rows), 4)  # 2 valid + duplicate-timestamp conflicting pair, minus the exact duplicate row
        self.assertEqual(rejected, 4)  # missing measurement, bad timestamp, bad value, exact duplicate
        self.assertEqual(rows[0]["value"], 3.1)
        self.assertIsNone(rows[1]["quality"])
        self.assertTrue(any("missing measurement" in w for w in warnings))
        self.assertTrue(any("invalid timestamp" in w for w in warnings))
        self.assertTrue(any("invalid value" in w for w in warnings))
        self.assertTrue(any("conflicting reading" in w for w in warnings))
        self.assertEqual(rows[0]["raw_equipment_tag"], "P-204")
        self.assertEqual(rows[1]["raw_equipment_tag"], "P204")  # raw text preserved; normalization happens at ingest


class FeatureComputationTests(unittest.TestCase):
    def test_compute_features_matches_worked_example(self):
        values = [3.1, 3.3, 3.4, 3.5, 8.2]
        features = compute_features(values)
        self.assertEqual(features.count, 5)
        self.assertAlmostEqual(features.minimum, 3.1)
        self.assertAlmostEqual(features.maximum, 8.2)
        self.assertAlmostEqual(features.mean, 4.3)
        self.assertAlmostEqual(features.median, 3.4)
        self.assertAlmostEqual(features.first_value, 3.1)
        self.assertAlmostEqual(features.last_value, 8.2)
        self.assertAlmostEqual(features.absolute_change, 5.1)
        self.assertAlmostEqual(features.percentage_change, 5.1 / 3.1 * 100)

    def test_empty_and_rolling_window(self):
        self.assertEqual(compute_features([]).count, 0)
        features = compute_features([1, 2, 3, 4, 5], rolling_window=2)
        self.assertEqual(features.rolling_mean, [1.5, 2.5, 3.5, 4.5])
        self.assertIsNotNone(features.slope)


class AnomalyObservationTests(unittest.TestCase):
    def readings(self):
        base = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
        values = [3.1, 3.3, 3.4, 3.5, 8.2]
        return [{"value": v, "timestamp": base.replace(minute=i * 5), "quality": "good" if i < 4 else "uncertain"}
                for i, v in enumerate(values)]

    def test_relative_trend_is_threshold_independent(self):
        observations = detect_anomalies(self.readings(), SensorFeatureThresholds(), "vibration", "mm/s")
        increase = [o for o in observations if o.kind == "relative_increase"]
        self.assertEqual(len(increase), 1)
        self.assertEqual(increase[0].observation, "Latest value increased relative to preceding values in the window.")

    def test_threshold_and_gap_and_quality_observations(self):
        thresholds = SensorFeatureThresholds(maximum=7.0, minimum=3.2, max_absolute_change=1.0,
                                             expected_interval_minutes=5, stale_after_minutes=10)
        readings = self.readings()
        as_of = readings[-1]["timestamp"]
        observations = detect_anomalies(readings, thresholds, "vibration", "mm/s", as_of=as_of)
        kinds = {o.kind for o in observations}
        self.assertIn("threshold_exceeded", kinds)
        self.assertIn("threshold_below", kinds)
        self.assertIn("sudden_change", kinds)
        self.assertIn("bad_quality", kinds)
        self.assertNotIn("missing_samples", kinds)  # regular 5-minute cadence

    def test_no_observation_ever_names_a_diagnosis(self):
        thresholds = SensorFeatureThresholds(maximum=3.0, minimum=3.6, max_absolute_change=0.01,
                                              expected_interval_minutes=1, stale_after_minutes=1)
        readings = self.readings()
        observations = detect_anomalies(readings, thresholds, "vibration", "mm/s", as_of=readings[-1]["timestamp"])
        self.assertTrue(observations)
        for observation in observations:
            lowered = observation.observation.lower()
            for word in FORBIDDEN_WORDS:
                self.assertNotIn(word, lowered)

    def test_empty_readings_produce_no_observations(self):
        self.assertEqual(detect_anomalies([], SensorFeatureThresholds(), "vibration", None), [])


class MaintenanceIngestionAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.patch = patch.object(settings, "data_root", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.root / "raw/maintenance").mkdir(parents=True)

    def write(self, name, text):
        path = self.root / "raw/maintenance" / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_idempotent_reingest_conflict_and_dedup(self):
        content = (
            "equipment_tag,work_order_id,maintenance_type,maintenance_date,description\n"
            "P-204,WO-7712,corrective,2026-04-12,Bearing investigation\n"
            "P204,WO-7713,preventive,2026-05-03,Coupling aligned\n"
        )
        path = self.write("maintenance.csv", content)
        checksum = sha256(path.read_bytes()).hexdigest()
        session = StructuredMemorySession()
        app.dependency_overrides[get_db] = lambda: session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        from app.api.deps import get_optional_current_user
        from app.db.models import User
        actor = User(id=uuid4(), username="phase11-admin", role="admin")
        app.dependency_overrides[get_optional_current_user] = lambda: actor
        self.addCleanup(app.dependency_overrides.pop, get_optional_current_user)
        with TestClient(app) as client:
            body = {"source_path": "maintenance.csv", "synthetic": True}
            response = client.post("/data/maintenance/ingest", json=body)
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result["status"], "ingested")
            self.assertEqual(result["source_sha256"], checksum)
            self.assertEqual(result["row_count"], 2)
            self.assertEqual(len(session.equipment), 1)  # P-204 and P204 collapse
            self.assertEqual(len(session.records), 2)

            duplicate = client.post("/data/maintenance/ingest", json=body)
            self.assertEqual(duplicate.status_code, 200, duplicate.text)
            self.assertEqual(duplicate.json()["status"], "duplicate")
            self.assertEqual(len(session.records), 2)  # no re-insert

            conflict = client.post("/data/maintenance/ingest", json=body | {"facility_id": "other"})
            self.assertEqual(conflict.status_code, 409)

            self.assertEqual(client.post("/data/maintenance/ingest", json=body | {"source_path": "../x.csv"}).status_code, 422)
        normalized = list((self.root / "processed/maintenance/normalized").glob("*.json"))
        self.assertEqual(len(normalized), 1)


class SensorIngestionAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.patch = patch.object(settings, "data_root", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        (self.root / "raw/sensors").mkdir(parents=True)

    def write(self, name, text):
        path = self.root / "raw/sensors" / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_idempotent_reingest_and_provenance(self):
        content = (
            "timestamp,equipment_tag,sensor_tag,measurement,value,unit,quality\n"
            "2026-09-16T10:00:00Z,P-204,VIB-P204-01,vibration,3.1,mm/s,good\n"
            "2026-09-16T10:05:00Z,P-204,VIB-P204-01,vibration,3.3,mm/s,good\n"
        )
        path = self.write("sensor.csv", content)
        checksum = sha256(path.read_bytes()).hexdigest()
        session = StructuredMemorySession()
        app.dependency_overrides[get_db] = lambda: session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        from app.api.deps import get_optional_current_user
        from app.db.models import User
        actor = User(id=uuid4(), username="phase11-admin", role="admin")
        app.dependency_overrides[get_optional_current_user] = lambda: actor
        self.addCleanup(app.dependency_overrides.pop, get_optional_current_user)
        with TestClient(app) as client:
            body = {"source_path": "sensor.csv", "synthetic": True}
            response = client.post("/data/sensors/ingest", json=body)
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result["status"], "ingested")
            self.assertEqual(result["row_count"], 2)
            reading = next(iter(session.records.values()))
            self.assertEqual(reading.source_sha256, checksum)
            self.assertIn(reading.source_row_number, (2, 3))
            duplicate = client.post("/data/sensors/ingest", json=body)
            self.assertEqual(duplicate.json()["status"], "duplicate")
            self.assertEqual(len(session.records), 2)
        normalized = list((self.root / "processed/sensors/normalized").glob("*.json"))
        self.assertEqual(len(normalized), 1)


class StructuredQueryTests(unittest.TestCase):
    def setUp(self):
        self.session = sqlite_session()

    def add_equipment(self, tag):
        equipment = Equipment(id=uuid4(), equipment_tag=tag, name=tag, equipment_type="pump")
        self.session.add(equipment)
        self.session.flush()
        return equipment

    def test_maintenance_history_filters_ordering_and_citation(self):
        equipment = self.add_equipment("P-204")
        older = MaintenanceRecord(id=uuid4(), equipment_id=equipment.id, raw_equipment_tag="P-204",
                                   work_order_id="WO-1", maintenance_type="preventive",
                                   maintenance_date=datetime(2026, 1, 1), source_filename="a.csv",
                                   source_sha256="a" * 64, source_row_number=2, raw_row={})
        newer = MaintenanceRecord(id=uuid4(), equipment_id=equipment.id, raw_equipment_tag="P-204",
                                   work_order_id="WO-2", maintenance_type="corrective",
                                   maintenance_date=datetime(2026, 5, 1), source_filename="a.csv",
                                   source_sha256="a" * 64, source_row_number=3, raw_row={})
        undated = MaintenanceRecord(id=uuid4(), equipment_id=equipment.id, raw_equipment_tag="P-204",
                                     work_order_id="WO-3", maintenance_type="inspection",
                                     maintenance_date=None, source_filename="a.csv",
                                     source_sha256="a" * 64, source_row_number=4, raw_row={})
        self.session.add_all([older, newer, undated])
        self.session.commit()

        results = maintenance_history(self.session, equipment_tag="p204")
        self.assertEqual([r.work_order_id for r in results], ["WO-2", "WO-1", "WO-3"])
        self.assertEqual(results[0].equipment_tag, "P-204")
        self.assertEqual(results[0].citation.source_row_number, 3)
        self.assertEqual(results[0].citation.source_filename, "a.csv")

        self.assertEqual([r.work_order_id for r in work_order_lookup(self.session, "WO-1")], ["WO-1"])
        self.assertEqual([r.work_order_id for r in maintenance_history(self.session, maintenance_type="corrective")], ["WO-2"])
        self.assertEqual(maintenance_history(self.session, equipment_tag="E-999"), [])

    def test_sensor_readings_latest_and_features(self):
        equipment = self.add_equipment("P-204")
        base = datetime(2026, 9, 16, 10, 0, 0)
        values = [3.1, 3.3, 3.4, 3.5, 8.2]
        for i, value in enumerate(values):
            self.session.add(SensorReading(
                id=uuid4(), equipment_id=equipment.id, sensor_tag="VIB-P204-01", sensor_type="vibration",
                value=value, unit="mm/s", quality="good", timestamp=base.replace(minute=i * 5),
                source_filename="sensor.csv", source_sha256="b" * 64, source_row_number=i + 2,
            ))
        other = SensorReading(id=uuid4(), equipment_id=equipment.id, sensor_tag="TEMP-P204-01",
                               sensor_type="bearing_temperature", value=55.0, unit="C", quality="good",
                               timestamp=base, source_filename="sensor.csv", source_sha256="b" * 64,
                               source_row_number=7)
        self.session.add(other)
        self.session.commit()

        window = sensor_readings_query(self.session, equipment_tag="P204", sensor_tag="VIB-P204-01")
        self.assertEqual(len(window), 5)
        self.assertEqual([r.value for r in window], values)
        self.assertEqual(window[0].citation.source_row_number, 2)

        latest = sensor_latest(self.session, "P-204")
        self.assertEqual({r.sensor_tag for r in latest}, {"VIB-P204-01", "TEMP-P204-01"})
        vib_latest = next(r for r in latest if r.sensor_tag == "VIB-P204-01")
        self.assertEqual(vib_latest.value, 8.2)

        request = SensorFeatureRequest(equipment_tag="P-204", sensor_tag="VIB-P204-01",
                                        start=base, end=base.replace(minute=20),
                                        thresholds=SensorFeatureThresholds(maximum=7.0))
        response = sensor_features_query(self.session, request, as_of=base.replace(minute=25), write_artifact=False)
        self.assertEqual(response.features.count, 5)
        self.assertEqual(response.unit, "mm/s")
        self.assertEqual(response.measurement, "vibration")
        self.assertEqual(len(response.provenance), 5)
        self.assertTrue(any(o.kind == "threshold_exceeded" for o in response.observations))
        self.assertTrue(any(o.kind == "relative_increase" for o in response.observations))
        for observation in response.observations:
            lowered = observation.observation.lower()
            for word in FORBIDDEN_WORDS:
                self.assertNotIn(word, lowered)
        self.assertIn("sensor.csv", response.citation_label)

    def test_no_readings_window_reports_warning_not_fabrication(self):
        self.add_equipment("P-204")
        request = SensorFeatureRequest(equipment_tag="P-204", sensor_tag="MISSING-01",
                                        start=datetime(2026, 1, 1), end=datetime(2026, 1, 2))
        response = sensor_features_query(self.session, request, as_of=None, write_artifact=False)
        self.assertEqual(response.features.count, 0)
        self.assertIsNone(response.measurement)
        self.assertTrue(any("No sensor readings" in w for w in response.warnings))
        self.assertEqual(response.provenance, [])


class QueryAPITests(unittest.TestCase):
    def test_maintenance_and_sensor_routes_use_the_injected_session(self):
        session = sqlite_session()
        equipment = Equipment(id=uuid4(), equipment_tag="P-204", name="P-204", equipment_type="pump")
        session.add(equipment)
        session.flush()
        session.add(MaintenanceRecord(id=uuid4(), equipment_id=equipment.id, raw_equipment_tag="P-204",
                                       work_order_id="WO-7712", maintenance_type="corrective",
                                       maintenance_date=datetime(2026, 4, 12), source_filename="m.csv",
                                       source_sha256="c" * 64, source_row_number=2, raw_row={}))
        session.add(SensorReading(id=uuid4(), equipment_id=equipment.id, sensor_tag="VIB-P204-01",
                                   sensor_type="vibration", value=3.1, unit="mm/s", quality="good",
                                   timestamp=datetime(2026, 9, 16, 10, 0, 0), source_filename="s.csv",
                                   source_sha256="d" * 64, source_row_number=2))
        session.commit()
        app.dependency_overrides[get_db] = lambda: session
        self.addCleanup(app.dependency_overrides.pop, get_db)
        from app.api.deps import get_optional_current_user
        from app.db.models import User
        actor = User(id=uuid4(), username="phase11-requester", role="requester")
        app.dependency_overrides[get_optional_current_user] = lambda: actor
        self.addCleanup(app.dependency_overrides.pop, get_optional_current_user)
        with TestClient(app) as client:
            history = client.get("/maintenance/history", params={"equipment_tag": "P-204"})
            self.assertEqual(history.status_code, 200, history.text)
            self.assertEqual(len(history.json()["results"]), 1)

            work_order = client.get("/maintenance/work-orders/WO-7712")
            self.assertEqual(work_order.json()["results"][0]["work_order_id"], "WO-7712")

            readings = client.get("/sensors/readings", params={"equipment_tag": "P-204"})
            self.assertEqual(len(readings.json()["results"]), 1)

            latest = client.get("/sensors/latest", params={"equipment_tag": "P-204"})
            self.assertEqual(latest.json()["results"][0]["sensor_tag"], "VIB-P204-01")

            features = client.post("/sensors/features", json={
                "equipment_tag": "P-204", "sensor_tag": "VIB-P204-01",
                "start": "2026-09-16T09:00:00Z", "end": "2026-09-16T11:00:00Z",
            })
            self.assertEqual(features.status_code, 200, features.text)
            self.assertEqual(features.json()["features"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
