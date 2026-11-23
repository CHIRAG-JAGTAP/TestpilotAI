"""Engine / session factory.

Every connection gets:  foreign_keys=ON, WAL, busy_timeout, synchronous=NORMAL.
We also apply SQLAlchemy's documented recipe for pysqlite so that BEGIN is
emitted explicitly - without it the driver runs DDL/SAVEPOINTs outside a
transaction and rollbacks are unreliable.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _url_for(path_or_url: str | Path) -> str:
    s = str(path_or_url)
    return s if s.startswith("sqlite") else f"sqlite:///{Path(s).as_posix()}"


def create_db_engine(path_or_url: str | Path, busy_timeout_ms: int | None = None) -> Engine:
    timeout_ms = busy_timeout_ms or get_settings().busy_timeout_ms
    engine = create_engine(
        _url_for(path_or_url),
        connect_args={"timeout": timeout_ms / 1000, "check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # noqa: ANN001
        dbapi_conn.isolation_level = None          # we control BEGIN ourselves
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")    # per-connection in SQLite!
        cur.execute(f"PRAGMA busy_timeout = {int(timeout_ms)}")
        cur.execute("PRAGMA journal_mode = WAL")
        cur.execute("PRAGMA synchronous = NORMAL")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):  # noqa: ANN001
        conn.exec_driver_sql("BEGIN")

    return engine


_engines: dict[str, Engine] = {}


def get_engine(db_path: str | Path | None = None) -> Engine:
    key = str(db_path or get_settings().db_path)
    if key not in _engines:
        _engines[key] = create_db_engine(key)
    return _engines[key]


def dispose_engines() -> None:
    for e in _engines.values():
        e.dispose()
    _engines.clear()


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Transactional scope: commit on success, rollback + re-raise on any error."""
    session = make_session_factory(engine or get_engine())()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as s:
        yield s
