"""Opt-in real PostgreSQL validation for Phase 3C maintenance/sensor ingestion.

Creates small immutable synthetic CSV fixtures (if absent), ingests them through
the real FastAPI handlers, queries them back, verifies idempotent re-ingestion,
and confirms original source bytes/SHA-256 are unchanged."""
from datetime import date, timedelta
from hashlib import sha256
from time import perf_counter
from uuid import uuid4
import sys

from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import app


def main():
    fresh = "--fresh" in sys.argv
    run_id = uuid4().hex if fresh else None
    maintenance_name = f"phase3c_synthetic_maintenance_{run_id}.csv" if fresh else "phase3c_synthetic_maintenance.csv"
    sensor_name = f"phase3c_synthetic_sensor_{run_id}.csv" if fresh else "phase3c_synthetic_sensor.csv"

    # Fresh and reusable fixtures must never share byte-identical content: the API
    # deduplicates by SHA-256, not filename, so identical bytes under a different
    # name would collapse into the earlier file's source record.
    marker = f"fresh run {run_id}" if fresh else "reusable fixture"

    maintenance_path = settings.data_root / "raw/maintenance/work_orders" / maintenance_name
    maintenance_path.parent.mkdir(parents=True, exist_ok=True)
    if not maintenance_path.exists():
        maintenance_path.write_text(
            "equipment_tag,work_order_id,maintenance_type,failure_mode,maintenance_date,"
            "description,downtime_hours,parts_replaced,technician_notes,status\n"
            "P-204,WO-7712,corrective,bearing wear,2026-04-12,"
            "Drive-end bearing temperature investigated; lubrication corrected,4.5,"
            f"drive-end bearing,No impeller damage confirmed ({marker}),closed\n"
            "P204,WO-7713,preventive,,2026-05-03,Coupling alignment check,1.0,,Routine inspection,closed\n"
            "p-204,WO-7714,inspection,,2026-06-01,Suction strainer fouling noted,0.5,strainer,"
            "Recurring issue flagged for follow-up,open\n",
            encoding="utf-8", newline="",
        )
    sensor_path = settings.data_root / "raw/sensors/faults" / sensor_name
    sensor_path.parent.mkdir(parents=True, exist_ok=True)
    if not sensor_path.exists():
        # sensor_features_query matches on an absolute time range, so every --fresh
        # run needs its own day: otherwise repeated runs' readings would all fall
        # inside one another's query windows. The reusable fixture keeps one fixed
        # day (2026-09-16, the spec's own worked example) since it is only ever
        # written once and its rows never accumulate across non-fresh invocations.
        anchor = date(2026, 1, 1) + timedelta(days=int(run_id[:6], 16) % 3650) if fresh else date(2026, 9, 16)
        stamp = anchor.isoformat()
        marker_tag = f"MARKER-{run_id}" if fresh else "MARKER-REUSE"
        sensor_path.write_text(
            "timestamp,equipment_tag,sensor_tag,measurement,value,unit,quality\n"
            f"{stamp}T10:00:00Z,P-204,VIB-P204-01,vibration,3.1,mm/s,good\n"
            f"{stamp}T10:05:00Z,P-204,VIB-P204-01,vibration,3.3,mm/s,good\n"
            f"{stamp}T10:10:00Z,P-204,VIB-P204-01,vibration,3.4,mm/s,good\n"
            f"{stamp}T10:15:00Z,P-204,VIB-P204-01,vibration,3.5,mm/s,good\n"
            f"{stamp}T10:20:00Z,P-204,VIB-P204-01,vibration,8.2,mm/s,good\n"
            f"{stamp}T10:00:00Z,P-204,{marker_tag},fixture_marker,1,flag,good\n",
            encoding="utf-8", newline="",
        )

    maintenance_hash_before = sha256(maintenance_path.read_bytes()).hexdigest()
    sensor_hash_before = sha256(sensor_path.read_bytes()).hexdigest()

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200 and health.json()["status"] == "ok", health.text

        maintenance_body = {"source_path": f"work_orders/{maintenance_name}", "synthetic": True}
        started = perf_counter()
        result = client.post("/data/maintenance/ingest", json=maintenance_body)
        elapsed_maintenance = perf_counter() - started
        assert result.status_code == 200, result.text
        ingestion = result.json()
        assert ingestion["status"] in ("ingested", "duplicate"), ingestion
        if fresh:
            assert ingestion["status"] == "ingested"
        assert ingestion["row_count"] == 3, ingestion
        assert ingestion["source_sha256"] == maintenance_hash_before

        sensor_body = {"source_path": f"faults/{sensor_name}", "synthetic": True}
        started = perf_counter()
        sensor_result = client.post("/data/sensors/ingest", json=sensor_body)
        elapsed_sensor = perf_counter() - started
        assert sensor_result.status_code == 200, sensor_result.text
        sensor_ingestion = sensor_result.json()
        assert sensor_ingestion["status"] in ("ingested", "duplicate"), sensor_ingestion
        if fresh:
            assert sensor_ingestion["status"] == "ingested"
        assert sensor_ingestion["row_count"] == 6, sensor_ingestion  # 5 vibration points + 1 fixture marker

        history = client.get("/maintenance/history", params={"equipment_tag": "P-204"})
        assert history.status_code == 200, history.text
        history_results = history.json()["results"]
        assert len(history_results) >= 3, history_results
        assert all(r["equipment_tag"] == "P-204" for r in history_results)
        provenance = history_results[0]["citation"]
        assert provenance["source_filename"] == maintenance_name
        assert provenance["source_row_number"] >= 2

        work_order = client.get("/maintenance/work-orders/WO-7712")
        assert work_order.status_code == 200, work_order.text
        # WO-7712 is reused across every synthetic fixture this script has ever run;
        # earlier runs' records legitimately coexist, so match on this run's own file.
        wo_results = work_order.json()["results"]
        this_run = [r for r in wo_results if r["citation"]["source_filename"] == maintenance_name]
        assert len(this_run) == 1, wo_results
        assert this_run[0]["maintenance_type"] == "corrective"
        wo_results = this_run

        readings = client.get("/sensors/readings", params={"equipment_tag": "P-204", "sensor_tag": "VIB-P204-01"})
        assert readings.status_code == 200, readings.text
        reading_results = readings.json()["results"]
        assert len(reading_results) >= 5, reading_results
        # Earlier runs' VIB-P204-01 rows legitimately coexist (each on its own day);
        # isolate this run's own five points by source file, not list position.
        window = [r for r in reading_results if r["citation"]["source_filename"] == sensor_name]
        assert len(window) == 5, reading_results

        latest = client.get("/sensors/latest", params={"equipment_tag": "P-204"})
        assert latest.status_code == 200, latest.text
        assert any(r["sensor_tag"] == "VIB-P204-01" for r in latest.json()["results"])

        window_start = min(r["timestamp"] for r in window)
        window_end = max(r["timestamp"] for r in window)
        features = client.post("/sensors/features", json={
            "equipment_tag": "P-204", "sensor_tag": "VIB-P204-01",
            "start": window_start, "end": window_end,
        })
        assert features.status_code == 200, features.text
        feature_body = features.json()
        assert feature_body["features"]["count"] == 5, feature_body
        assert feature_body["features"]["first_value"] == 3.1
        assert feature_body["features"]["last_value"] == 8.2
        assert any(o["kind"] == "relative_increase" for o in feature_body["observations"]), feature_body
        for word in ("bearing failure", "cavitation", "impeller damage"):
            assert word not in feature_body["observations"].__repr__().lower()

        repeat_maintenance = client.post("/data/maintenance/ingest", json=maintenance_body)
        assert repeat_maintenance.status_code == 200
        assert repeat_maintenance.json()["status"] == "duplicate"
        assert repeat_maintenance.json()["source_id"] == ingestion["source_id"]

        repeat_sensor = client.post("/data/sensors/ingest", json=sensor_body)
        assert repeat_sensor.status_code == 200
        assert repeat_sensor.json()["status"] == "duplicate"
        assert repeat_sensor.json()["source_id"] == sensor_ingestion["source_id"]

        history_after_repeat = client.get("/maintenance/history", params={"equipment_tag": "P-204"})
        assert len(history_after_repeat.json()["results"]) == len(history_results), "duplicate re-ingest must not add rows"
        readings_after_repeat = client.get("/sensors/readings", params={"equipment_tag": "P-204", "sensor_tag": "VIB-P204-01"})
        assert len(readings_after_repeat.json()["results"]) == len(reading_results), "duplicate re-ingest must not add rows"

    maintenance_hash_after = sha256(maintenance_path.read_bytes()).hexdigest()
    sensor_hash_after = sha256(sensor_path.read_bytes()).hexdigest()
    assert maintenance_hash_after == maintenance_hash_before, "source bytes must never be mutated"
    assert sensor_hash_after == sensor_hash_before, "source bytes must never be mutated"

    print("Phase 3C smoke validation passed.")
    print(f"  maintenance ingest: {ingestion['status']} in {elapsed_maintenance:.2f}s, "
          f"{ingestion['row_count']} rows, sha256={maintenance_hash_after[:12]}...")
    print(f"  sensor ingest: {sensor_ingestion['status']} in {elapsed_sensor:.2f}s, "
          f"{sensor_ingestion['row_count']} rows, sha256={sensor_hash_after[:12]}...")
    print(f"  maintenance history rows for P-204: {len(history_results)}")
    print(f"  WO-7712 lookup: {wo_results[0]['maintenance_type']}")
    print(f"  sensor readings for VIB-P204-01: {len(reading_results)}")
    print(f"  feature window observations: {[o['kind'] for o in feature_body['observations']]}")


if __name__ == "__main__":
    main()
