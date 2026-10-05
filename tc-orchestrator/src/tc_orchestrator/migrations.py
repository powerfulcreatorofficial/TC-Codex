"""Reproducible database migrations.

Migrations are plain SQL files under ``migrations/`` applied in lexical order.
Each is wrapped in a transaction and recorded in ``schema_migrations`` so they
run exactly once. No manual SQL editing is required.

Usage::

    python -m tc_orchestrator.migrations apply "$DATABASE_URL"
    python -m tc_orchestrator.migrations reset  "$DATABASE_URL"   # dev only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"

# Files must look like 0001_name.sql, 0002_name.sql, ...
_MIGRATION_RE = re.compile(r"^\d{4}_.+\.sql$")


def _migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    return sorted(p for p in MIGRATIONS_DIR.iterdir() if _MIGRATION_RE.match(p.name))


def _ensure_migration_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def _applied(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def apply_migrations(dsn: str) -> list[str]:
    """Apply all pending migrations. Returns the list of newly applied files."""
    applied_now: list[str] = []
    with psycopg.connect(dsn) as conn:
        _ensure_migration_table(conn)
        already = _applied(conn)
        for path in _migration_files():
            if path.name in already:
                continue
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)",
                        (path.name,),
                    )
            applied_now.append(path.name)
            print(f"applied {path.name}")
    return applied_now


def reset_database(dsn: str) -> None:
    """DEV ONLY: drop all Step 4 tables and re-apply migrations."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            for table in (
                "tc_learnings",
                "task_approvals",
                "task_events",
                "tasks",
                "tc_plans",
                "tc_projects",
                "schema_migrations",
            ):
                cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    apply_migrations(dsn)
    print("database reset complete")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TC orchestrator DB migrations")
    parser.add_argument("command", choices=["apply", "reset"])
    parser.add_argument("dsn", help="PostgreSQL DSN")
    args = parser.parse_args(argv)
    if args.command == "apply":
        applied = apply_migrations(args.dsn)
        print(f"migrations up to date ({len(applied)} newly applied)")
    else:
        reset_database(args.dsn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
