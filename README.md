# TestPilot
**Execution- and Coverage-Guided Refinement of Python Unit Tests**

Free, offline, local-first. No API keys. SQLite is the authoritative store.

**Status: Phases 1, 3, 4 written (2, 5-12 pending) - see `docs/PROGRESS.md`.**

## Quick start (100% free, offline, no accounts or API keys)
Needs only Python 3.11+.

| | Windows | macOS / Linux |
|---|---|---|
| Run the app (auto-setup on first run) | `start.bat` | `./start.sh` |
| Run the tests | `run_tests.bat` | `./run_tests.sh` |
| Setup only | `setup.bat` | `./setup.sh` |

Then open http://127.0.0.1:8000/docs. Everything used is open source (MIT/BSD/Apache); data stays in a local SQLite file.

## Frontend (React + Vite)
Needs Node.js 18+ (free, nodejs.org). Start the backend first, then in a second terminal:
```
cd frontend
npm install
npm run dev          :: http://localhost:5173
```
Or run `start_frontend.bat` / `./start_frontend.sh`. Paste Python code, click **Analyze & generate tests**,
download the generated `test_<module>.py`. The dev server proxies `/api` to the backend on port 8000.

## PyCharm
1. **File > Open** and choose the `testpilot` folder (the one containing `backend/` and `README.md`).
2. **Settings > Project > Python Interpreter > Add Interpreter > Add Local Interpreter > Virtualenv Environment > New**.
   Set the location to `testpilot/backend/.venv` and the base interpreter to Python 3.11+.
3. Open the Terminal tab (it activates the venv) and run:
   `cd backend`, `pip install -r requirements.txt`, `python -m app.database.cli init`.
4. Pick **TestPilot Server** or **TestPilot Tests** in the run-configuration dropdown (top right) and press Run.
   If a configuration shows a red interpreter warning, edit it and choose the venv from step 2.
5. Mark `backend` as **Sources Root** (right-click > Mark Directory as) so imports like `app.main` resolve.

## Windows details
```bat
setup.bat        :: venv + dependencies + creates backend\data\testpilot.db via Alembic
run_tests.bat    :: Phase 1 acceptance tests (pytest)
backup_database.bat
```
Manual equivalent:
```bat
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m app.database.cli init       :: migrate (auto-backup first if DB already has data)
python -m app.database.cli health     :: integrity + foreign-key report (exit code 1 if unhealthy)
python -m app.database.cli backup
python -m app.database.cli restore ..\storage\backups\<file>.db
python -m pytest
uvicorn app.main:app --reload         :: http://127.0.0.1:8000/docs
```

## Database design (Phase 1)
* 20 tables, SQLAlchemy 2.0 ORM, Alembic migrations, file at `backend/data/testpilot.db`.
* Every connection: `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout`, explicit `BEGIN`.
* Explicit `ON DELETE` on every FK. CASCADE for owned data, SET NULL for audit/history links
  (activity log, test-case->function), RESTRICT for benchmarks that have experiment history.
* CHECK constraints keep the research data honest, e.g. token counts may only be stored when
  `tokens_reported = 1` - the schema itself refuses fabricated token usage.
* Backups use SQLite's online backup API (WAL-safe), are integrity-checked before being published,
  and restores are validated (header, integrity, FK check, schema revision) with an automatic
  safety backup and automatic rollback on failure.
* `app/database/maintenance.py` is stdlib-only so recovery works even if the ORM layer is broken.

## Known limitations
* `0001_initial_schema` is a baseline built from model metadata; freeze it to explicit
  `op.create_table` calls before changing models (see the file's docstring).
* Backup restore keeps the application running; for a very large DB, stop the backend first.
