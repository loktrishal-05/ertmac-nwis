"""Use application settings and all registered models for migrations."""

from alembic import context
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine, pool, text
from app.core.config import settings
from app.db.base import Base
from app.db import models  # noqa: F401 -- register table metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Only display connection identity; omit password and URL query parameters.
    url = make_url(settings.database_url)
    context.config.print_stdout(
        "Database target: %s (connect timeout: %ss)",
        url.set(query={}).render_as_string(hide_password=True),
        settings.database_connect_timeout,
    )
    engine = create_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": settings.database_connect_timeout},
    )
    try:
        with engine.connect() as connection:
            # PostGIS images may expose extension-owned TIGER tables on search_path.
            # Exclude only catalog-confirmed extension objects, never application tables.
            extension_tables = set(connection.scalars(text("""SELECT c.relname FROM pg_class c
                JOIN pg_depend d ON d.objid=c.oid AND d.classid='pg_class'::regclass
                WHERE d.deptype='e' AND c.relkind IN ('r','p')""")))
            connection.commit()
            def include_name(name, type_, parent_names):
                return type_ != 'table' or name not in extension_tables
            context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True, include_name=include_name)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
