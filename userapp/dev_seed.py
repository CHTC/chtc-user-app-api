"""
Seed a local development database with the admin user the UI's dev login token points at.

The UI's dev nginx sends a login cookie for user 4 (chtc-user-ui scripts/dev/generate_tokens.py),
and the UI treats you as logged out unless /me finds that user. Run after `alembic upgrade head`.
Safe to run repeatedly: an existing user 4 (for example from a restored snapshot) is left alone.

    python -m userapp.dev_seed
"""
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from userapp.db import connect_engine
from userapp.core.models.tables import User

DEV_ADMIN_ID = 4


def _db_url() -> str:
    url = os.environ.get("DB_URL")
    if url:
        return url
    return (
        f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{os.environ['DB_NAME']}"
    )


async def seed() -> None:
    engine = await connect_engine(_db_url())
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            async with s.begin():
                if await s.get(User, DEV_ADMIN_ID):
                    print(f"User {DEV_ADMIN_ID} already exists, leaving it as is")
                    return
                s.add(User(id=DEV_ADMIN_ID, name="Local Dev Admin", is_admin=True, active=True, unix_uid=50000))
                await s.flush()
                # An explicit id does not advance the SERIAL sequence; move it past MAX(id)
                # so users created through the app don't collide with the seeded one.
                await s.execute(text(
                    "SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT COALESCE(MAX(id), 1) FROM users))"
                ))
                print(f"Seeded admin user {DEV_ADMIN_ID}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
