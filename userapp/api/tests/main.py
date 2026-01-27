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
def admin_user() -> dict:
    return {
        "username": os.environ.get("TEST_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "password"),
        "id": int(os.environ.get("TEST_ADMIN_ID", 0))
    }


@pytest.fixture
def basic_auth_client(admin_user) -> Generator[TestClient, Any, None]:
    """Yields a TestClient authenticated as admin_user via SSO-style cookies.

    The app now relies on SSO/OIDC and expects a JWT-bearing `login_token`
    cookie (with a leading "Bearer ") and a separate `csrf_token` cookie
    tied to the same `session_id`. This fixture constructs those tokens
    directly, so tests don't depend on the interactive login flow.
    """

    with TestClient(app) as client:
        # Create a synthetic session id for this test client
        session_id = "test-session-admin"

        # Build the JWT used by get_user_from_cookie / is_admin via login_token
        login_jwt = create_login_token(
            username=admin_user["username"],
            user_id=admin_user['id'],  # user id isn't strictly needed for admin checks in tests
            is_admin=True,
            session_id=session_id,
        )

        # CSRF token is a separate JWT that embeds the same session_id
        csrf_jwt = create_login_token(session_id=session_id, random_value="test")

        # The app expects the cookie value to start with "Bearer "
        client.cookies.set("login_token", f"Bearer {login_jwt}")
        client.cookies.set("csrf_token", csrf_jwt)

        # For convenience, automatically send the CSRF token header on
        # state-changing requests in tests that use this fixture.
        client.headers["X-CSRF-Token"] = csrf_jwt

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

        return {
            **response.json(),
            "password": user_payload["password"]
        }

    return _create_user

@pytest.fixture
def user(client: Client, project_factory: Callable, user_factory: Callable) -> dict:
    """Fixture to create and yield a test user, then clean up after the test."""

    project = project_factory()
    user = user_factory(0, project_id=project['id'])
    yield user
    client.delete(f"/users/{user['id']}")


@pytest.fixture
def token(client: Client) -> str:
    """Fixture to create and yield an authentication token for a user."""

    response = client.post(
        "/tokens",
        json={
            "description": "Test Token"
        }
    )
    assert response.status_code == 201, f"Creating a token should return a 201 status code instead of {response.text}"
    data = response.json()
    yield data["token"]
    client.delete(f"/tokens/{data['id']}")


@pytest.fixture
def user_auth_client(user) -> Generator[TestClient, Any, None]:
    """Yields a TestClient that logs in the user, uses session cookies, and automatically adds CSRF token for state-changing requests."""

    with TestClient(app) as client:
        # Create a synthetic session id for this test client
        session_id = "test-session-admin"

        # Build the JWT used by get_user_from_cookie / is_admin via login_token
        login_jwt = create_login_token(
            username=user["username"],
            user_id=user['id'],
            is_admin=user['is_admin'],
            session_id=session_id,
        )

        # CSRF token is a separate JWT that embeds the same session_id
        csrf_jwt = create_login_token(session_id=session_id, random_value="test")

        # The app expects the cookie value to start with "Bearer "
        client.cookies.set("login_token", f"Bearer {login_jwt}")
        client.cookies.set("csrf_token", csrf_jwt)

        # For convenience, automatically send the CSRF token header on
        # state-changing requests in tests that use this fixture.
        client.headers["X-CSRF-Token"] = csrf_jwt

        yield client


@pytest.fixture
def token_auth_client(token: str) -> Callable[[str], TestClient]:
    """
    Returns a factory that creates a TestClient using token auth
    from a specified client IP.

    Usage in tests:
        def test_something(token_auth_client):
            with token_auth_client("128.104.55.10") as client:
                ...
    """

    def _make_client(ip: str = WHITE_IP) -> TestClient:
        # You can also make the port configurable if you need.
        client = TestClient(app, client=(ip, 443))
        client.headers["Authorization"] = f"Bearer {token}"
        return client

    return _make_client
