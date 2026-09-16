"""
Database engine/session setup.

The DB file location is configurable with DB_PATH so the service can point at a
Render persistent disk. Everything here is defensive on purpose: a bad or
unwritable DB_PATH must never take the API down, because the API failing to
start is what leaves users staring at stale or missing listings.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

log = logging.getLogger("database")

DEFAULT_DB_PATH = "./movienearme.db"
_configured_path = os.getenv("DB_PATH", DEFAULT_DB_PATH)


def _usable_db_path(path: str) -> tuple[str, bool]:
    """
    Return (path, is_persistent).

    A configured DB_PATH usually means a mounted disk. If the directory cannot
    be created or written to (e.g. the disk was never attached because Render
    free instances do not support disks), fall back to the local file rather
    than crashing on the first query.
    """
    if path == DEFAULT_DB_PATH:
        return path, False
    parent = Path(path).parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return path, True
    except OSError as e:
        log.warning(
            "DB_PATH %s is not writable (%s) - falling back to %s. "
            "Data will NOT survive a restart.",
            path, e, DEFAULT_DB_PATH,
        )
        return DEFAULT_DB_PATH, False


DB_PATH, DB_IS_PERSISTENT = _usable_db_path(_configured_path)
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    """
    WAL lets the API keep reading the previous dataset while the scraper's
    replace transaction is still open, so a refresh is invisible to clients
    instead of blocking or exposing a half-written database.
    """
    cur = dbapi_connection.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
    except Exception as e:  # noqa: BLE001 - pragmas are best-effort
        log.warning("could not apply sqlite pragmas: %s", e)
    finally:
        cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
