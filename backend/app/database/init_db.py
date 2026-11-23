"""Database initialisation: create dirs, back up before migrating, run Alembic to head."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import get_settings
from app.database import maintenance as mt


def alembic_config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(get_settings().migrations_dir))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{Path(db_path).as_posix()}")
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config(get_settings().db_path)).get_current_head()


def all_revisions() -> set[str]:
    return {r.revision for r in ScriptDirectory.from_config(
        alembic_config(get_settings().db_path)).walk_revisions()}


def init_database(db_path: Path | None = None, backup_dir: Path | None = None) -> dict:
    """Idempotent. Safe to call on every start-up.

    If an existing, non-empty database is behind the code's schema head, a backup labelled
    `pre_migration` is taken *before* any DDL runs.
    """
    settings = get_settings()
    db_path = Path(db_path or settings.db_path)
    backup_dir = Path(backup_dir or settings.backup_dir)
    for d in settings.managed_dirs + [db_path.parent, backup_dir]:
        d.mkdir(parents=True, exist_ok=True)

    current, head = mt.current_revision(db_path), head_revision()
    backup: Path | None = None
    if current != head and mt.has_user_tables(db_path):
        backup = mt.create_backup(db_path, backup_dir, label="pre_migration")

    command.upgrade(alembic_config(db_path), "head")

    health = mt.database_health(db_path, backup_dir)
    return {"db_path": str(db_path), "previous_revision": current, "revision": head,
            "migrated": current != head, "pre_migration_backup": str(backup) if backup else None,
            "healthy": health.get("healthy", False)}


def restore_database(backup_path: Path, db_path: Path | None = None,
                     backup_dir: Path | None = None) -> dict:
    """Safe restore, then migrate forward if the backup is from an older schema."""
    settings = get_settings()
    db_path = Path(db_path or settings.db_path)
    backup_dir = Path(backup_dir or settings.backup_dir)
    safety = mt.restore_backup(db_path, backup_path, backup_dir,
                               required_tables=(),
                               allowed_revisions=all_revisions())
    info = init_database(db_path, backup_dir)
    info["pre_restore_backup"] = str(safety) if safety else None
    return info
