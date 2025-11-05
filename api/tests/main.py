from typing import Any, Generator, Callable
import pytest
import os
import base64

from httpx import Client
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import async_sessionmaker

# Have to run before the imports that use the db env variables
from dotenv import load_dotenv
from starlette.testclient import TestClient

load_dotenv()

from api.app import app
from api.db import connect_engine, dispose_engine, get_engine
from api.tests.fake_data import project_data_f, user_data_f

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


@pytest.fixture
def project_factory(client: Client):
    """Fixture to create projects on demand in tests."""

    def _create_project() -> dict:
        project_response = client.post(
            "/projects",
            json=project_data_f()
        )
        assert project_response.status_code == 201, f"Creating a project should return a 201 status code, instead got {project_response.text}"
        return project_response.json()

    return _create_project


@pytest.fixture
def project(client: Client, project_factory: Callable) -> dict:

    project = project_factory()
    yield project
    client.delete(f"/projects/{project['id']}")


@pytest.fixture
def filled_out_project(client: Client, project: dict) -> dict:
    """Fill out project attributes with fake data"""

    project['users'] = []
    for i in range(2):
        user = user_data_f(i, primary_project_id=project['id'])
        user_response = client.post(
            "/users",
            json=user
        )
        assert user_response.status_code == 201, f"Creating a user should return a 201 instead of {user_response.text}"
        project['users'].append(user_response.json())

    yield project


@pytest.fixture
def user_factory(client: Client):
    """Fixture to create users on demand in tests."""

    def _create_user(index: int, project_id: int) -> dict:
        user_payload = user_data_f(index, project_id)
        response = client.post(
            "/users",
            json=user_payload
        )
        assert response.status_code == 201, f"Creating a user should return a 201 status code instead of {response.text}"
        return response.json()

    return _create_user

@pytest.fixture
def user(client: Client, project_factory: Callable, user_factory: Callable) -> dict:
    """Fixture to create and yield a test user, then clean up after the test."""

    project = project_factory()
    user = user_factory(0, project_id=project['id'])
    yield user
    client.delete(f"/users/{user['id']}")