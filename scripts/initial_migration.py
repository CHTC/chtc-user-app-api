#!/usr/bin/env python3
"""
Initial data migration utility: copy data from a MySQL database (port 3306)
into a PostgreSQL database (port 5432) using SQLAlchemy and the project's
SQLAlchemy models in api.models.

Configuration via environment variables (recommended put into a .env file):
- MYSQL_URL        e.g. mysql+pymysql://user:pass@localhost:3306/source_db
- POSTGRES_URL     e.g. postgresql+psycopg2://user:pass@localhost:5432/target_db

Optional split variables if URLs are not provided:
- MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB
- POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

Usage examples:
  - Dry run, print table counts only:
      python scripts/initial_migration.py --dry-run

  - Truncate destination tables then migrate in dependency-safe order:
      python scripts/initial_migration.py --truncate

  - Only migrate selected tables in custom batch size:
      python scripts/initial_migration.py --tables users projects --batch-size 1000

Notes:
- The script will attempt to create destination tables if they don't exist
  based on api.models metadata, unless --skip-ddl is passed.
- After copying, it will fix Postgres sequences for integer primary keys.
- Ensure you have installed required dependencies from requirements.txt.
"""
from __future__ import annotations

import os
import sys
import argparse
from typing import List, Optional, Tuple

# Load .env early if present
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv()

# Delay heavy imports so that --help works without installed deps

def _build_mysql_url() -> str:
    url = os.getenv("MYSQL_URL")
    if url:
        return url
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "user")
    password = os.getenv("MYSQL_PASSWORD", "password")
    db = os.getenv("MYSQL_DB", "CHTCUSERAPP")
    # Use pymysql driver
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"


