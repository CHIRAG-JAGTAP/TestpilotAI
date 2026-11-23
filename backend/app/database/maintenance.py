"""Integrity checks, health report, backup and restore.

Deliberately stdlib-only (sqlite3) so recovery still works if the ORM layer is
broken. Backups use SQLite's online backup API - never a raw file copy of a
database that may be mid-write (WAL!).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

SQLITE_HEADER = b"SQLite format 3\x00"


class BackupError(RuntimeError):
    pass


class RestoreError(RuntimeError):
    pass


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    revision: str | None = None


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _open(path: Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=10)
    return sqlite3.connect(str(path), timeout=30)


# ---------------------------------------------------------------- checks
def run_integrity_check(db_path: Path) -> dict:
    conn = _open(db_path, readonly=True)
    try:
        rows = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "messages": [f"{type(exc).__name__}: {exc}"]}
    finally:
        conn.close()
    return {"ok": rows == ["ok"], "messages": rows}


def run_foreign_key_check(db_path: Path) -> dict:
    conn = _open(db_path, readonly=True)
    try:
        rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "violations": [{"error": str(exc)}]}
    finally:
        conn.close()
    cols = ("table", "rowid", "parent", "fkid")
    return {"ok": not rows, "violations": [dict(zip(cols, r)) for r in rows]}


def table_counts(db_path: Path) -> dict[str, int]:
    conn = _open(db_path, readonly=True)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: conn.execute(f"SELECT COUNT(*) FROM {_quote(n)}").fetchone()[0] for n in names}
    finally:
        conn.close()


def current_revision(db_path: Path) -> str | None:
    """Alembic revision stored in the DB, or None if unversioned/absent."""
    if not Path(db_path).exists():
        return None
    conn = _open(db_path, readonly=True)
    try:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    except (sqlite3.DatabaseError, TypeError):
        return None
    finally:
        conn.close()


def has_user_tables(db_path: Path) -> bool:
    if not Path(db_path).exists() or Path(db_path).stat().st_size == 0:
        return False
    try:
        return bool(table_counts(db_path))
    except sqlite3.DatabaseError:
        return True   # exists but unreadable -> treat as precious


def database_health(db_path: Path, backup_dir: Path) -> dict:
    """Everything the Settings / Database Health dashboard needs."""
    db_path = Path(db_path)
    out: dict = {"path": str(db_path), "exists": db_path.exists(), "connected": False}
    if not db_path.exists():
        return out
    try:
        conn = _open(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        out["connected"] = True
        out["journal_mode"] = mode
    except sqlite3.DatabaseError as exc:
        out["error"] = str(exc)
        return out
    out["file_size_bytes"] = db_path.stat().st_size
    out["integrity"] = run_integrity_check(db_path)
    out["foreign_keys"] = run_foreign_key_check(db_path)
    out["table_counts"] = table_counts(db_path)
    out["total_records"] = sum(out["table_counts"].values())
    out["schema_revision"] = current_revision(db_path)
    backups = list_backups(backup_dir)
    out["backup_count"] = len(backups)
    out["last_backup"] = backups[0] if backups else None
    out["healthy"] = out["integrity"]["ok"] and out["foreign_keys"]["ok"]
    return out


# ---------------------------------------------------------------- backup
_LABEL_RE = re.compile(r"[^a-z0-9_]+")


def create_backup(db_path: Path, backup_dir: Path, label: str = "manual") -> Path:
    """Consistent single-file snapshot via the SQLite backup API; verified before it is published."""
    db_path, backup_dir = Path(db_path), Path(backup_dir)
    if not db_path.exists():
        raise BackupError(f"database not found: {db_path}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    label = _LABEL_RE.sub("_", label.lower()).strip("_") or "manual"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    final = backup_dir / f"testpilot_{stamp}_{label}.db"
    partial = final.with_suffix(".db.partial")
    src = sqlite3.connect(str(db_path), timeout=30)
    dst = sqlite3.connect(str(partial))
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = DELETE")   # make the backup a self-contained single file
        dst.commit()
    except sqlite3.Error as exc:
        dst.close(); src.close(); partial.unlink(missing_ok=True)
        raise BackupError(f"backup failed: {exc}") from exc
    dst.close(); src.close()
    check = run_integrity_check(partial)
    if not check["ok"]:
        partial.unlink(missing_ok=True)
        raise BackupError(f"backup failed integrity check: {check['messages']}")
    partial.replace(final)
    return final


def list_backups(backup_dir: Path) -> list[dict]:
    """Newest first."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    files = sorted(backup_dir.glob("testpilot_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": f.name, "path": str(f), "size_bytes": f.stat().st_size,
             "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")}
            for f in files]


