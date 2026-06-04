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
from pydantic_settings import BaseSettings
from starlette.requests import Request

from userapp.api.routes import all_routers
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

    for router in all_routers:
        app.include_router(router)

    return app

async def main():
    config = uvicorn.Config("userapp.main:create_app", host="0.0.0.0", port=8080, log_level="info", factory=True)
    server = uvicorn.Server(config)
    await server.serve()

# To run the server, use the following command in your terminal:
if __name__ == "__main__":
    asyncio.run(main())
