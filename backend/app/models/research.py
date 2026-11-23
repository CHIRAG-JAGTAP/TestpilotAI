"""Refinement, mutation, benchmarks, experiments, usage, reports (tables 11-17, 20)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Entity, fk, in_list
from app.models.testing import RUN_STATUSES, STRATEGIES

STOP_REASONS = ("max_iterations", "coverage_target", "no_useful_tests", "plateau", "runtime_budget", "error")
MUTANT_STATUSES = ("killed", "survived", "timeout", "invalid", "skipped")


class RefinementIteration(Entity):
    __tablename__ = "refinement_iterations"
    __table_args__ = (
        UniqueConstraint("generation_run_id", "iteration_number",
                         name="uq_refinement_iterations_generation_run_id_iteration_number"),
        CheckConstraint("iteration_number >= 0", name="iteration_non_negative"),
        CheckConstraint("stopping_reason IS NULL OR " + in_list("stopping_reason", STOP_REASONS),
                        name="stopping_reason_valid"),
        CheckConstraint("line_coverage_pct BETWEEN 0 AND 100", name="line_pct"),
        CheckConstraint("branch_coverage_pct IS NULL OR branch_coverage_pct BETWEEN 0 AND 100", name="branch_pct"),
        CheckConstraint("tokens_reported = 1 OR (prompt_tokens IS NULL AND completion_tokens IS NULL)",
                        name="no_fabricated_tokens"),
    )
    project_id: Mapped[int] = fk("projects.id", "CASCADE")
    generation_run_id: Mapped[int] = fk("generation_runs.id", "CASCADE")
    experiment_run_id: Mapped[Optional[int]] = fk("experiment_runs.id", "SET NULL", nullable=True)
    execution_id: Mapped[Optional[int]] = fk("test_executions.id", "SET NULL", nullable=True)
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tests_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_valid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    branch_coverage_pct: Mapped[Optional[float]] = mapped_column(Float)
    newly_covered_branches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    newly_covered_detail: Mapped[Optional[Any]] = mapped_column(JSON)
    remaining_uncovered_branches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_uncovered_detail: Mapped[Optional[Any]] = mapped_column(JSON)
    generation_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    execution_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_reported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)       # NULL = not available (never guessed)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    stopping_reason: Mapped[Optional[str]] = mapped_column(String(30))  # set on the final iteration only


class MutationRun(Entity):
    __tablename__ = "mutation_runs"
    __table_args__ = (
        CheckConstraint(in_list("status", RUN_STATUSES), name="status_valid"),
        CheckConstraint("mutation_score IS NULL OR mutation_score BETWEEN 0 AND 100", name="score_pct"),
        CheckConstraint("total_mutants >= 0 AND valid_mutants >= 0 AND killed >= 0 AND survived >= 0 "
                        "AND timed_out >= 0 AND invalid_mutants >= 0", name="counts_non_negative"),
        CheckConstraint("killed + survived + timed_out <= valid_mutants", name="outcomes_le_valid"),
    )
    project_id: Mapped[int] = fk("projects.id", "CASCADE")
    suite_id: Mapped[Optional[int]] = fk("test_suites.id", "SET NULL", nullable=True)
    experiment_run_id: Mapped[Optional[int]] = fk("experiment_runs.id", "SET NULL", nullable=True)
    tool: Mapped[str] = mapped_column(String(40), nullable=False, default="mutmut")
    tool_version: Mapped[Optional[str]] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    total_mutants: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    valid_mutants: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    killed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    survived: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    timed_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    invalid_mutants: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    mutation_score: Mapped[Optional[float]] = mapped_column(Float)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)   # e.g. equivalent-mutant caveat

    results: Mapped[list["MutationResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True)


class MutationResult(Entity):
    __tablename__ = "mutation_results"
    __table_args__ = (
        UniqueConstraint("mutation_run_id", "mutant_key", name="uq_mutation_results_mutation_run_id_mutant_key"),
        CheckConstraint(in_list("status", MUTANT_STATUSES), name="status_valid"),
    )
    mutation_run_id: Mapped[int] = fk("mutation_runs.id", "CASCADE")
    mutant_key: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    lineno: Mapped[Optional[int]] = mapped_column(Integer)
    operator: Mapped[Optional[str]] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    diff: Mapped[Optional[str]] = mapped_column(Text)

    run: Mapped[MutationRun] = relationship(back_populates="results")


class BenchmarkProject(Entity):
    __tablename__ = "benchmark_projects"
    __table_args__ = (
        CheckConstraint(in_list("complexity", ("low", "medium", "high")), name="complexity_valid"),
        CheckConstraint(in_list("split", ("development", "held_out")), name="split_valid"),
    )
    benchmark_key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    complexity: Mapped[str] = mapped_column(String(10), nullable=False)
    split: Mapped[str] = mapped_column(String(15), nullable=False, default="development")
    description: Mapped[Optional[str]] = mapped_column(Text)
    expected_behavior: Mapped[Optional[str]] = mapped_column(Text)
    dependencies: Mapped[Optional[Any]] = mapped_column(JSON)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    has_existing_tests: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")


class ExperimentRun(Entity):
    __tablename__ = "experiment_runs"
    __table_args__ = (
        CheckConstraint(in_list("strategy", STRATEGIES), name="strategy_valid"),
        CheckConstraint(in_list("status", RUN_STATUSES), name="status_valid"),
        CheckConstraint("max_iterations >= 0 AND timeout_seconds > 0 AND repeat_index >= 0", name="config_valid"),
        CheckConstraint("coverage_target BETWEEN 0 AND 100", name="target_pct"),
    )
    user_id: Mapped[int] = fk("users.id", "CASCADE")
    project_id: Mapped[Optional[int]] = fk("projects.id", "SET NULL", nullable=True)
    benchmark_id: Mapped[Optional[int]] = fk("benchmark_projects.id", "RESTRICT", nullable=True)
    group_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # batches repeated runs
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    strategy: Mapped[str] = mapped_column(String(30), nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(100))
    random_seed: Mapped[Optional[int]] = mapped_column(Integer)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    coverage_target: Mapped[float] = mapped_column(Float, nullable=False, default=90.0)
    mutation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    config: Mapped[Optional[Any]] = mapped_column(JSON)       # full config snapshot incl. tool versions
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    metrics: Mapped[list["ExperimentMetric"]] = relationship(
        back_populates="experiment_run", cascade="all, delete-orphan", passive_deletes=True)


class ExperimentMetric(Entity):
    __tablename__ = "experiment_metrics"
    __table_args__ = (
        UniqueConstraint("experiment_run_id", "metric_name",
                         name="uq_experiment_metrics_experiment_run_id_metric_name"),
    )
    experiment_run_id: Mapped[int] = fk("experiment_runs.id", "CASCADE")
    metric_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    metric_value: Mapped[Optional[float]] = mapped_column(Float)   # NULL = not measurable
    unit: Mapped[Optional[str]] = mapped_column(String(30))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    experiment_run: Mapped[ExperimentRun] = relationship(back_populates="metrics")


class ModelUsage(Entity):
    __tablename__ = "model_usage"
    __table_args__ = (
        CheckConstraint("tokens_reported = 1 OR (prompt_tokens IS NULL AND completion_tokens IS NULL)",
                        name="no_fabricated_tokens"),
        CheckConstraint("(prompt_tokens IS NULL OR prompt_tokens >= 0) AND "
                        "(completion_tokens IS NULL OR completion_tokens >= 0)", name="tokens_non_negative"),
    )
    generation_run_id: Mapped[Optional[int]] = fk("generation_runs.id", "CASCADE", nullable=True)
    experiment_run_id: Mapped[Optional[int]] = fk("experiment_runs.id", "SET NULL", nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)    # rule_based | ollama
    model_name: Mapped[Optional[str]] = mapped_column(String(100))
    tokens_reported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)


class ReportHistory(Entity):
    __tablename__ = "report_history"
    __table_args__ = (
        CheckConstraint(in_list("report_format", ("pdf", "html", "csv", "json")), name="format_valid"),
    )
    user_id: Mapped[int] = fk("users.id", "CASCADE")
    project_id: Mapped[Optional[int]] = fk("projects.id", "SET NULL", nullable=True)
    experiment_run_id: Mapped[Optional[int]] = fk("experiment_runs.id", "SET NULL", nullable=True)
    report_format: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
