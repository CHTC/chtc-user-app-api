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

from sqlalchemy import Table

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
    password = os.getenv("POSTGRES_PASSWORD", "password")
    db = os.getenv("POSTGRES_DB", "chtc-userapp")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}?sslmode=disable"


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


def _is_view_table(table) -> bool:
    """Return True if a mapped Table should be treated as a view.

    We detect this via the SQLAlchemy Table.info mapping, expecting
    something like table.info["is_view"] == True. If the flag is
    missing or falsey, we treat the object as a real table.
    """

    try:
        info = getattr(table, "info", None) or {}
        return bool(info.get("is_view"))
    except Exception:
        # Be conservative: if we can't read info, assume it's a table
        return False


def _tables_for_create_all(models_module) -> List[Table]:
    """Return the subset of Table objects that should be created.

    This filters out any mapped objects whose underlying Table has
    info["is_view"] == True, so that view-like models are not included
    in metadata.create_all(). The result is ordered consistently with
    _ordered_tables(models_module).
    """

    ordered = _ordered_tables(models_module)
    tables_to_create: List[Table] = []
    for name, table in ordered:
        if not _is_view_table(table):
            tables_to_create.append(table)
    return tables_to_create


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
        import intermediate_models as models_module
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
            tables_to_create = _tables_for_create_all(models_module)
            models_module.Base.metadata.create_all(dst_engine, tables=tables_to_create)
        except Exception as e:
            print(f"DDL create_all failed: {e}")
            if drop_create:
                print("Continuing due to --drop-create; will attempt drop/create per table if needed.")

    # TRANSACTION STRATEGY
    # --------------------
    # We no longer keep a single long-running transaction for the whole
    # migration. Instead:
    #   * Optional DDL (drop/truncate) runs in its own short transaction.
    #   * Each table's bulk insert runs in its own transaction. When that
    #     with-block exits, those rows are COMMITTED (flushed) and visible
    #     for foreign keys from later tables.
    #   * Row-level fallbacks (after a batch error) run each row in its own
    #     short transaction so a single bad row can't poison anything else.
    #   * Sequence fixing at the end runs in its own transaction.

    with src_engine.connect() as src_conn:
        # Optional truncate or drop/create in a dedicated transaction
        if drop_create or truncate:
            with dst_engine.begin() as ddl_conn:
                if drop_create:
                    print("Dropping and recreating destination tables…")
                    for name, table in reversed(tables_ordered):
                        try:
                            ddl_conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{name}" CASCADE')
                        except Exception as e:
                            print(f"  Drop failed for {name}: {e}")
                    try:
                        tables_to_create = _tables_for_create_all(models_module)
                        models_module.Base.metadata.create_all(ddl_conn.connection, tables=tables_to_create)
                    except Exception as e:
                        print(f"  create_all after drop failed: {e}")
                elif truncate:
                    print("Truncating destination tables…")
                    for name, table in reversed(tables_ordered):
                        try:
                            ddl_conn.exec_driver_sql(f'TRUNCATE TABLE "{name}" RESTART IDENTITY CASCADE')
                        except Exception as e:
                            print(f"  Truncate failed for {name}: {e}")

        # Main data copy: ONE TRANSACTION PER TABLE
        for name, table in tables_ordered:
            # Each table has its own transaction; when this with-block exits,
            # all inserts into this table are COMMITTED.
            with dst_engine.begin() as dst_conn:
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
                        # Fast path: batch insert inside this table's transaction
                        dst_conn.execute(ins, payload)
                        inserted += len(payload)
                    except SQLAlchemyError as e:
                        # Provide context for first row in batch
                        print(f"  Insert error on table {name} after {_fmt_int(inserted)} rows: {e}")
                        # Row-by-row fallback, each in its own independent transaction
                        for rec in payload:
                            try:
                                with dst_engine.begin() as row_conn:
                                    row_conn.execute(ins, [rec])
                                inserted += 1
                            except SQLAlchemyError as e2:
                                print(
                                    f"    Skipped row due to error (row-level, independent tx): {e2}; "
                                    f"row keys: {list(rec.keys())}"
                                )
                    # Progress
                    if fetched % (batch_size * 10) == 0:
                        print(f"  {name}: {_fmt_int(fetched)} fetched, {_fmt_int(inserted)} inserted…")

                print(f"  {name}: done. {_fmt_int(fetched)} fetched, {_fmt_int(inserted)} inserted.")

        # Fix sequences for integer PKs named 'id' where a backing sequence exists,
        # in a separate transaction so this doesn't depend on prior tx state.
        print("Fixing Postgres sequences…")
        with dst_engine.begin() as seq_conn:
            for name, table in tables_ordered:
                if "id" in table.c and table.c["id"].primary_key:
                    try:
                        # Use 1 as fallback if table is empty
                        seq_conn.exec_driver_sql(
                            f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM \"{name}\"), 1), true)"
                        )
                        # Check if table is empty and print info
                        count_res = seq_conn.execute(text(f"SELECT COUNT(1) FROM \"{name}\""))
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
