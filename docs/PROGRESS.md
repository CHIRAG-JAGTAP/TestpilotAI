# Progress checklist (honest status)

| Phase | Scope | Status |
|------:|-------|--------|
| 1 | Architecture, SQLite, integrity, Alembic, transactions, backup/restore | Code complete. `maintenance.py` **verified** (stdlib). ORM/Alembic/pytest suite **verified** - full suite (67 tests) passes on a fresh install, server starts and health endpoints respond |
| 2 | Authentication + project management | not started |
| 3 | AST analysis (`engines/analyzer`) | **Done and verified** - 13 tests, stdlib only |
| 4 | Offline rule-based generation (`engines/generator`) | **Done and verified** - 15 tests; passes on correct code, kills 7/7 seeded non-equivalent bugs on benchmark b01 |
| 5 | Execution (subprocess) + coverage | not started (needs pytest-cov / coverage.py) |
| 6 | Iterative refinement | not started |
| 7 | Mutation testing | not started (needs mutmut) |
| 8 | Benchmarks + comparators | 1 of 8-12 benchmarks (`benchmarks/b01_arithmetic`) |
| 9 | Experiment engine | not started |
| 10 | React frontend | **Starter done and verified** - paste code, analyze, generate, download tests (`/api/analyze`, `/api/generate`); no auth/projects/charts yet |
| 11 | Reports, charts, DB health UI | not started |
| 12 | Integration, security review, docs | not started |

Gate: Phase 1 + 3 + 4 tests must be green on your machine (`run_tests.bat`) before Phase 5 starts.
Verification note: the build sandbox had no network, so pytest/SQLAlchemy/coverage/FastAPI/npm could not be
installed; the analyzer/generator tests were executed with a stand-in runner, the rest are written but unrun.
