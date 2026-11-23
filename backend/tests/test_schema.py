"""Structure of the schema as actually created in SQLite."""
from sqlalchemy import inspect

from app.models import EXPECTED_TABLES, Base

INDEXED_COLUMNS = {"user_id", "project_id", "experiment_run_id", "execution_id", "created_at"}


def test_exactly_the_twenty_required_tables(engine):
    assert len(EXPECTED_TABLES) == 20
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_every_table_has_primary_key_and_timestamps(engine):
    insp = inspect(engine)
    for t in EXPECTED_TABLES:
        assert insp.get_pk_constraint(t)["constrained_columns"], t
        cols = {c["name"]: c for c in insp.get_columns(t)}
        assert not cols["created_at"]["nullable"] and not cols["updated_at"]["nullable"], t


def test_every_foreign_key_declares_ondelete(engine):
    insp = inspect(engine)
    count = 0
    for t in EXPECTED_TABLES:
        for fk in insp.get_foreign_keys(t):
            count += 1
            assert fk["options"].get("ondelete") in {"CASCADE", "SET NULL", "RESTRICT"}, (t, fk)
    assert count >= 30


def test_frequently_queried_columns_are_indexed(engine):
    insp = inspect(engine)
    for t in EXPECTED_TABLES:
        covered = {i["column_names"][0] for i in insp.get_indexes(t) if i["column_names"]}
        covered |= {u["column_names"][0] for u in insp.get_unique_constraints(t)}
        for col in {c["name"] for c in insp.get_columns(t)} & INDEXED_COLUMNS:
            assert col in covered, f"{t}.{col} is not indexed"


def test_unique_constraints_exist(engine):
    insp = inspect(engine)
    def uniques(t):
        return {tuple(u["column_names"]) for u in insp.get_unique_constraints(t)}
    assert ("username",) in uniques("users") and ("email",) in uniques("users")
    assert ("user_id", "slug") in uniques("projects")
    assert ("project_id", "rel_path") in uniques("source_files")
    assert ("benchmark_key",) in uniques("benchmark_projects")
    assert ("user_id",) in uniques("user_settings")
