"""Command-line DB tools:  python -m app.database.cli <init|health|backup|list|restore FILE>"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.database import maintenance as mt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="testpilot-db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "health", "backup", "list"):
        sub.add_parser(name)
    r = sub.add_parser("restore"); r.add_argument("file")
    args = ap.parse_args(argv)
    s = get_settings()

    if args.cmd == "init":
        from app.database.init_db import init_database
        out = init_database()
    elif args.cmd == "health":
        out = mt.database_health(s.db_path, s.backup_dir)
    elif args.cmd == "backup":
        out = {"backup": str(mt.create_backup(s.db_path, s.backup_dir, "manual"))}
    elif args.cmd == "list":
        out = mt.list_backups(s.backup_dir)
    else:
        from app.database.init_db import restore_database
        out = restore_database(Path(args.file))
    print(json.dumps(out, indent=2, default=str))
    return 0 if (args.cmd != "health" or out.get("healthy")) else 1


if __name__ == "__main__":
    sys.exit(main())
