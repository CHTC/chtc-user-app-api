from typing import Any, Generator

import pytest
import os
import hashlib
import datetime
import random
import base64

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import NoResultFound

from fastapi.testclient import TestClient

# Have to run before the imports that use the db env variables
from dotenv import load_dotenv
from starlette.testclient import TestClient

load_dotenv()

from api.app import app
from api.db import connect_engine, dispose_engine, get_engine

os.environ["DB_URL"] = os.environ.get("TEST_DB_URL", "sqllite+aiosqlite:///./test.db")


@pytest.fixture
def api_client() -> Generator[TestClient, Any, None]:
    with TestClient(app) as api_client:
        yield api_client


@pytest.fixture
async def engine() -> AsyncEngine:
    await connect_engine()
    yield get_engine()
    await dispose_engine()


@pytest.fixture
async def session(engine: AsyncEngine):
    async_session = async_sessionmaker(engine)
    yield async_session


@pytest.fixture
def admin_user() -> dict:
    return {
        "username": os.environ.get("TEST_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "password")
    }


@pytest.fixture
def basic_auth_client(admin_user) -> Generator[TestClient, Any, None]:
    """Yields a TestClient that automatically sends Basic Auth headers."""

    class BasicAuthClient(TestClient):
        def request(self, method, url, **kwargs):
            credentials = f"{admin_user['username']}:{admin_user['password']}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers = kwargs.pop("headers", {}) or {}
            headers = dict(headers)  # ensure mutable
            headers["Authorization"] = f"Basic {encoded}"
            return super().request(method, url, headers=headers, **kwargs)

    with BasicAuthClient(app) as client:
        yield client
