#
# File of all db accesses
#
# When they can be they are made with the SQLAlchemy ORM model
#
# On the bottom you will find the methods that do not use this method
#
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from fastapi import Depends
from dotenv import load_dotenv
from starlette.requests import Request

load_dotenv()

async def connect_engine(db_url: str) -> AsyncEngine:
    # Normalize URL for asyncpg
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    connect_args = {}
    if os.environ.get("PYTHON_ENV") != "production":
        connect_args["ssl"] = False

    engine: AsyncEngine = create_async_engine(db_url, connect_args=connect_args)

    return engine


async def dispose_engine(engine) -> None:
    if engine is not None:
        await engine.dispose()


def get_async_session(request: Request) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(request.app.state._state.get('engine', None), expire_on_commit=False)

async def session_generator(request: Request, async_session_maker=Depends(get_async_session)) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        async with session.begin():
            request.state.db_session = session
            yield session

