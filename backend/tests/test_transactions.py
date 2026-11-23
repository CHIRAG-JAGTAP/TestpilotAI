import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.session import create_db_engine, session_scope
from app.models import Project, User
from tests.conftest import make_user


def test_session_scope_commits_on_success(engine):
    with session_scope(engine) as s:
        make_user(s, "carol")
    with session_scope(engine) as s:
        assert s.scalar(select(User).where(User.username == "carol")) is not None


def test_session_scope_rolls_back_on_exception(engine):
    with pytest.raises(RuntimeError):
        with session_scope(engine) as s:
            make_user(s, "dave")
            raise RuntimeError("boom")
    with session_scope(engine) as s:
        assert s.scalar(select(User).where(User.username == "dave")) is None


def test_multi_statement_operation_is_atomic(engine):
    """User + project are created together; if the project violates a constraint, the user must vanish too."""
    with pytest.raises(IntegrityError):
        with session_scope(engine) as s:
            u = make_user(s, "erin")
            s.add(Project(user_id=u.id, name="p", slug="p", status="not_a_status"))
            s.flush()
    with session_scope(engine) as s:
        assert s.scalar(select(User).where(User.username == "erin")) is None


def test_data_persists_after_engine_is_closed_and_reopened(engine, db_path):
    with session_scope(engine) as s:
        make_user(s, "frank")
    engine.dispose()                                   # "close the application"
    fresh = create_db_engine(db_path)
    try:
        with session_scope(fresh) as s:
            assert s.scalar(select(User).where(User.username == "frank")) is not None
    finally:
        fresh.dispose()


def test_concurrent_writer_waits_instead_of_failing_immediately(engine, db_path):
    """busy_timeout: a second writer blocked by an open write transaction fails only after waiting."""
    import time
    from sqlalchemy import text
    short = create_db_engine(db_path, busy_timeout_ms=300)
    try:
        with engine.connect() as holder:
            holder.execute(text("INSERT INTO users (username,email,password_hash) VALUES ('w','w@x.io','h')"))
            t0 = time.monotonic()
            with pytest.raises(Exception) as exc:
                with short.connect() as other:
                    other.execute(text("INSERT INTO users (username,email,password_hash) VALUES ('v','v@x.io','h')"))
            assert "locked" in str(exc.value).lower()
            assert time.monotonic() - t0 >= 0.25        # it really waited for the timeout
            holder.rollback()
    finally:
        short.dispose()
