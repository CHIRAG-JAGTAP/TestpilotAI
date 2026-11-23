import pytest
from sqlalchemy.orm import Session

from app.database.init_db import init_database
from app.database.session import create_db_engine
from app.models import (Project, SourceFile, User)


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "data" / "testpilot.db"


@pytest.fixture()
def backup_dir(tmp_path):
    return tmp_path / "backups"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Never touch the real database/storage during tests."""
    monkeypatch.setenv("TESTPILOT_DB_PATH", str(tmp_path / "data" / "testpilot.db"))
    monkeypatch.setenv("TESTPILOT_STORAGE_DIR", str(tmp_path / "storage"))


@pytest.fixture()
def engine(db_path, backup_dir):
    init_database(db_path, backup_dir)
    eng = create_db_engine(db_path)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


def make_user(s, name="alice"):
    u = User(username=name, email=f"{name}@example.com", password_hash="h" * 60)
    s.add(u); s.flush()
    return u


def make_project(s, user, name="demo"):
    p = Project(user_id=user.id, name=name, slug=name)
    s.add(p); s.flush()
    return p


def make_file(s, project, rel="calc.py"):
    f = SourceFile(project_id=project.id, rel_path=rel, storage_path=f"projects/{project.id}/{rel}",
                   sha256="0" * 64, size_bytes=10, line_count=2)
    s.add(f); s.flush()
    return f
