"""Opt-in real PostgreSQL migration/trigger/concurrency tests in an isolated schema.

Run with WORKBENCH_TEST_POSTGRES=1 against the configured local development DB.
No SQLite concurrency claims; these tests are skipped unless explicitly enabled.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import ActionRevision
from app.schemas.query import QueryRequest
from app.services.governance import create_revision
from test_phase5a import state


@unittest.skipUnless(os.environ.get("WORKBENCH_TEST_POSTGRES") == "1", "Real PostgreSQL integration not enabled")
class PostgreSQLGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_phase5a_" + uuid4().hex
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
        # Only the uniquely named schema created by this class is removed.
        assert cls.schema.startswith("test_phase5a_") and len(cls.schema) == 45
        with cls.admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.admin.dispose()

    def setUp(self):
        self.request = QueryRequest(query="Review pump recommendation", request_id=uuid4())

    def test_concurrent_duplicate_creation_and_different_model_retry(self):
        barrier = Barrier(2)

        def persist(index):
            with Session(self.engine) as session:
                barrier.wait(timeout=10)
                revision = create_revision(session, self.request, state(summary=f"Attempt {index}"), replay=True)
                revision_id = revision.id
                session.commit()
                return revision_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(persist, index) for index in range(2)]
            ids = [future.result(timeout=30) for future in futures]
        self.assertEqual(ids[0], ids[1])
        with Session(self.engine) as session:
            count = session.scalar(select(func.count()).select_from(ActionRevision)
                                   .where(ActionRevision.request_id == self.request.request_id))
            self.assertEqual(count, 1)

    def test_raw_sql_mutation_and_invalid_binding_are_rejected(self):
        with Session(self.engine) as session:
            revision = create_revision(session, self.request, state())
            session.commit()
            revision_id = revision.id
            values = {column.name: getattr(revision, column.name) for column in ActionRevision.__table__.columns}
        for statement, params in [
            ("UPDATE action_revisions SET governance_status='APPROVED' WHERE id=:id", {"id": revision_id}),
            ("UPDATE action_revisions SET canonical_proposal='{}' WHERE id=:id", {"id": revision_id}),
            ("DELETE FROM action_revisions WHERE id=:id", {"id": revision_id}),
            ("DELETE FROM governance_requests WHERE id=:id", {"id": self.request.request_id}),
        ]:
            with self.assertRaises(DBAPIError), self.engine.begin() as connection:
                connection.execute(text(statement), params)
        for changes in ({"id": uuid4(), "canonical_proposal_hash": "0" * 64},
                        {"id": uuid4(), "canonical_request_hash": "1" * 64},
                        {"id": uuid4(), "governance_status": "APPROVED"}):
            with self.assertRaises(DBAPIError), self.engine.begin() as connection:
                connection.execute(insert(ActionRevision).values(**(values | changes)))

    def test_migration_downgrade_upgrade_and_metadata(self):
        with patch.object(settings, "database_url", self.url):
            command.downgrade(self.config, "0004_agent_runs")
            command.upgrade(self.config, "head")
            command.check(self.config)


if __name__ == "__main__":
    unittest.main()
