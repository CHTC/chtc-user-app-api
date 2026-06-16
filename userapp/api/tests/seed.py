"""Baseline fixture data the test suite assumes exists.

This is the foundational data the per-test fixtures in conftest.py build on
(e.g. existing_admin_user returns TEST_ADMIN_ID without creating it). It runs
once per test session via the autouse fixture in conftest.py, AFTER the schema
has been built by `alembic upgrade head`.

Idempotent: rows are created only if absent, so it's safe to re-run against a
DB that's already seeded. Connection info comes from the environment (DB_URL,
or DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD) — the same vars the app reads.
"""
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from userapp.db import connect_engine
from userapp.core.models.tables import User, SubmitNode, Group


def _db_url() -> str:
    url = os.environ.get("DB_URL")
    if url:
        return url
    return (
        f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{os.environ['DB_NAME']}"
    )


async def seed_baseline() -> None:
    engine = await connect_engine(_db_url())
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        async with s.begin():
            # Submit node referenced by user_data_f (submit_node_id=1).
            if not await s.get(SubmitNode, 1):
                s.add(SubmitNode(id=1, name="seed-node"))
            # Admin matching TEST_ADMIN_ID; unix_uid set so tests reading an
            # existing user's uid have a non-null value.
            if not await s.get(User, 4):
                s.add(User(id=4, name="Seed Admin", is_admin=True, active=True, unix_uid=50000))
            # Two groups so tests that read an existing group, reference
            # group_id=1, or filter by has_groupdir have data present.
            if not await s.get(Group, 1):
                s.add(Group(id=1, name="seed-group-dir", unix_gid=55500, has_groupdir=True))
            if not await s.get(Group, 2):
                s.add(Group(id=2, name="seed-group-nodir", unix_gid=55501, has_groupdir=False))
            await s.flush()
            # Explicit ids do NOT advance the SERIAL sequences; bump each past
            # MAX(id) so app-created rows don't collide with the seeded ids.
            for table in ("submit_nodes", "users", "groups"):
                await s.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
                ))
    await engine.dispose()


if __name__ == "__main__":
    # Allows manual seeding for debugging: python -m userapp.api.tests.seed
    asyncio.run(seed_baseline())
    print("seed complete")
