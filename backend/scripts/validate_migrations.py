"""Real PostgreSQL fresh and existing-schema upgrades in disposable schemas only."""
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.core.config import settings


def main():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 5})
    try:
        for existing in (False, True):
            schema = "phase_e_migration_" + uuid4().hex
            with engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            try:
                url = make_url(settings.database_url).update_query_dict({"options": "-csearch_path=" + schema})
                with patch.object(settings, "database_url", url.render_as_string(hide_password=False)):
                    if existing:
                        command.upgrade(config, "0015_durable_execution")
                    command.upgrade(config, "head")
                    command.check(config)
                    command.upgrade(config, "head")  # Existing-head upgrade is idempotent.
            finally:
                with engine.begin() as conn:
                    conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        engine.dispose()
    print("MIGRATIONS PASS: fresh and prior-revision upgrades; alembic check; idempotent head upgrade")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
