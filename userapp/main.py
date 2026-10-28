from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import asyncio
import logging
import os

import uvicorn
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from pydantic_settings import BaseSettings
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError
from starlette.requests import Request
from starlette.responses import JSONResponse

from userapp.api.routes import all_routers
from userapp.api.util import user_visible_db_message
from userapp.db import (
    connect_engine,
    dispose_engine
)

logger = logging.getLogger(__name__)


def run_migrations(db_url: str) -> None:
    """
    Run Alembic `upgrade head` synchronously.

    Idempotent: creates all tables/views/enums on an empty DB,
    no-ops on an already-migrated DB.
    """
    # alembic.ini lives at the repo root, one level above the `userapp` package.
    project_root = Path(__file__).resolve().parent.parent
    alembic_ini = project_root / "alembic.ini"

    cfg = AlembicConfig(str(alembic_ini))
    # Make sure the migration scripts dir resolves correctly regardless of CWD.
    cfg.set_main_option("script_location", str(project_root / "alembic"))

    # env.py reads DB_URL from the environment; make sure it's set.
    os.environ["DB_URL"] = db_url

    logger.info("Running Alembic migrations (upgrade head)...")
    command.upgrade(cfg, "head")
    logger.info("Alembic migrations complete.")


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
    SMTP_SERVER: Optional[str] = "smtp.wiscmail.wisc.edu"
    SMTP_PORT: Optional[int] = 587


settings = AppSettings()

@asynccontextmanager
async def setup_engine(a: FastAPI):
    """Return database client instance."""

    if settings.DB_URL is None:
        settings.DB_URL = f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"  # Fix typo DB_name -> DB_NAME

    # Apply Alembic migrations before the app starts serving requests.
    # `command.upgrade` is synchronous and uses its own (sync) engine internally,
    # so we run it in a worker thread to avoid blocking the event loop.
    await asyncio.to_thread(run_migrations, settings.DB_URL)

    # assume connect_engine returns the engine instance
    engine = await connect_engine(settings.DB_URL)

    a.state.engine = engine

    try:
        yield
    finally:
        await dispose_engine(engine)

def create_app() -> FastAPI:

    # The API is served behind a path prefix (e.g. /api) that it does not know, so the
    # docs and the OpenAPI server use relative URLs to stay under whatever prefix that is.
    app = FastAPI(
        lifespan=setup_engine,
        servers=[{"url": "."}],
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui_html():
        return get_swagger_ui_html(openapi_url=f".{app.openapi_url}", title=f"{app.title} - Swagger UI")

    @app.get("/redoc", include_in_schema=False)
    async def redoc_html():
        return get_redoc_html(openapi_url=f".{app.openapi_url}", title=f"{app.title} - ReDoc")

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

    @app.exception_handler(DBAPIError)
    async def db_error_handler(request: Request, exc: DBAPIError):
        """Database errors are a 400. Messages marked user visible, such as trigger rule violations, say why, the rest stay generic."""
        logger.error(f"Database error: {str(exc)}")
        detail = user_visible_db_message(exc) or "Database error occurred, likely due to violation of constraints."
        return JSONResponse({"detail": detail}, status_code=400)

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        return JSONResponse({"detail": f"Data validation error: {str(exc)}"}, status_code=500)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logger.error("Unexpected error", exc_info=exc)
        return JSONResponse({"detail": f"An unexpected error occurred: {str(exc)}"}, status_code=500)

    for router in all_routers:
        app.include_router(router)

    return app

async def main():
    config = uvicorn.Config("userapp.main:create_app", host="0.0.0.0", port=1111, log_level="info", factory=True)
    server = uvicorn.Server(config)
    await server.serve()

# To run the server, use the following command in your terminal:
if __name__ == "__main__":
    asyncio.run(main())