def _build_postgres_url() -> str:
    url = os.getenv("POSTGRES_URL") or os.getenv("DB_URL") or os.getenv("uri")
    if url:
        # Normalize driver to sync psycopg2 if async is provided
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            # Leave as-is (psycopg2 is default for postgresql://)
            pass
        return url
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "YK.+050y>)xT8]N_3Q-X3oI,")
    db = os.getenv("POSTGRES_DB", "chtc-userapp")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def _ordered_tables(models_module) -> List[Tuple[str, object]]:
    """Return a list of (table_name, Table) in a dependency-safe order.

    Uses a hardcoded order based on known FKs in api.models; falls back to
    alphabetical for any tables not listed.
    """
    Base = None
    # Identify Base and collect mapped classes
    for name in dir(models_module):
        obj = getattr(models_module, name)
        if isinstance(obj, type) and name == "Base":
            Base = obj
            break
    if Base is None:
        raise RuntimeError("Could not locate Base in api.models")

    mapped = {}
    for name in dir(models_module):
        obj = getattr(models_module, name)
        if isinstance(obj, type) and obj is not Base and hasattr(obj, "__tablename__"):
            mapped[obj.__tablename__] = obj.__table__

    preferred = [
        "groups",
        "notes",
        "projects",
        "submit_nodes",
        "users",
        "pi_projects",   # no explicit FKs defined
        "user_groups",
        "user_notes",
        "user_projects",
        "user_submits",
    ]

    ordered: List[Tuple[str, object]] = []
    for t in preferred:
        if t in mapped:
            ordered.append((t, mapped.pop(t)))
    # Append any remaining tables alphabetically
    for t in sorted(mapped.keys()):
        ordered.append((t, mapped[t]))
    return ordered


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def migrate(
    batch_size: int,
    tables: Optional[List[str]] = None,
    truncate: bool = False,
    drop_create: bool = False,
    skip_ddl: bool = False,
    dry_run: bool = False,
) -> None:
    # Heavy imports here
    from sqlalchemy import create_engine, text, select
    from sqlalchemy.engine import Engine
    from sqlalchemy.exc import SQLAlchemyError

    # Import project models
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    try:
        from api import models as models_module  # type: ignore
    except Exception as e:
        print(f"Error importing api.models: {e}", file=sys.stderr)
        sys.exit(2)

    mysql_url = _build_mysql_url()
    pg_url = _build_postgres_url()

    print("Source (MySQL):", mysql_url)
    print("Destination (Postgres):", pg_url)

    src_engine: Engine = create_engine(mysql_url, pool_pre_ping=True)
    dst_engine: Engine = create_engine(pg_url, pool_pre_ping=True)

    tables_ordered = _ordered_tables(models_module)
    if tables:
        wanted = set(tables)
        tables_ordered = [(n, t) for (n, t) in tables_ordered if n in wanted]
        missing = wanted - {n for (n, _) in tables_ordered}
        if missing:
            print(f"Warning: requested tables not found in models: {', '.join(sorted(missing))}")

    # Ensure destination tables exist (DDL)
    if not skip_ddl:
        try:
            print("Ensuring destination tables exist (create_all)…")
            models_module.Base.metadata.create_all(dst_engine)
        except Exception as e:
            print(f"DDL create_all failed: {e}")
            if drop_create:
                print("Continuing due to --drop-create; will attempt drop/create per table if needed.")

    with src_engine.connect() as src_conn, dst_engine.begin() as dst_conn:
        # Optional truncate or drop/create
        if drop_create:
            print("Dropping and recreating destination tables…")
            # Drop in reverse order to satisfy FKs
            for name, table in reversed(tables_ordered):
                try:
                    dst_conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{name}" CASCADE')
                except Exception as e:
                    print(f"  Drop failed for {name}: {e}")
            # Recreate
            try:
                models_module.Base.metadata.create_all(dst_conn.connection)
            except Exception as e:
                print(f"  create_all after drop failed: {e}")
        elif truncate:
            print("Truncating destination tables…")
            for name, table in reversed(tables_ordered):
                try:
                    dst_conn.exec_driver_sql(f'TRUNCATE TABLE "{name}" RESTART IDENTITY CASCADE')
                except Exception as e:
                    print(f"  Truncate failed for {name}: {e}")

        for name, table in tables_ordered:
            # Columns to transfer
            col_names = [c.name for c in table.columns]
            sel = select(*[table.c[c] for c in col_names])
            print(f"Table {name}: fetching from MySQL…")
            try:
                result = src_conn.execute(sel.execution_options(stream_results=True))
            except Exception as e:
                print(f"  Select failed for {name}: {e}")
                continue

            fetched = 0
            inserted = 0

            if dry_run:
                # Count rows efficiently
                try:
                    count_res = src_conn.execute(text(f"SELECT COUNT(1) FROM `{name}`"))
                    count = count_res.scalar() or 0
                    print(f"  {name}: source rows = {_fmt_int(count)}")
                except Exception as e:
                    print(f"  Count failed for {name}: {e}")
                continue

            # Prepare insert statement
            ins = table.insert()

            while True:
                rows = result.fetchmany(batch_size)
                if not rows:
                    break
                fetched += len(rows)
                # Build list[dict] preserving all columns
                payload = [dict(zip(col_names, row)) for row in rows]
                try:
                    dst_conn.execute(ins, payload)
                    inserted += len(payload)
                except SQLAlchemyError as e:
                    # Provide context for first row in batch
                    print(f"  Insert error on table {name} after {_fmt_int(inserted)} rows: {e}")
                    # Try row-by-row for this batch to continue
                    for rec in payload:
                        try:
                            dst_conn.execute(ins, [rec])
                            inserted += 1
                        except SQLAlchemyError as e2:
                            print(f"    Skipped row due to error: {e2}; row keys: {list(rec.keys())}")
                # Progress
                if fetched % (batch_size * 10) == 0:
                    print(f"  {name}: {_fmt_int(fetched)} fetched, {_fmt_int(inserted)} inserted…")

            print(f"  {name}: done. {_fmt_int(fetched)} fetched, {_fmt_int(inserted)} inserted.")

        # Fix sequences for integer PKs named 'id' where a backing sequence exists
        print("Fixing Postgres sequences…")
        for name, table in tables_ordered:
            if "id" in table.c and table.c["id"].primary_key:
                try:
                    # Use 1 as fallback if table is empty
                    dst_conn.exec_driver_sql(
                        f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM \"{name}\"), 1), true)"
                    )
                    # Check if table is empty and print info
                    count_res = dst_conn.execute(text(f"SELECT COUNT(1) FROM \"{name}\""))
                    count = count_res.scalar() or 0
                    if count == 0:
                        print(f"  {name}: table is empty, sequence set to 1.")
                except Exception as e:
                    print(f"  Sequence fix skipped for {name}: {e}")

    print("Migration completed.")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Copy data from MySQL to PostgreSQL using SQLAlchemy models.")
    p.add_argument("--batch-size", type=int, default=1000, help="Number of rows to transfer per batch")
    p.add_argument("--tables", nargs="*", help="Only migrate these tables (defaults to all in dependency-safe order)")
    p.add_argument("--truncate", action="store_true", help="TRUNCATE destination tables before inserting")
    p.add_argument("--drop-create", action="store_true", help="DROP and CREATE destination tables before inserting")
    p.add_argument("--skip-ddl", action="store_true", help="Skip create_all DDL on destination")
    p.add_argument("--dry-run", action="store_true", help="Don't insert; just print source row counts")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    try:
        migrate(
            batch_size=args.batch_size,
            tables=args.tables,
            truncate=args.truncate,
            drop_create=args.drop_create,
            skip_ddl=args.skip_ddl,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)
