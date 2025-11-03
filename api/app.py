from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic_settings import BaseSettings

import api.routes.security
import api.routes.groups
import api.routes.user
import api.routes.projects
from api.db import (
    connect_engine,
    dispose_engine
)


class AppSettings(BaseSettings):
    DB_URL: str
    SECRET_KEY: str


settings = AppSettings()


@asynccontextmanager
async def setup_engine(a: FastAPI):
    """Return database client instance."""
    await connect_engine(settings.DB_URL)
    yield
    await dispose_engine()


app = FastAPI(
    lifespan=setup_engine,
    openapi_prefix="./",
)

origins = [
    "http://localhost:8000",
    "http://localhost:3000",
    "http://localhost:3000/",
    "http://localhost:6006"
]

app.include_router(api.routes.security.router)
app.include_router(api.routes.groups.router)
app.include_router(api.routes.user.router)
app.include_router(api.routes.projects.router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, headers=[("Access-Control-Expose-Headers", "X-Total-Count")])