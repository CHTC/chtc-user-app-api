from typing import Any, Generator, Callable, Optional
import asyncio
import pytest
import os
import random

from httpx import Client

from dotenv import load_dotenv
from starlette.testclient import TestClient

load_dotenv()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from userapp.main import create_app
from userapp.db import connect_engine
from userapp.core.models.tables import User, SubmitNode, Group
from userapp.api.routes.security import create_login_token
from userapp.api.tests.fake_data import project_data_f, user_data_f

VALID_CIDR_RANGE = '128.104.55.0/24'
INVALID_CIDR_RANGE = '127.0.0.0/24'
WHITE_IP = VALID_CIDR_RANGE.split('/')[0]
BLACK_IP = INVALID_CIDR_RANGE.split('/')[0]


def _seed_db_url() -> str:
    url = os.environ.get("DB_URL")
    if url:
        return url
    return (
        f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT', '5432')}/{os.environ['DB_NAME']}"
    )


async def _seed_baseline() -> None:
    """Seed data needed by certain tests - needed for testing on new empty DB"""
    engine = await connect_engine(_seed_db_url())
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        async with s.begin():
            # Submit node referenced by user_data_f (submit_node_id=1).
            if not await s.get(SubmitNode, 1):
                s.add(SubmitNode(id=1, name="seed-node"))
            # Admin matching TEST_ADMIN_ID; unix_uid set so tests reading an
            # existing user's uid have a non-null value.
            if not await s.get(User, 4):
                s.add(User(id=4, name="Seed Admin", is_admin=True, active=True, unix_uid=50000))
            # Two groups so tests that read an existing group or reference group_id=1 have
            # data present.
            if not await s.get(Group, 1):
                s.add(Group(id=1, name="seed-group-1", unix_gid=55500))
            if not await s.get(Group, 2):
                s.add(Group(id=2, name="seed-group-2", unix_gid=55501))
            await s.flush()
            # Explicit ids do NOT advance the SERIAL sequences; bump each past
            # MAX(id) so app-created rows don't collide with the seeded ids.
            for table in ("submit_nodes", "users", "groups"):
                await s.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
                ))
    await engine.dispose()


