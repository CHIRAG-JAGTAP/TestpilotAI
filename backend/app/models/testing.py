"""Generation, suites, cases, executions, logs, coverage (tables 5-10)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Entity, fk, in_list

STRATEGIES = ("existing", "one_shot", "rule_based", "iterative", "hypothesis", "pynguin")
RUN_STATUSES = ("pending", "running", "completed", "failed", "cancelled")
EXEC_STATUSES = ("queued", "running", "passed", "failed", "error", "timeout")
LOG_STREAMS = ("stdout", "stderr", "traceback", "collection")


class GenerationRun(Entity):
    __tablename__ = "generation_runs"
    __table_args__ = (
        CheckConstraint(in_list("strategy", STRATEGIES), name="strategy_valid"),
        CheckConstraint(in_list("status", RUN_STATUSES), name="status_valid"),
    )
    project_id: Mapped[int] = fk("projects.id", "CASCADE")
    strategy: Mapped[str] = mapped_column(String(30), nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(100))   # NULL for offline rule-based runs
    random_seed: Mapped[Optional[int]] = mapped_column(Integer)
    config: Mapped[Optional[Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)


class TestSuite(Entity):
    __test__ = False  # not a pytest class
    __tablename__ = "test_suites"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_test_suites_project_id_name"),
        CheckConstraint(in_list("kind", STRATEGIES), name="kind_valid"),
        CheckConstraint("iteration_number >= 0", name="iteration_non_negative"),
    )
    project_id: Mapped[int] = fk("projects.id", "CASCADE")
    generation_run_id: Mapped[Optional[int]] = fk("generation_runs.id", "SET NULL", nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000))   # generated .py file
    sha256: Mapped[Optional[str]] = mapped_column(String(64))

    cases: Mapped[list["TestCase"]] = relationship(
        back_populates="suite", cascade="all, delete-orphan", passive_deletes=True)


class TestCase(Entity):
    __test__ = False
    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("suite_id", "name", name="uq_test_cases_suite_id_name"),
        CheckConstraint("origin_iteration >= 0", name="iteration_non_negative"),
    )
    suite_id: Mapped[int] = fk("test_suites.id", "CASCADE")
    function_id: Mapped[Optional[int]] = fk("functions.id", "SET NULL", nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario_category: Mapped[Optional[str]] = mapped_column(String(40))  # boundary, negative, exception...
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    origin_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    strategy_metadata: Mapped[Optional[Any]] = mapped_column(JSON)

    suite: Mapped[TestSuite] = relationship(back_populates="cases")


class TestExecution(Entity):
    __test__ = False
    __tablename__ = "test_executions"
    __table_args__ = (
        CheckConstraint(in_list("status", EXEC_STATUSES), name="status_valid"),
        CheckConstraint("total_tests >= 0 AND passed >= 0 AND failed >= 0 AND errors >= 0 AND skipped >= 0",
                        name="counts_non_negative"),
    )
    project_id: Mapped[int] = fk("projects.id", "CASCADE")
    suite_id: Mapped[int] = fk("test_suites.id", "CASCADE")
    experiment_run_id: Mapped[Optional[int]] = fk("experiment_runs.id", "SET NULL", nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    total_tests: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    python_version: Mapped[Optional[str]] = mapped_column(String(40))
    pytest_version: Mapped[Optional[str]] = mapped_column(String(40))

    logs: Mapped[list["ExecutionLog"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan", passive_deletes=True)
    coverage: Mapped[list["CoverageResult"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan", passive_deletes=True)


class ExecutionLog(Entity):
    __tablename__ = "execution_logs"
    __table_args__ = (
        UniqueConstraint("execution_id", "sequence", name="uq_execution_logs_execution_id_sequence"),
        CheckConstraint(in_list("stream", LOG_STREAMS), name="stream_valid"),
    )
    execution_id: Mapped[int] = fk("test_executions.id", "CASCADE")
    test_case_id: Mapped[Optional[int]] = fk("test_cases.id", "SET NULL", nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stream: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[Optional[str]] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    execution: Mapped[TestExecution] = relationship(back_populates="logs")


class CoverageResult(Entity):
    """One row per (execution, file). Line and branch coverage are kept strictly separate."""
    __tablename__ = "coverage_results"
    __table_args__ = (
        UniqueConstraint("execution_id", "file_path", name="uq_coverage_results_execution_id_file_path"),
        CheckConstraint("line_coverage_pct BETWEEN 0 AND 100", name="line_pct"),
        CheckConstraint("branch_coverage_pct IS NULL OR branch_coverage_pct BETWEEN 0 AND 100", name="branch_pct"),
        CheckConstraint("num_statements >= 0 AND covered_lines >= 0 AND num_branches >= 0 "
                        "AND covered_branches >= 0 AND covered_lines <= num_statements "
                        "AND covered_branches <= num_branches", name="counts_valid"),
    )
    execution_id: Mapped[int] = fk("test_executions.id", "CASCADE")
    source_file_id: Mapped[Optional[int]] = fk("source_files.id", "SET NULL", nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    num_statements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    covered_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_lines: Mapped[Optional[Any]] = mapped_column(JSON)
    num_branches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    covered_branches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_branches: Mapped[Optional[Any]] = mapped_column(JSON)
    line_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    branch_coverage_pct: Mapped[Optional[float]] = mapped_column(Float)  # NULL when file has no branches

    execution: Mapped[TestExecution] = relationship(back_populates="coverage")