def prune_backups(backup_dir: Path, keep: int = 20) -> list[str]:
    removed = []
    for b in list_backups(backup_dir)[keep:]:
        Path(b["path"]).unlink(missing_ok=True)
        removed.append(b["name"])
    return removed


# ---------------------------------------------------------------- restore
def validate_backup(path: Path, required_tables: Iterable[str] = (),
                    allowed_revisions: Iterable[str] | None = None) -> ValidationResult:
    """Validate a candidate backup BEFORE it is allowed anywhere near the live DB."""
    path = Path(path)
    errors: list[str] = []
    if not path.is_file():
        return ValidationResult(False, [f"file not found: {path}"])
    with open(path, "rb") as fh:
        if fh.read(16) != SQLITE_HEADER:
            return ValidationResult(False, ["not an SQLite 3 database (bad header)"])
    try:
        integ = run_integrity_check(path)
        if not integ["ok"]:
            errors.append(f"integrity_check failed: {integ['messages'][:3]}")
        fkc = run_foreign_key_check(path)
        if not fkc["ok"]:
            errors.append(f"foreign_key_check found {len(fkc['violations'])} violation(s)")
        tables = set(table_counts(path))
        missing = set(required_tables) - tables
        if missing:
            errors.append(f"missing required tables: {sorted(missing)}")
        rev = current_revision(path)
        if allowed_revisions is not None and rev not in set(allowed_revisions):
            errors.append(f"unknown schema revision {rev!r} (backup from a newer/other version?)")
    except sqlite3.DatabaseError as exc:
        errors.append(f"cannot read database: {exc}")
        rev = None
    return ValidationResult(not errors, errors, rev)


def restore_backup(db_path: Path, backup_path: Path, backup_dir: Path,
                   required_tables: Iterable[str] = (),
                   allowed_revisions: Iterable[str] | None = None) -> Path | None:
    """Validate -> safety backup of live DB -> copy via backup API -> re-verify -> auto-rollback on failure.

    Writing *through SQLite* (instead of swapping files) keeps other open
    connections consistent and avoids Windows "file in use" errors.
    Returns the path of the pre-restore safety backup (None if there was no live DB).
    """
    db_path, backup_path = Path(db_path), Path(backup_path)
    verdict = validate_backup(backup_path, required_tables, allowed_revisions)
    if not verdict.ok:
        raise RestoreError("backup rejected, live database untouched: " + "; ".join(verdict.errors))

    safety: Path | None = None
    if db_path.exists() and has_user_tables(db_path):
        safety = create_backup(db_path, backup_dir, label="pre_restore")

    src = _open(backup_path, readonly=True)
    dst = sqlite3.connect(str(db_path), timeout=30)
    try:
        src.backup(dst)
        dst.commit()
    except sqlite3.Error as exc:
        src.close(); dst.close()
        _rollback_to(db_path, safety)
        raise RestoreError(f"restore failed ({exc}); previous database reinstated") from exc
    src.close(); dst.close()

    post = validate_backup(db_path, required_tables)
    if not post.ok:
        _rollback_to(db_path, safety)
        raise RestoreError("restored database failed verification; previous database reinstated: "
                           + "; ".join(post.errors))
    return safety


def _rollback_to(db_path: Path, safety: Path | None) -> None:
    if safety is None:
        return
    src = _open(safety, readonly=True)
    dst = sqlite3.connect(str(db_path), timeout=30)
    try:
        src.backup(dst); dst.commit()
    finally:
        src.close(); dst.close()
