from typing import Any, Generator, Callable
import pytest
import os

from httpx import Client

from dotenv import load_dotenv
from starlette.testclient import TestClient

load_dotenv()

from userapp.main import app
from userapp.api.routes.security import create_login_token
from userapp.api.tests.fake_data import project_data_f, user_data_f

os.environ["DB_URL"] = os.environ.get("TEST_DB_URL", "sqllite+aiosqlite:///./test.db")

VALID_CIDR_RANGE = '128.104.55.0/24'
INVALID_CIDR_RANGE = '127.0.0.0/24'
WHITE_IP = VALID_CIDR_RANGE.split('/')[0]
BLACK_IP = INVALID_CIDR_RANGE.split('/')[0]


@pytest.fixture
def api_client() -> Generator[TestClient, Any, None]:
    with TestClient(app) as api_client:
        yield api_client


@pytest.fixture
def existing_admin_user() -> dict:
    return {
        "username": os.environ.get("TEST_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "password"),
        "id": int(os.environ.get("TEST_ADMIN_ID", 0))
    }


def _make_auth_client(user: dict) -> Generator[TestClient, Any, None]:
    with TestClient(app) as client:
        session_id = "test-session-admin"

        login_jwt = create_login_token(
            username=user["username"],
            user_id=user["id"],
            is_admin=user.get("is_admin", False),
            session_id=session_id,
        )

        csrf_jwt = create_login_token(session_id=session_id, random_value="test")

        client.cookies.set("login_token", f"Bearer {login_jwt}")
        client.cookies.set("csrf_token", csrf_jwt)
        client.headers["X-CSRF-Token"] = csrf_jwt

        yield client


@pytest.fixture
def existing_admin_client(existing_admin_user) -> Generator[TestClient, Any, None]:
    yield from _make_auth_client({
        **existing_admin_user,
        "is_admin": True,
    })


@pytest.fixture
def admin_client(admin_user) -> Generator[TestClient, Any, None]:
    yield from _make_auth_client(admin_user)
    

@pytest.fixture
def nonadmin_client(user) -> Generator[TestClient, Any, None]:
    yield from _make_auth_client(user)



@pytest.fixture
def token_client(token: dict) -> Callable[[str], TestClient]:
    """
    Returns a factory that creates a TestClient using token auth
    from a specified client IP.

    Usage in tests:
        def test_something(token_client):
            with token_client("128.104.55.10") as client:
                ...
    """

    def _make_client(ip: str = WHITE_IP) -> TestClient:
        # You can also make the port configurable if you need.
        client = TestClient(app, client=(ip, 443))
        client.headers["Authorization"] = f"Bearer {token['token']}"
        return client

    return _make_client


@pytest.fixture
def project_factory(existing_admin_client: Client):
    """Fixture to create projects on demand in tests."""

    def _create_project() -> dict:
        project_response = existing_admin_client.post(
            "/projects",
            json=project_data_f()
        )
        assert project_response.status_code == 201, f"Creating a project should return a 201 status code, instead got {project_response.text}"
        return project_response.json()

    return _create_project


@pytest.fixture
def project(existing_admin_client: Client, project_factory: Callable) -> dict:

    project = project_factory()
    yield project
    existing_admin_client.delete(f"/projects/{project['id']}")


@pytest.fixture
def filled_out_project(existing_admin_client: Client, project: dict) -> dict:
    """Fill out project attributes with fake data"""

    project['users'] = []
    for i in range(2):
        user = user_data_f(i, primary_project_id=project['id'])
        user_response = existing_admin_client.post(
            "/users",
            json=user
        )
        assert user_response.status_code == 201, f"Creating a user should return a 201 instead of {user_response.text}"
        project['users'].append(user_response.json())

    yield project


@pytest.fixture
def user_factory(existing_admin_client: Client):
    """Fixture to create users on demand in tests."""

    def _create_user(index: int, project_id: int) -> dict:
        user_payload = user_data_f(index, project_id)
        response = existing_admin_client.post(
            "/users",
            json=user_payload
        )
        assert response.status_code == 201, f"Creating a user should return a 201 status code instead of {response.text}"

        return {
            **response.json(),
            "password": user_payload["password"]
        }

    return _create_user


@pytest.fixture
def user(existing_admin_client: Client, project_factory: Callable, user_factory: Callable):
    """Fixture to create and yield a test user, then clean up after the test."""

    project = project_factory()
    user = user_factory(0, project_id=project['id'])
    yield user
    existing_admin_client.delete(f"/users/{user['id']}")


@pytest.fixture
def admin_user_factory(existing_admin_client: Client):
    """Fixture to create admin users on demand in tests."""

    def _create_admin_user(index: int, project_id: int) -> dict:
        user_payload = user_data_f(index, primary_project_id=project_id, is_admin=True)
        response = existing_admin_client.post(
            "/users",
            json=user_payload
        )
        assert response.status_code == 201, f"Creating a user should return a 201 status code instead of {response.text}"

        return {
            **response.json(),
            "password": user_payload["password"]
        }

    return _create_admin_user


@pytest.fixture
def admin_user(existing_admin_client: Client, project_factory: Callable, admin_user_factory: Callable):
    """Fixture to create and yield an admin user, then clean up after the test."""

    project = project_factory()
    admin_user = admin_user_factory(0, project_id=project['id'])
    yield admin_user
    existing_admin_client.delete(f"/users/{admin_user['id']}")


@pytest.fixture
def token(existing_admin_client: Client) -> str:
    """Fixture to create and yield an authentication token for a user."""

    response = existing_admin_client.post(
        "/tokens",
        json={
            "description": "Test Token"
        }
    )
    assert response.status_code == 201, f"Creating a token should return a 201 status code instead of {response.text}"
    token = response.json()

    # Add some general access to the test token
    add_permissions_response = existing_admin_client.post(f"/tokens/{token['id']}/permissions", json={
        "route": "/users",
        "method": "GET"
    })
    assert add_permissions_response.status_code == 201, f"Adding permissions to the token should return a 201 status code instead of {add_permissions_response.text}"
    add_permissions_response = existing_admin_client.post(f"/tokens/{token['id']}/permissions", json={
        "route": "/tokens/{token_id}",
        "method": "GET"
    })
    assert add_permissions_response.status_code == 201, f"Adding permissions to the token should return a 201 status code instead of {add_permissions_response.text}"

    yield token
    existing_admin_client.delete(f"/tokens/{token['id']}")
