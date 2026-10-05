"""PostgreSQL connection management (psycopg3, sync).

The orchestrator's existing API/store surface is synchronous; psycopg3 is used
in sync mode to match it without forcing an async rewrite of Step 3 (which
would risk regressing verified behavior).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg


def default_dsn() -> str:
    """Resolve the DB DSN from the environment.

    Honors DATABASE_URL first, then individual TC_DB_* vars, then a sensible
    local default. Never logs the password.
    """
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    user = os.environ.get("TC_DB_USER", "tc")
    password = os.environ.get("TC_DB_PASSWORD", "tc")
    host = os.environ.get("TC_DB_HOST", "127.0.0.1")
    port = os.environ.get("TC_DB_PORT", "5432")
    dbname = os.environ.get("TC_DB_NAME", "tc")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


class Database:
    """Thin wrapper that hands out short-lived connections."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    @property
    def dsn(self) -> str:
        return self._dsn

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(self._dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return True
        except psycopg.Error:
            return False
