from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

import api.routes.security
from api.db import (
    connect_engine,
    dispose_engine
)

from api.routes.crud import all_routers


class AppSettings(BaseSettings):
    DB_URL: str


settings = AppSettings()


@asynccontextmanager
async def setup_engine(a: FastAPI):
    """Return database client instance."""
    await connect_engine(settings.DB_URL)
    yield
    await dispose_engine()


app = FastAPI(
    lifespan=lambda: setup_engine(),
    openapi_prefix="./",
)

origins = [
    "http://localhost:8000",
    "http://localhost:3000",
    "http://localhost:3000/",
    "http://localhost:6006"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.routes.security.router)
for router in all_routers:
    app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, headers=[("Access-Control-Expose-Headers", "X-Total-Count")])