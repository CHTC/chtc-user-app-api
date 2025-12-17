from contextlib import asynccontextmanager
from typing import Optional
import asyncio

import uvicorn
from fastapi import FastAPI
from pydantic_settings import BaseSettings
from starlette.requests import Request

from userapp.api.routes import all_routers
from userapp.db import (
    connect_engine,
    dispose_engine
)


class AppSettings(BaseSettings):
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = 5432
    DB_NAME: Optional[str] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_URL: Optional[str] = None
    SECRET_KEY: str


settings = AppSettings()


@asynccontextmanager
async def setup_engine(a: FastAPI):
    """Return database client instance."""

    if settings.DB_URL is None:
        settings.DB_URL = f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"  # Fix typo DB_name -> DB_NAME

    await connect_engine(settings.DB_URL)
    yield
    await dispose_engine()


app = FastAPI(
    lifespan=setup_engine,
    openapi_prefix="./",
)

@app.middleware("http")
async def commit_db_session(request: Request, call_next):
    """
    Commit db_session before response is returned.
    """
    response = await call_next(request)
    db_session = request.state._state.get("db_session")  # noqa
    if db_session:
        await db_session.commit()
    return response

origins = [
    "http://localhost:8000",
    "http://localhost:3000",
    "http://localhost:3000/",
    "http://localhost:6006"
]

for router in all_routers:
    app.include_router(router)

async def main():
    config = uvicorn.Config("userapp.main:app", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

# To run the server, use the following command in your terminal:
if __name__ == "__main__":
    asyncio.run(main())
