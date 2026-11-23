"""Dependency-free smoke test for backup/restore/integrity (stdlib only).
Run:  python scripts/verify_maintenance.py"""
import sqlite3, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.database import maintenance as m  # noqa: E402

tmp = Path(tempfile.mkdtemp()); db = tmp / "t.db"; bk = tmp / "bk"
live = sqlite3.connect(db); live.execute("PRAGMA journal_mode=WAL")
live.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT);
 CREATE TABLE projects(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id));
 CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('0001');
 INSERT INTO users VALUES(1,'a'); INSERT INTO projects VALUES(1,1);""")
live.commit(); req = ["users", "projects"]

assert m.database_health(db, bk)["healthy"]
live.execute("INSERT INTO users VALUES(2,'b')"); live.commit()
b1 = m.create_backup(db, bk, "smoke")
assert m.table_counts(b1)["users"] == 2 and not list(bk.glob("*-wal"))
assert m.validate_backup(b1, req, {"0001"}).ok
junk = tmp / "junk.db"; junk.write_bytes(b"x" * 500)
assert not m.validate_backup(junk, req).ok
live.execute("DELETE FROM users WHERE id=2"); live.commit()
safety = m.restore_backup(db, b1, bk, req, {"0001"})
assert live.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2 and safety
try:
    m.restore_backup(db, junk, bk, req); sys.exit("bad backup was accepted!")
except m.RestoreError:
    pass
live.execute("INSERT INTO projects VALUES(9,999)"); live.commit()
assert not m.run_foreign_key_check(db)["ok"]
print("maintenance smoke test: PASS")
