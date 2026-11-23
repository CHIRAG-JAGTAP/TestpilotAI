"""Central configuration. Everything is overridable by environment variable so
tests (and demos) can point the app at a throw-away database."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


@dataclass(frozen=True)
class Settings:
    db_path: Path
    storage_dir: Path
    busy_timeout_ms: int = 5000

    @property
    def backup_dir(self) -> Path:
        return self.storage_dir / "backups"

    @property
    def migrations_dir(self) -> Path:
        return BACKEND_DIR / "migrations"

    @property
    def managed_dirs(self) -> list[Path]:
        s = self.storage_dir
        return [self.db_path.parent, s / "projects", s / "generated_tests",
                s / "reports", s / "coverage", s / "backups"]


def get_settings() -> Settings:
    """Read settings fresh each call (no caching) so env overrides take effect."""
    return Settings(
        db_path=Path(os.environ.get("TESTPILOT_DB_PATH", BACKEND_DIR / "data" / "testpilot.db")),
        storage_dir=Path(os.environ.get("TESTPILOT_STORAGE_DIR", PROJECT_ROOT / "storage")),
        busy_timeout_ms=int(os.environ.get("TESTPILOT_BUSY_TIMEOUT_MS", "5000")),
    )