def db_rows(sql: str, **params) -> list[dict]:
    """Read-only raw SQL against the test database, for what the API does not expose"""

    async def run():
        engine = await connect_engine(_seed_db_url())
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(sql), params)
                return [dict(row._mapping) for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(run())


_audit_mark = 0


@pytest.fixture(autouse=True)
def _remember_audit_position():
    """The seed fixture resets id sequences, so ids (users, projects) come back in later runs
    against the same database. Entries from earlier runs must not be mistaken for this test's."""

    global _audit_mark
    _audit_mark = db_rows("SELECT COALESCE(MAX(id), 0) AS m FROM audit_log")[0]["m"]
    yield


def audit_rows(where: str = "TRUE", **params) -> list[dict]:
    """Audit entries written since the current test started"""

    return db_rows(
        "SELECT id, action::text AS action, actor_id, group_id, member_user_id, member_group_id, caused_by, details "
        f"FROM audit_log WHERE id > :mark AND ({where}) ORDER BY id",
        mark=_audit_mark, **params,
    )


@pytest.fixture(scope="session", autouse=True)
def _baseline_seed():
    asyncio.run(_seed_baseline())
    yield


@pytest.fixture
def api_client() -> Generator[TestClient, Any, None]:
    with TestClient(create_app()) as api_client:
        yield api_client


@pytest.fixture
def existing_admin_user() -> dict:
    return {
        "id": int(os.environ.get("TEST_ADMIN_ID", 4))
    }


def _make_auth_client(user: dict) -> Generator[TestClient, Any, None]:
    with TestClient(create_app()) as client:
        session_id = "test-session-admin"

        login_jwt = create_login_token(
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
        client = TestClient(create_app(), client=(ip, 443))
        client.headers["Authorization"] = f"Bearer {token['token']}"
        return client

    return _make_client

@pytest.fixture
def group_factory(existing_admin_client: Client) -> Callable:
    """Fixture to create groups on demand. Extra keyword arguments go into the POST body
    (unix_gid, description, owner_group_id, administration, ...)."""

    def _create_group(**fields) -> dict:
        group_response = existing_admin_client.post(
            "/groups",
            json={"name": f"Test_Group_{random.randint(1, 10000000)}", **fields}
        )
        assert group_response.status_code == 201, f"Creating a group should return a 201 status code, instead got {group_response.text}"
        return group_response.json()

    return _create_group


@pytest.fixture
def group(existing_admin_client: Client, group_factory: Callable) -> dict:

    group = group_factory()
    yield group
    existing_admin_client.delete(f"/groups/{group['id']}")


@pytest.fixture
def group_member(existing_admin_client: Client) -> Callable:
    """Fixture to add a user or a group to a group, as staff. Returns the membership row.

        group_member(group['id'], user_id=user['id'])
        group_member(group['id'], member_group_id=other['id'])
    """

    def _add_member(group_id: int, user_id: Optional[int] = None, member_group_id: Optional[int] = None, **fields) -> dict:
        body = {"user_id": user_id} if user_id is not None else {"group_id": member_group_id}
        response = existing_admin_client.post(f"/groups/{group_id}/members", json={**body, **fields})
        assert response.status_code == 201, f"Adding a member to a group should return a 201 status code, instead got {response.text}"
        return response.json()

    return _add_member


@pytest.fixture
def project_factory(existing_admin_client: Client) -> Callable[[str], TestClient]:
    """Fixture to create projects on demand in tests."""

    def _create_project() -> dict:

        admin_user_response = existing_admin_client.get("/me").json()
        project_response = existing_admin_client.post(
            "/projects",
            json=project_data_f(staff1=admin_user_response['id'])
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

    def _create_user(index: int, project_id: int, submit_node_ids: Optional[list] = None) -> dict:
        user_payload = user_data_f(index, project_id, submit_node_ids=submit_node_ids)
        response = existing_admin_client.post(
            "/users",
            json=user_payload
        )
        assert response.status_code == 201, f"Creating a user should return a 201 status code instead of {response.text}"

        return response.json()

    return _create_user


@pytest.fixture
def user(existing_admin_client: Client, project_factory: Callable, group_factory, user_factory: Callable):
    """Fixture to create and yield a test user, then clean up after the test."""

    project = project_factory()
    group = group_factory()

    # Tie a submit node to the group - the user is granted the group (and thus the
    # submit node) below purely via submit node assignment, not a direct group add.
    submit_node_response = existing_admin_client.post(
        "/submit_nodes",
        json={"name": f"test-submit-{random.randint(0, 10**6)}", "group_id": group['id']},
    )
    assert submit_node_response.status_code == 201
    submit_node = submit_node_response.json()

    user = user_factory(0, project_id=project['id'], submit_node_ids=[submit_node['id']])

    user = existing_admin_client.get(f"/users/{user['id']}").json()

    yield user

    existing_admin_client.delete(f"/users/{user['id']}")
    existing_admin_client.delete(f"/submit_nodes/{submit_node['id']}")
    existing_admin_client.delete(f"/groups/{group['id']}")


@pytest.fixture
def plain_user_factory(existing_admin_client: Client):
    """Creates users that belong to no project or group, and deletes them after the test"""

    created = []

    def _create_user(index: int = 0, **fields) -> dict:
        response = existing_admin_client.post("/users", json={**user_data_f(index), **fields})
        assert response.status_code == 201, f"Creating a user should return a 201 status code instead of {response.text}"
        created.append(response.json())
        return created[-1]

    yield _create_user

    for user in created:
        existing_admin_client.delete(f"/users/{user['id']}")


@pytest.fixture
def client_as():
    """A client that is logged in as the given (non-staff) user"""

    generators = []

    def _make(user: dict):
        generator = _make_auth_client({"id": user["id"], "is_admin": False})
        client = next(generator)
        generators.append(generator)
        return client

    yield _make

    for generator in generators:
        generator.close()


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

        return response.json()

    return _create_admin_user


@pytest.fixture
def admin_user(existing_admin_client: Client, project_factory: Callable, admin_user_factory: Callable):
    """Fixture to create and yield an admin user, then clean up after the test."""

    project = project_factory()
    admin_user = admin_user_factory(0, project_id=project['id'])
    yield admin_user
    existing_admin_client.delete(f"/users/{admin_user['id']}")


@pytest.fixture
def token(admin_client: Client) -> str:
    """Fixture to create and yield an authentication token for a user."""

    response = admin_client.post(
        "/tokens",
        json={
            "description": "Test Token"
        }
    )
    assert response.status_code == 201, f"Creating a token should return a 201 status code instead of {response.text}"
    token = response.json()

    # Add some general access to the test token
    add_permissions_response = admin_client.post(f"/tokens/{token['id']}/permissions", json={
        "route": "/users",
        "method": "GET"
    })
    assert add_permissions_response.status_code == 201, f"Adding permissions to the token should return a 201 status code instead of {add_permissions_response.text}"
    add_permissions_response = admin_client.post(f"/tokens/{token['id']}/permissions", json={
        "route": "/tokens/{token_id}",
        "method": "GET"
    })
    assert add_permissions_response.status_code == 201, f"Adding permissions to the token should return a 201 status code instead of {add_permissions_response.text}"

    yield token
    admin_client.delete(f"/tokens/{token['id']}")
