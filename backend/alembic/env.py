"""Use application settings and all registered models for migrations."""

from alembic import context
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine, pool
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
            context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
