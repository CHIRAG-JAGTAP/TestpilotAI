"""Importing this package registers all 20 tables on Base.metadata."""
from app.models.base import Base  # noqa: F401
from app.models.core import ActivityLog, Function, Project, SourceFile, User, UserSettings  # noqa: F401
from app.models.research import (BenchmarkProject, ExperimentMetric, ExperimentRun,  # noqa: F401
                                 ModelUsage, MutationResult, MutationRun, RefinementIteration,
                                 ReportHistory)
from app.models.testing import (CoverageResult, ExecutionLog, GenerationRun, TestCase,  # noqa: F401
                                TestExecution, TestSuite)

EXPECTED_TABLES = frozenset({
    "users", "projects", "source_files", "functions", "generation_runs", "test_suites", "test_cases",
    "test_executions", "execution_logs", "coverage_results", "refinement_iterations", "mutation_runs",
    "mutation_results", "benchmark_projects", "experiment_runs", "experiment_metrics", "model_usage",
    "activity_logs", "user_settings", "report_history",
})
