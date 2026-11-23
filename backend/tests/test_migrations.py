import sqlite3

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.database import maintenance as mt
from app.database.init_db import alembic_config, head_revision, init_database
from app.database.session import create_db_engine
from app.models import EXPECTED_TABLES, Base


def test_fresh_init_creates_all_tables_at_head_without_backup(db_path, backup_dir):
    info = init_database(db_path, backup_dir)
    assert info["revision"] == head_revision() == mt.current_revision(db_path)
    assert info["pre_migration_backup"] is None and info["healthy"]
    assert set(mt.table_counts(db_path)) >= EXPECTED_TABLES
    assert mt.list_backups(backup_dir) == []


def test_init_is_idempotent(db_path, backup_dir):
    init_database(db_path, backup_dir)
    again = init_database(db_path, backup_dir)
    assert again["migrated"] is False and mt.list_backups(backup_dir) == []


def test_models_match_migrated_schema(db_path, backup_dir):
    """Fails when someone edits a model without writing a migration."""
    init_database(db_path, backup_dir)
    eng = create_db_engine(db_path)
    try:
        with eng.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn),
                                    Base.metadata)
        assert diff == [], diff
    finally:
        eng.dispose()


def test_backup_taken_before_migrating_existing_database(db_path, backup_dir):
    """A populated DB that is behind head (here: unversioned) is backed up BEFORE DDL runs."""
    db_path.parent.mkdir(parents=True)
    c = sqlite3.connect(db_path)
    c.executescript("CREATE TABLE legacy(id INTEGER PRIMARY KEY, note TEXT); INSERT INTO legacy VALUES(1,'keep me');")
    c.commit(); c.close()
    info = init_database(db_path, backup_dir)
    assert info["pre_migration_backup"]
    b = info["pre_migration_backup"]
    assert "pre_migration" in b
    assert "users" not in mt.table_counts(b)              # snapshot predates the migration
    assert mt.table_counts(b)["legacy"] == 1              # and contains the original data


def test_downgrade_to_base_removes_tables(db_path, backup_dir):
    init_database(db_path, backup_dir)
    command.downgrade(alembic_config(db_path), "base")
    eng = create_db_engine(db_path)
    try:
        assert not (EXPECTED_TABLES & set(inspect(eng).get_table_names()))
    finally:
        eng.dispose()
