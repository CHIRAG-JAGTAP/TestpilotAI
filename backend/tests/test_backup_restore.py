import sqlite3

import pytest
from sqlalchemy import select

from app.database import maintenance as mt
from app.database.init_db import all_revisions, restore_database
from app.database.session import session_scope
from app.models import EXPECTED_TABLES, User
from tests.conftest import make_user


def names(s):
    return sorted(s.scalars(select(User.username)))


def test_health_report_fields(engine, db_path, backup_dir):
    h = mt.database_health(db_path, backup_dir)
    assert h["connected"] and h["healthy"] and h["integrity"]["ok"] and h["foreign_keys"]["ok"]
    assert h["file_size_bytes"] > 0 and h["journal_mode"] == "wal"
    assert set(h["table_counts"]) >= EXPECTED_TABLES and h["last_backup"] is None


def test_backup_is_single_valid_file_taken_while_app_connection_is_open(engine, db_path, backup_dir):
    with session_scope(engine) as s:
        make_user(s, "gina")
    b = mt.create_backup(db_path, backup_dir)
    assert not list(backup_dir.glob("*-wal")) and not list(backup_dir.glob("*.partial"))
    v = mt.validate_backup(b, EXPECTED_TABLES, all_revisions())
    assert v.ok, v.errors
    assert mt.table_counts(b)["users"] == 1


def test_restore_roundtrip_with_safety_backup(engine, db_path, backup_dir):
    with session_scope(engine) as s:
        make_user(s, "hank")
    snap = mt.create_backup(db_path, backup_dir, "before_change")
    with session_scope(engine) as s:
        make_user(s, "ivy")
    with session_scope(engine) as s:
        assert names(s) == ["hank", "ivy"]
    info = restore_database(snap, db_path, backup_dir)
    assert info["pre_restore_backup"] and "pre_restore" in info["pre_restore_backup"]
    with session_scope(engine) as s:                       # same engine, still works after restore
        assert names(s) == ["hank"]
    # the safety backup still holds the state we just overwrote
    assert mt.table_counts(info["pre_restore_backup"])["users"] == 2


def test_invalid_backups_are_rejected_and_live_db_untouched(engine, db_path, backup_dir, tmp_path):
    with session_scope(engine) as s:
        make_user(s, "jack")
    junk = tmp_path / "junk.db"; junk.write_bytes(b"not a database" * 50)
    empty_sqlite = tmp_path / "other.db"
    c = sqlite3.connect(empty_sqlite); c.execute("CREATE TABLE x(a)"); c.commit(); c.close()
    for bad in (junk, empty_sqlite, tmp_path / "missing.db"):
        with pytest.raises(mt.RestoreError):
            mt.restore_backup(db_path, bad, backup_dir, EXPECTED_TABLES, all_revisions())
    with session_scope(engine) as s:
        assert names(s) == ["jack"]
    assert mt.run_integrity_check(db_path)["ok"]


def test_corrupted_backup_detected(engine, db_path, backup_dir, tmp_path):
    with session_scope(engine) as s:
        for i in range(30):
            make_user(s, f"user{i}")
    b = mt.create_backup(db_path, backup_dir)
    data = bytearray(b.read_bytes())
    for i in range(4096, min(len(data), 4096 + 512)):
        data[i] = 0xFF
    bad = tmp_path / "corrupt.db"; bad.write_bytes(data)
    assert not mt.validate_backup(bad, EXPECTED_TABLES).ok


def test_backup_with_fk_violations_rejected(engine, db_path, backup_dir):
    raw = sqlite3.connect(db_path)          # raw connection: foreign_keys is OFF by default
    raw.execute("INSERT INTO projects (user_id, name, slug) VALUES (4242, 'orphan', 'orphan')")
    raw.commit(); raw.close()
    assert not mt.run_foreign_key_check(db_path)["ok"]
    assert not mt.database_health(db_path, backup_dir)["healthy"]
    b = mt.create_backup(db_path, backup_dir)
    assert not mt.validate_backup(b, EXPECTED_TABLES).ok


def test_prune_keeps_newest(db_path, engine, backup_dir):
    for _ in range(5):
        mt.create_backup(db_path, backup_dir)
    mt.prune_backups(backup_dir, keep=2)
    assert len(mt.list_backups(backup_dir)) == 2
