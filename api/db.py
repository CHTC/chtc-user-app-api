#
# File of all db accesses
#
# When they can be they are made with the SQLAlchemy ORM model
#
# On the bottom you will find the methods that do not use this method
#
import datetime
from os import environ

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession


from dotenv import load_dotenv

import schemas as schemas

load_dotenv()

engine: AsyncEngine = None


def get_engine():
    return engine


async def connect_engine(db_url: str) -> AsyncEngine:
    global engine

    # Make sure this is all run async
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)

    async with engine.begin() as conn:
        await conn.run_sync(schemas.Base.metadata.create_all)


async def dispose_engine():
    global engine
    await engine.dispose()


def get_async_session(engine: AsyncEngine, **kwargs) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, **kwargs)


