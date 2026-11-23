"""PRAGMAs must hold on EVERY connection (foreign_keys is per-connection in SQLite)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import make_user


def test_pragmas_on_every_pooled_connection(engine):
    conns = [engine.connect() for _ in range(4)]       # force several distinct connections
    try:
        for c in conns:
            assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert c.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
            assert c.execute(text("PRAGMA busy_timeout")).scalar() >= 1000
    finally:
        for c in conns:
            c.close()


def test_orphan_insert_is_rejected(session):
    with pytest.raises(IntegrityError):
        session.execute(text("INSERT INTO projects (user_id, name, slug) VALUES (9999, 'x', 'x')"))


def test_foreign_key_check_clean_after_normal_use(session, db_path):
    from app.database import maintenance as mt
    make_user(session); session.commit()
    assert mt.run_foreign_key_check(db_path)["ok"]
    assert mt.run_integrity_check(db_path)["ok"]
