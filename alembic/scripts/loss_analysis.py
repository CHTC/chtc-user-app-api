#!/usr/bin/env python3
"""
Loss analysis for f3a9c2e81d04_convert_staff_fields_to_user_ids.
"""
from __future__ import annotations

import os
import sys

import sqlalchemy as sa

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    print("Warning: .env file not loaded", file=sys.stderr)
    pass



def _build_postgres_url() -> str:
    url = os.getenv("DB_URL") or os.getenv("uri")
    if url:
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        return url
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "password")
    db = os.getenv("DB_NAME", "chtc-userapp")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def _print_unmatched(label: str, values: list[str]) -> None:
    if values:
        print(f"  {label}:")
        for v in values:
            print(f"    - {v!r}")
    else:
        print(f"  {label}: (none)")


def run(bind) -> None:
    print("=== Values that will become NULL after migration: ===\n")

    # groups.point_of_contact match by username
    rows = bind.execute(sa.text("""
        SELECT DISTINCT point_of_contact
        FROM groups
        WHERE point_of_contact IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM users u WHERE u.username = groups.point_of_contact
          )
        ORDER BY point_of_contact
    """)).fetchall()
    _print_unmatched("groups.point_of_contact", [r[0] for r in rows])

    # notes.author match by stringified id or username
    rows = bind.execute(sa.text("""
        SELECT DISTINCT author
        FROM notes
        WHERE author IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM users u
              WHERE u.id::text = notes.author
                 OR u.username    = notes.author
          )
        ORDER BY author
    """)).fetchall()
    _print_unmatched("notes.author", [r[0] for r in rows])

    # projects.staff1 match by username
    rows = bind.execute(sa.text("""
        SELECT DISTINCT staff1
        FROM projects
        WHERE staff1 IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM users u WHERE u.username = projects.staff1
          )
        ORDER BY staff1
    """)).fetchall()
    _print_unmatched("projects.staff1", [r[0] for r in rows])

    # projects.staff2 match by username
    rows = bind.execute(sa.text("""
        SELECT DISTINCT staff2
        FROM projects
        WHERE staff2 IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM users u WHERE u.username = projects.staff2
          )
        ORDER BY staff2
    """)).fetchall()
    _print_unmatched("projects.staff2", [r[0] for r in rows])

    print("\n=== Done ===")


if __name__ == "__main__":
    url = _build_postgres_url()
    print(f"Connecting to: {url}\n")
    engine = sa.create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            run(conn)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
