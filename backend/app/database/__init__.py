"""Database package. Kept import-light on purpose: `maintenance` (backup/restore/health) is
stdlib-only and must stay usable even when SQLAlchemy is unavailable or broken.
Import engine helpers explicitly:  from app.database.session import session_scope
"""
