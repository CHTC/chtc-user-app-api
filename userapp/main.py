from contextlib import asynccontextmanager
from typing import Optional
import asyncio
import json

import uvicorn
from fastapi import FastAPI
from pydantic_settings import BaseSettings
from starlette.requests import Request
from starlette.background import BackgroundTasks

from userapp.api.routes import all_routers
from userapp.core.models.enum import HttpRequestMethodEnum
from userapp.core.models.tables import Access
from userapp.db import (
    connect_engine,
    dispose_engine,
    get_async_session,
)


class AppSettings(BaseSettings):
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = 5432
    DB_NAME: Optional[str] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_URL: Optional[str] = None
    SECRET_KEY: str
    OIDC_CLIENT_ID: Optional[str] = None
    OIDC_CLIENT_SECRET: Optional[str] = None


settings = AppSettings()

@asynccontextmanager
async def setup_engine(a: FastAPI):
    """Return database client instance."""

    if settings.DB_URL is None:
        settings.DB_URL = f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"  # Fix typo DB_name -> DB_NAME

    # assume connect_engine returns the engine instance
    engine = await connect_engine(settings.DB_URL)

    a.state.engine = engine

    try:
        yield
    finally:
        await dispose_engine(engine)

def create_app() -> FastAPI:

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
        db_session = getattr(request.state, "db_session", None)
        if db_session:
            await db_session.commit()
        return response

    @app.middleware("http")
    async def log_access(request: Request, call_next):
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        # body will be either JSON, None, or {"raw_body": "utf8"} if JSON decoding fails
        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes) if body_bytes else None
        except (json.JSONDecodeError, ValueError):
            body = {"raw_body": body_bytes.decode("utf-8", errors="replace")}

        response = await call_next(request)

        route = request.scope.get("route")
        user_token = getattr(request.state, "user_token", None)
        api_token = getattr(request.state, "api_token", None)

        if route:
            query_string = str(request.url.query) or None
            session_maker = get_async_session(request)

            access = Access(
                user_id=user_token.user_id if user_token else None,
                token_id=api_token.token_id if api_token else None,
                method=HttpRequestMethodEnum(request.method),
                route=route.path,
                query_string=query_string,
                payload=body,
                status=response.status_code,
            )

            async def write_access_log():
                async with session_maker() as session:
                    session.add(access)
                    await session.commit()

            background_tasks = BackgroundTasks()
            background_tasks.add_task(write_access_log)
            response.background = background_tasks

        return response

    for router in all_routers:
        app.include_router(router)

    return app

async def main():
    config = uvicorn.Config("userapp.main:create_app", host="0.0.0.0", port=80, log_level="info", factory=True)
    server = uvicorn.Server(config)
    await server.serve()

# To run the server, use the following command in your terminal:
if __name__ == "__main__":
    asyncio.run(main())
