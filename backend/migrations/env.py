"""Alembic environment. Uses the application's own engine factory so every migration
connection gets PRAGMA foreign_keys=ON, WAL and busy_timeout like normal app connections.

NOTE for future migrations: SQLite cannot ALTER most things in place; use
`with op.batch_alter_table(...)` (render_as_batch=True is already enabled for autogenerate).
"""
from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app.database.session import create_db_engine
from app.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or f"sqlite:///{get_settings().db_path.as_posix()}"


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(_url())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata,
                              render_as_batch=True, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
