import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import (ActivityLog, BenchmarkProject, CoverageResult, ExecutionLog, ExperimentMetric,
                        ExperimentRun, Function, ModelUsage, Project, TestCase, TestExecution,
                        TestSuite, User, UserSettings)
from tests.conftest import make_file, make_project, make_user


def count(s, model):
    return s.scalar(select(func.count()).select_from(model))


# ------------------------------------------------------------ uniqueness
def test_duplicate_username_and_email_rejected(session):
    make_user(session, "bob")
    session.add(User(username="bob", email="other@example.com", password_hash="x"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_project_slug_unique_per_user_but_not_global(session):
    a, b = make_user(session, "a"), make_user(session, "b")
    make_project(session, a, "demo"); make_project(session, b, "demo")   # different users: fine
    session.add(Project(user_id=a.id, name="other", slug="demo"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_usernames_must_be_lowercase(session):
    session.add(User(username="Alice", email="a@example.com", password_hash="x"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_password_hash_required_unless_local_user(session):
    session.add(User(username="nopw", email="n@example.com"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.add(User(username="local", email="l@example.com", is_local_user=True))
    session.flush()


# ------------------------------------------------------------ check constraints
def test_coverage_percentage_range_enforced(session):
    u = make_user(session); p = make_project(session, u); f = make_file(session, p)
    from app.models import TestSuite as S
    s = S(project_id=p.id, name="s", kind="rule_based"); session.add(s); session.flush()
    e = TestExecution(project_id=p.id, suite_id=s.id); session.add(e); session.flush()
    session.add(CoverageResult(execution_id=e.id, file_path="calc.py", line_coverage_pct=140.0))
    with pytest.raises(IntegrityError):
        session.flush()


def test_tokens_cannot_be_fabricated(session):
    """Token counts are only allowed when explicitly flagged as reported by the model."""
    session.add(ModelUsage(provider="rule_based", prompt_tokens=123, tokens_reported=False))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.add(ModelUsage(provider="rule_based"))                    # NULL tokens: fine
    session.add(ModelUsage(provider="ollama", model_name="m", tokens_reported=True,
                           prompt_tokens=5, completion_tokens=7))     # reported: fine
    session.flush()


def test_invalid_enum_value_rejected(session):
    u = make_user(session); p = make_project(session, u)
    session.add(TestSuite(project_id=p.id, name="s", kind="made_up_strategy"))
    with pytest.raises(IntegrityError):
        session.flush()


# ------------------------------------------------------------ cascade / set null / restrict
def build_graph(s):
    u = make_user(s); p = make_project(s, u); f = make_file(s, p)
    fn = Function(source_file_id=f.id, name="add", qualified_name="add", lineno=1); s.add(fn)
    suite = TestSuite(project_id=p.id, name="s", kind="rule_based"); s.add(suite); s.flush()
    tc = TestCase(suite_id=suite.id, function_id=fn.id, name="test_add", source_code="def test_add(): pass",
                  content_hash="h"); s.add(tc)
    ex = TestExecution(project_id=p.id, suite_id=suite.id); s.add(ex); s.flush()
    s.add(ExecutionLog(execution_id=ex.id, test_case_id=tc.id, sequence=1, stream="stdout", message="."))
    s.add(CoverageResult(execution_id=ex.id, source_file_id=f.id, file_path="calc.py", line_coverage_pct=50))
    s.add(ActivityLog(user_id=u.id, project_id=p.id, action="project.create"))
    s.add(UserSettings(user_id=u.id))
    s.flush()
    return u, p, f, fn, suite, tc, ex


def test_deleting_user_cascades_through_whole_tree(session):
    u, *_ = build_graph(session)
    session.commit()
    session.execute(delete(User).where(User.id == u.id)); session.commit()
    for model in (Project, Function, TestSuite, TestCase, TestExecution, ExecutionLog, CoverageResult,
                  UserSettings):
        assert count(session, model) == 0, model.__name__


def test_activity_log_survives_user_and_project_deletion(session):
    u, p, *_ = build_graph(session); session.commit()
    session.execute(delete(User).where(User.id == u.id)); session.commit()
    log = session.scalars(select(ActivityLog)).one()
    assert log.user_id is None and log.project_id is None      # audit row kept, links nulled


def test_deleting_function_sets_test_case_link_null(session):
    *_, fn, suite, tc, ex = build_graph(session); session.commit()
    session.execute(delete(Function).where(Function.id == fn.id)); session.commit()
    session.refresh(tc)
    assert tc.function_id is None and count(session, TestCase) == 1


def test_orm_delete_of_project_cascades(session):
    u, p, *_ = build_graph(session); session.commit()
    session.delete(p); session.commit()
    assert count(session, TestSuite) == 0 and count(session, Function) == 0


def test_benchmark_with_experiment_history_cannot_be_deleted(session):
    u = make_user(session)
    b = BenchmarkProject(benchmark_key="b01", name="arith", category="arithmetic", complexity="low",
                         storage_path="benchmarks/b01")
    session.add(b); session.flush()
    session.add(ExperimentRun(user_id=u.id, benchmark_id=b.id, group_key="g1", strategy="iterative"))
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(delete(BenchmarkProject).where(BenchmarkProject.id == b.id))


def test_experiment_delete_cascades_to_metrics_and_nulls_usage(session):
    u = make_user(session)
    run = ExperimentRun(user_id=u.id, group_key="g", strategy="one_shot"); session.add(run); session.flush()
    session.add(ExperimentMetric(experiment_run_id=run.id, metric_name="branch_coverage", metric_value=61.5))
    mu = ModelUsage(provider="rule_based", experiment_run_id=run.id); session.add(mu); session.commit()
    session.execute(delete(ExperimentRun).where(ExperimentRun.id == run.id)); session.commit()
    assert count(session, ExperimentMetric) == 0
    session.refresh(mu); assert mu.experiment_run_id is None


# ------------------------------------------------------------ timestamps
def test_timestamps_set_and_updated_at_changes(session):
    u = make_user(session); session.commit()
    assert u.created_at is not None and u.updated_at is not None
    before = u.updated_at
    u.display_name = "Alice A."; session.commit()
    session.refresh(u)
    assert u.updated_at >= before and u.created_at <= u.updated_at
