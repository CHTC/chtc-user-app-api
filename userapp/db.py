#
# File of all db accesses
#
# When they can be they are made with the SQLAlchemy ORM model
#
# On the bottom you will find the methods that do not use this method
#
import datetime
from os import environ
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from fastapi import Depends

from dotenv import load_dotenv

load_dotenv()

engine: AsyncEngine = None


def get_engine():
    return engine


async def connect_engine(db_url: str) -> AsyncEngine:
    global engine

    # Make sure this is all run async
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=True, connect_args={"ssl": False})


async def dispose_engine():
    global engine
    await engine.dispose()


def get_async_session() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine)

async def session_generator(async_session_maker=Depends(get_async_session)) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        async with session.begin():
            yield session
