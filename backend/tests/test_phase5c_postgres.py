"""Opt-in real PostgreSQL Phase 5C audit-chain immutability/concurrency/
legacy checks in an isolated schema. Run with WORKBENCH_TEST_POSTGRES=1.

No SQLite concurrency or raw-SQL-trigger claims here either -- this is the
Phase 5C counterpart to test_phase5a_postgres.py/test_phase5b_postgres.py,
same isolation technique."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AuditChainHead, AuditLog
from app.services.audit import CHAIN_ID, append_event, verify_chain


@unittest.skipUnless(os.environ.get("WORKBENCH_TEST_POSTGRES") == "1", "Real PostgreSQL integration not enabled")
class PostgreSQLAuditChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_phase5c_" + uuid4().hex
        cls.admin = create_engine(settings.database_url, connect_args={"connect_timeout": 5})
        with cls.admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.addClassCleanup(cls.cleanup_schema)
        url = make_url(settings.database_url).update_query_dict({"options": f"-csearch_path={cls.schema}"})
        cls.url = url.render_as_string(hide_password=False)
        cls.engine = create_engine(url, connect_args={"connect_timeout": 5})
        cls.addClassCleanup(cls.engine.dispose)
        cls.config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.object(settings, "database_url", cls.url):
            command.upgrade(cls.config, "head")
            command.check(cls.config)

    @classmethod
    def cleanup_schema(cls):
        assert cls.schema.startswith("test_phase5c_") and len(cls.schema) == 45
        with cls.admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.admin.dispose()

    # -- IMMUTABILITY (real trigger, not the ORM/SQLAlchemy event guard) ----

    def test_raw_sql_update_of_audit_event_denied(self):
        with Session(self.engine) as session:
            record = append_event(session, event_type="LOGIN_SUCCESS", actor_id=None, actor_kind="system",
                                 payload={"n": 1})
            session.commit()
            record_id = record.id
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(text("UPDATE audit_events SET event_type='LOGIN_FAILURE' WHERE id=:id"),
                              {"id": record_id})

    def test_raw_sql_delete_of_audit_event_denied(self):
        with Session(self.engine) as session:
            record = append_event(session, event_type="LOGIN_SUCCESS", actor_id=None, actor_kind="system",
                                 payload={"n": 1})
            session.commit()
            record_id = record.id
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(text("DELETE FROM audit_events WHERE id=:id"), {"id": record_id})

    def test_event_hash_binding_check_rejects_mismatched_raw_insert(self):
        # Defense in depth: even a raw INSERT bypassing append_event cannot
        # store an event_hash that doesn't match its own canonical_event_json.
        with self.assertRaises(DBAPIError), self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO audit_events (id, schema_version, chain_id, sequence_number, occurred_at, "
                "actor_kind, event_type, payload, canonical_payload_hash, previous_hash, canonical_event_json, "
                "event_hash) VALUES (gen_random_uuid(), 'phase5c-audit-v1', :chain_id, 999, now(), 'system', "
                "'LOGIN_SUCCESS', '{}'::jsonb, repeat('0', 64), repeat('0', 64), '{}', repeat('1', 64))"
            ), {"chain_id": CHAIN_ID + "-mismatch-test"})

    # -- CONCURRENCY ----------------------------------------------------------

    def test_concurrent_appends_produce_unique_monotonic_sequence_and_one_chain(self):
        chain_id = "pg-concurrency-test-" + uuid4().hex
        workers = 8
        barrier = Barrier(workers)

        def do_append(n):
            with Session(self.engine) as session:
                barrier.wait(timeout=10)
                record = append_event(session, event_type="LOGIN_SUCCESS", actor_id=None, actor_kind="system",
                                     payload={"worker": n}, chain_id=chain_id)
                session.commit()
                return record.sequence_number

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(do_append, n) for n in range(workers)]
            sequences = [future.result(timeout=30) for future in futures]

        # Unique, monotonic, no gaps, no duplicates, no lost updates: exactly
        # {1, 2, ..., workers}.
        self.assertEqual(sorted(sequences), list(range(1, workers + 1)))

        with Session(self.engine) as session:
            result = verify_chain(session, chain_id=chain_id)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["events_checked"], workers)
        self.assertEqual(result["first_sequence"], 1)
        self.assertEqual(result["last_sequence"], workers)

        with Session(self.engine) as session:
            head = session.execute(select(AuditChainHead).where(AuditChainHead.chain_id == chain_id)).scalar_one()
        self.assertEqual(head.next_sequence_number, workers + 1)
        self.assertEqual(head.head_hash, result["head_hash"])

    # -- LEGACY (real PostgreSQL JSONB, unlike test_phase5c.py's SQLite fixture) --

    def test_legacy_audit_log_row_is_not_chained_history(self):
        with Session(self.engine) as session:
            session.add(AuditLog(event_type="legacy", actor="system", entity_type="x", entity_id=None,
                                event_data={"note": "pre-phase5c"}, previous_hash=None, current_hash=None))
            session.commit()
            result = verify_chain(session, chain_id=CHAIN_ID)
        self.assertTrue(result["valid"])
        self.assertEqual(result["events_checked"], 0)

    def test_migration_downgrade_upgrade_and_metadata(self):
        with patch.object(settings, "database_url", self.url):
            command.downgrade(self.config, "0006_phase5b_approvals")
            command.upgrade(self.config, "head")
            command.check(self.config)


if __name__ == "__main__":
    unittest.main()
