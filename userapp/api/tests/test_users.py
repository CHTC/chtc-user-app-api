import asyncio
import random

from httpx import Client
import pytest
from pydantic import ValidationError

from sqlalchemy import text

from userapp.api.tests.conftest import _seed_db_url
from userapp.api.tests.fake_data import user_data_f
from userapp.db import connect_engine
from userapp.core.models.enum import RoleEnum
from userapp.core.schemas.general import JoinedProjectView
from userapp.core.schemas.users import UserGet, UserPost


def create_submit_node(admin_client: Client) -> dict:
    """Creates a submit node along with the group it depends on for assignment."""

    group_response = admin_client.post(
        "/groups",
        json={"name": f"Test_Group_{random.randint(1, 10000000)}"},
    )
    assert group_response.status_code == 201, (
        f"POST /groups should return 201, got {group_response.status_code}: {group_response.text}"
    )
    group = group_response.json()

    response = admin_client.post(
        "/submit_nodes",
        json={"name": f"test-submit-{random.randint(0, 10**6)}", "group_id": group["id"]},
    )
    assert response.status_code == 201, (
        f"POST /submit_nodes should return 201, got {response.status_code}: {response.text}"
    )
    return response.json()


class TestUsers:

    def test_list_users(self, admin_client: Client, admin_user: dict, user_factory, project_factory):
        """Test listing users"""

        project = project_factory()

        # Create some users
        num_users = 5
        for _ in range(num_users):
            user_factory(_, project['id'])

        response = admin_client.get("/users?is_pi=eq.true")

        assert response.status_code == 200, f"Listing users should return a 200 status code, instead got {response.text}"
        users_list = response.json()
        assert len(users_list) >= num_users, f"Users list should contain at least {num_users} users, found {len(users_list)}"

    def test_create_user(self, admin_client: Client, project: dict):
        """Test creating a new user"""
        submit_node = create_submit_node(admin_client)
        user_payload = user_data_f(1, project['id'], submit_node_ids=[submit_node['id']])

        response = admin_client.post(
            "/users",
            json=user_payload
        )

        assert response.status_code == 201, f"Creating a user should return a 201 status code, instead got {response.text}"
        created_user = response.json()
        for key in created_user:
            if key not in ["id", "is_pi", "submit_nodes", "date", "created_at", "updated_at", "notes", "projects", "groups", "auth_netid", "auth_username", "username", "user_forms"]:
                assert created_user[key] == user_payload[key], f"User {key} should match the payload"

        assert set(map(lambda x: x['submit_node_id'], user_payload['submit_nodes'])) == set(map(lambda x: x['id'], created_user['submit_nodes']))

    def test_get_user(self, admin_client: Client, user_factory, project_factory):
        """Test getting a user by ID"""

        project = project_factory()
        user = user_factory(5, project['id'])
        user = user_factory(5, project['id'])

        user_response = admin_client.get(f"/users/{user['id']}")

        assert user_response.status_code == 200, f"Getting a user should return a 200 status code, instead got {user_response.text}"
        fetched_user = user_response.json()
        assert fetched_user['id'] == user['id'], "Fetched user ID should match the created user ID"
        assert fetched_user['name'] == user['name'], "Fetched user name should match the created user name"
        assert fetched_user['username'] == user['username'], "Fetched user username should match the created user username"

    def test_update_user_simple(self, admin_client: Client, user_factory, project_factory):
        """Test updating an existing user"""

        project = project_factory()
        user = user_factory(10, project['id'])
        submit_node = create_submit_node(admin_client)

        new_name = f"Updated Name {random.randint(1, 100)}"
        update_payload = {
            "name": new_name,
            "phone1": "555-9999",
            "phone2": "",
            "position": "POSTDOC",
            "submit_nodes": [
                {
                    "submit_node_id": submit_node['id']
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        assert updated_data['name'] == new_name, "User name should be updated"
        assert updated_data['phone1'] == update_payload['phone1'], "Phone 1 should be updated"
        assert updated_data['phone2'] == None, "Phone 2 should be updated"
        assert updated_data['position'] == update_payload['position'], "Position should be updated"
        assert updated_data['submit_nodes'][0]['id'] == submit_node['id'], "User submit node should be updated"

    def test_update_users_submit_nodes(self, admin_client: Client, user_factory, project_factory):
        """Test updating user's submit nodes"""

        project = project_factory()
        user = user_factory(10, project['id'])
        submit_node_1 = create_submit_node(admin_client)
        submit_node_2 = create_submit_node(admin_client)

        update_payload = {
            "submit_nodes": [
                {
                    "submit_node_id": submit_node_1['id']
                },
                {
                    "submit_node_id": submit_node_2['id']
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['id'], updated_data['submit_nodes']))
        expected_submit_node_ids = {submit_node_1['id'], submit_node_2['id']}
        assert updated_submit_node_ids == expected_submit_node_ids, "User submit nodes should be updated correctly"

    def test_update_users_submit_nodes_twice(self, admin_client: Client, user_factory, project_factory):
        """Test updating user's submit nodes"""

        project = project_factory()
        user = user_factory(10, project['id'])
        submit_node_1 = create_submit_node(admin_client)
        submit_node_2 = create_submit_node(admin_client)

        update_payload = {
            "submit_nodes": [
                {
                    "submit_node_id": submit_node_1['id']
                },
                {
                    "submit_node_id": submit_node_2['id']
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['id'], updated_data['submit_nodes']))
        expected_submit_node_ids = {submit_node_1['id'], submit_node_2['id']}
        assert updated_submit_node_ids == expected_submit_node_ids, "User submit nodes should be updated correctly"

        update_payload = {
            "submit_nodes": [
                {
                    "submit_node_id": submit_node_2['id']
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['id'], updated_data['submit_nodes']))
        expected_submit_node_ids = {submit_node_2['id']}
        assert updated_submit_node_ids == expected_submit_node_ids, "User submit nodes should be updated correctly"



    def test_nullify_email1(self, admin_client: Client, user_factory, project_factory):

        project = project_factory()
        user = user_factory(10, project['id'])

        update_payload = {
            "email1": ""
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Nullifying email1 should return a 200 status code, instead got {user_payload.text}"
        assert user_payload.json()["email1"] is None, "email1 should be null after patching with an empty string"

    def test_user_get_self(self, user, nonadmin_client):
        """Test that a user can get their own details"""

        user_payload = nonadmin_client.get(f"/users/{user['id']}")

        assert user_payload.status_code == 200, f"User getting their own details should return a 200 status code, instead got {user_payload.text}"

        fetched_user = user_payload.json()
        assert fetched_user['id'] == user['id'], "Fetched user ID should match the user's ID"
        assert fetched_user['name'] == user['name'], "Fetched user name should match the user's name"
        assert fetched_user.get('password', None) == None, "Fetched user data has no data"


    def test_user_get_other_user(self, user, nonadmin_client):
        """Test that a user cannot get another user's details"""

        user_payload = nonadmin_client.get(f"/users/{user['id'] - 1}")

        assert user_payload.status_code == 403, f"User getting another user's details should return a 403 status code, instead got {user_payload.text}"

    def test_user_modifying_self(self, user, nonadmin_client):
        """Test that a user can modify their own details"""

        new_phone = "555-1234"
        update_payload = {
            "phone1": new_phone
        }

        user_payload = nonadmin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"User updating their own details should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        assert updated_data['phone1'] == new_phone, "User phone1 should be updated"

    def test_user_modifying_restricted_fields(self, user, nonadmin_client):
        """Test that a user cannot modify restricted fields of their own details"""

        update_payload = {
            "is_admin": True,
            "name": "New Name"
        }

        user_payload = nonadmin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"User updating their own restricted details should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        assert updated_data['is_admin'] == False, "User should not be able to update is_admin field"
        assert updated_data['name'] == "New Name", "User should be able to update name field"

    def test_get_user_projects(self, admin_client: Client, user_factory, filled_out_project: dict):
        """Test getting projects for a user"""
        user = user_factory(random.randint(1000, 2000), filled_out_project['id'])

        response = admin_client.get(f"/users/{user['id']}/projects")

        assert response.status_code == 200, f"Getting user projects should return a 200 status code, instead got {response.text}"
        projects = response.json()
        assert len(projects) > 0, "User should have at least one project"
        assert any(proj['project_id'] == filled_out_project['id'] for proj in projects), "User's projects should include the filled out project"

    def test_get_user_submit_nodes(self, admin_client: Client, user_factory, filled_out_project: dict):
        """Test getting submit nodes for a user"""
        submit_node = create_submit_node(admin_client)
        user = user_factory(random.randint(2001, 3000), filled_out_project['id'], submit_node_ids=[submit_node['id']])

        response = admin_client.get(f"/users/{user['id']}/submit_nodes")

        assert response.status_code == 200, f"Getting user submit nodes should return a 200 status code, instead got {response.text}"
        submit_nodes = response.json()
        assert len(submit_nodes) > 0, "User should have at least one submit node"
        assert user['submit_nodes'][0]['id'] in map(lambda x: x['id'], submit_nodes), "User's submit nodes should include those from the filled out project"

    def test_get_user_submit_nodes_legacy_fields(self, admin_client: Client, user_factory, filled_out_project: dict):
        """The pre-group submit_node_id/submit_node_name field names are still served and filterable"""

        submit_node = create_submit_node(admin_client)
        user = user_factory(random.randint(3001, 4000), filled_out_project['id'], submit_node_ids=[submit_node['id']])

        response = admin_client.get(f"/users/{user['id']}/submit_nodes")

        assert response.status_code == 200, f"Getting user submit nodes should return a 200 status code, instead got {response.text}"
        returned = next(sn for sn in response.json() if sn['id'] == submit_node['id'])
        assert returned['submit_node_id'] == returned['id'], "submit_node_id should mirror id"
        assert returned['submit_node_name'] == returned['name'] == submit_node['name'], "submit_node_name should mirror name"

        # Filtering on the legacy column name should still resolve against the view
        filtered = admin_client.get(f"/users/{user['id']}/submit_nodes?submit_node_name=eq.{submit_node['name']}")

        assert filtered.status_code == 200, f"Filtering on submit_node_name should return a 200 status code, instead got {filtered.text}"
        assert [sn['submit_node_id'] for sn in filtered.json()] == [submit_node['id']], "Filtering on submit_node_name should return just the matching submit node"

    def test_get_user_groups_simple(self, admin_client: Client, user_factory, filled_out_project: dict):
        """Test getting groups for a user"""
        user = user_factory(random.randint(3001, 4000), filled_out_project['id'])

        response = admin_client.get(f"/users/{user['id']}/groups")

        assert response.status_code == 200, f"Getting user groups should return a 200 status code, instead got {response.text}"
        groups = response.json()
        assert len(groups) == 0, "User should belong to no groups"

    def test_get_user_groups_with_groups(self, admin_client: Client, user_factory, project_factory):
        """Test getting groups for a user who belongs to groups"""
        project = project_factory()
        user = user_factory(random.randint(4001, 5000), project['id'])

        # Manually add user to groups in the database for testing
        group_ids = [1, 2]
        for group_id in group_ids:
            r = admin_client.post(f"/groups/{group_id}/users", json={"user_id": user['id']})
            assert r.status_code == 201, f"Adding user to group {group_id} should return a 201 status code, instead got {r.text}"

        response = admin_client.get(f"/users/{user['id']}/groups")

        assert response.status_code == 200, f"Getting user groups should return a 200 status code, instead got {response.text}"
        groups = response.json()
        assert len(groups) == len(group_ids), f"User should belong to {len(group_ids)} groups"
        assert all(group['group_id'] in group_ids for group in groups), "User's groups should match the added groups"

    def test_get_user_by_netid(self, admin_client: Client, user_factory, project_factory):
        """Test getting a user by netid"""

        project = project_factory()
        user = user_factory(5001, project['id'])

        response = admin_client.get(f"/users?netid=eq.{user['netid']}")

        assert response.status_code == 200, f"Getting a user by netid should return a 200 status code, instead got {response.text}"
        users = response.json()
        assert len(users) == 1, "Should return exactly one user"
        fetched_user = users[0]
        assert fetched_user['id'] == user['id'], "Fetched user ID should match the created user ID"
        assert fetched_user['name'] == user['name'], "Fetched user name should match the created user name"

    def test_patch_user_doesnt_remove_submit_nodes(self, admin_client: Client, user, project):
        """Test that patching a user without submit nodes does not remove existing submit nodes"""

        # First, update the user with an empty submit nodes list
        update_payload = {
            "name": "Cool Name"
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user with empty submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        assert len(updated_data['submit_nodes']) > 0, "User's submit nodes should not be removed when patching with an empty list"


class TestSubmitNodeGroupMembership:
    """Submit node access is derived from group membership, so the group endpoints and the
    submit_nodes field on /users are two views of the same rows - these cover both directions."""

    def _submit_node_ids(self, admin_client: Client, user_id: int) -> set:
        response = admin_client.get(f"/users/{user_id}/submit_nodes")
        assert response.status_code == 200, f"Getting user submit nodes should return a 200 status code, instead got {response.text}"
        return {submit_node['id'] for submit_node in response.json()}

    def _group_ids(self, admin_client: Client, user_id: int) -> set:
        response = admin_client.get(f"/users/{user_id}/groups")
        assert response.status_code == 200, f"Getting user groups should return a 200 status code, instead got {response.text}"
        return {group['group_id'] for group in response.json()}

    def test_group_membership_grants_submit_node(self, admin_client: Client, user_factory, project: dict):
        """Adding a user to a submit node's group grants access to that node"""

        submit_node = create_submit_node(admin_client)
        user = user_factory(random.randint(4001, 5000), project['id'])

        assert submit_node['id'] not in self._submit_node_ids(admin_client, user['id']), "User should start without access to the submit node"

        response = admin_client.post(f"/groups/{submit_node['group_id']}/users", json={"user_id": user['id']})

        assert response.status_code == 201, f"Adding a user to a group should return a 201 status code, instead got {response.text}"
        assert submit_node['id'] in self._submit_node_ids(admin_client, user['id']), "Group membership alone should grant access to the submit node"

    def test_removing_group_membership_revokes_submit_node(self, admin_client: Client, user_factory, project: dict):
        """Removing a user from a submit node's group revokes access to that node"""

        submit_node = create_submit_node(admin_client)
        user = user_factory(random.randint(5001, 6000), project['id'], submit_node_ids=[submit_node['id']])

        response = admin_client.delete(f"/groups/{submit_node['group_id']}/users/{user['id']}")

        assert response.status_code == 204, f"Removing a user from a group should return a 204 status code, instead got {response.text}"
        assert submit_node['id'] not in self._submit_node_ids(admin_client, user['id']), "Losing the group membership should revoke access to the submit node"

    def test_assigning_submit_node_adds_group_membership(self, admin_client: Client, user_factory, project: dict):
        """Assigning a submit node is stored as membership in that node's group"""

        submit_node = create_submit_node(admin_client)
        user = user_factory(random.randint(6001, 7000), project['id'], submit_node_ids=[submit_node['id']])

        assert submit_node['group_id'] in self._group_ids(admin_client, user['id']), "Assigning a submit node should add the user to its group"

    def test_patching_submit_nodes_leaves_unrelated_groups(self, admin_client: Client, user_factory, project: dict, group: dict):
        """Revoking submit nodes only removes groups that a submit node depends on"""

        submit_node = create_submit_node(admin_client)
        user = user_factory(random.randint(7001, 8000), project['id'], submit_node_ids=[submit_node['id']])

        # A group with no submit node attached to it - membership here is unrelated to node access
        group_addition = admin_client.post(f"/groups/{group['id']}/users", json={"user_id": user['id']})
        assert group_addition.status_code == 201, f"Adding a user to a group should return a 201 status code, instead got {group_addition.text}"

        response = admin_client.patch(f"/users/{user['id']}", json={"submit_nodes": []})

        assert response.status_code == 200, f"Clearing a user's submit nodes should return a 200 status code, instead got {response.text}"

        group_ids = self._group_ids(admin_client, user['id'])
        assert submit_node['group_id'] not in group_ids, "The submit node's group should be removed when its node is revoked"
        assert group['id'] in group_ids, "A group with no submit node attached should be left alone"

    def test_submit_nodes_sharing_a_group_are_granted_together(self, admin_client: Client, user_factory, project: dict, group: dict):
        """Two submit nodes pointed at one group cannot be granted independently"""

        shared_nodes = []
        for _ in range(2):
            response = admin_client.post(
                "/submit_nodes",
                json={"name": f"test-submit-{random.randint(0, 10**6)}", "group_id": group['id']},
            )
            assert response.status_code == 201, f"POST /submit_nodes should return 201, got {response.status_code}: {response.text}"
            shared_nodes.append(response.json())

        user = user_factory(random.randint(8001, 9000), project['id'], submit_node_ids=[shared_nodes[0]['id']])

        submit_node_ids = self._submit_node_ids(admin_client, user['id'])
        assert {node['id'] for node in shared_nodes} <= submit_node_ids, "Granting one node should grant every node sharing its group"

    def test_patching_unknown_submit_node_is_rejected(self, admin_client: Client, user_factory, project: dict):
        """A submit_node_id that doesn't exist is rejected rather than silently ignored"""

        user = user_factory(random.randint(9001, 10000), project['id'])

        response = admin_client.patch(f"/users/{user['id']}", json={"submit_nodes": [{"submit_node_id": 10 ** 8}]})

        assert response.status_code == 400, f"Patching an unknown submit node should return a 400 status code, instead got {response.text}"

    def test_patching_submit_node_without_a_group_is_rejected(self, admin_client: Client, user_factory, project: dict):
        """A submit node with no group has nowhere to record membership, so it cannot be assigned"""

        response = admin_client.post("/submit_nodes", json={"name": f"test-submit-{random.randint(0, 10**6)}"})
        assert response.status_code == 201, f"POST /submit_nodes should return 201, got {response.status_code}: {response.text}"
        submit_node = response.json()
        assert submit_node['group_id'] is None, "Submit node should have been created without a group"

        user = user_factory(random.randint(10001, 11000), project['id'])
        response = admin_client.patch(f"/users/{user['id']}", json={"submit_nodes": [{"submit_node_id": submit_node['id']}]})

        assert response.status_code == 400, f"Patching a submit node with no group should return a 400 status code, instead got {response.text}"


def schema_user_data(**overrides):
    data = {
        "id": 1,
        "username": "testnetid",
        "name": "Test User",
        "email1": "test@example.com",
        "active": True,
        "netid": "testnetid",
    }
    data.update(overrides)
    return data


def schema_project_view_data(**overrides):
    data = {
        "id": 1,
        "project_id": 10,
        "project_name": "Test Project",
        "username": "testnetid",
        "name": "Test User",
        "email1": "test@example.com",
        "active": True,
        "netid": "testnetid",
        "role": RoleEnum.PI,
    }
    data.update(overrides)
    return data


def expected_auth_netid(user_data: dict) -> bool | None:
    return user_data["active"] and user_data["netid"] == user_data["username"]


def expected_auth_username(user_data: dict) -> bool:
    return user_data["netid"] != user_data["username"]


class TestUserAuthBehavior:

    def test_userpost_requires_netid_when_active(self):
        with pytest.raises(ValidationError) as exc_info:
            UserPost(**schema_user_data(username="testnetid", active=True, netid=None))

        assert "netid must be provided" in str(exc_info.value).lower()

    def test_patch_user_can_set_distinct_username(self, admin_client: Client, project_factory):
        project = project_factory()
        user_payload = user_data_f(102, project["id"])

        create_response = admin_client.post("/users", json=user_payload)
        assert create_response.status_code == 201, create_response.text
        created_user = create_response.json()

        update_payload = {
            "username": f"unixuser{random.randint(100000, 999999)}",
        }
        patch_response = admin_client.patch(f"/users/{created_user['id']}", json=update_payload)
        assert patch_response.status_code == 200, patch_response.text
        updated_user = patch_response.json()

        assert updated_user["username"] == update_payload["username"]
        assert updated_user["netid"] == created_user["netid"]
        assert updated_user["auth_netid"] is False
        assert updated_user["auth_username"] is True

    def test_user_endpoints_include_auth_compatibility_fields(self, admin_client: Client, project_factory):
        project = project_factory()
        user_payload = user_data_f(100, project["id"], username="unixuser100")
        user_payload["netid"] = f"netid{random.randint(100000, 999999)}"
        user_payload["active"] = True

        create_response = admin_client.post("/users", json=user_payload)
        assert create_response.status_code == 201, create_response.text
        created_user = create_response.json()

        get_response = admin_client.get(f"/users/{created_user['id']}")
        assert get_response.status_code == 200, get_response.text
        fetched_user = get_response.json()

        projects_response = admin_client.get(f"/users/{created_user['id']}/projects")
        assert projects_response.status_code == 200, projects_response.text
        project_view = projects_response.json()[0]

        assert fetched_user["auth_netid"] == expected_auth_netid(fetched_user)
        assert fetched_user["auth_username"] == expected_auth_username(fetched_user)
        assert project_view["auth_netid"] == expected_auth_netid(project_view)
        assert project_view["auth_username"] == (project_view["active"] and expected_auth_username(project_view))


def _run_sql(statement: str, params: dict, bypass_triggers: bool = False) -> None:
    """Run one statement against the test database, optionally skipping triggers (needs a superuser)"""

    async def run():
        engine = await connect_engine(_seed_db_url())
        async with engine.begin() as connection:
            if bypass_triggers:
                await connection.execute(text("SET session_replication_role = replica"))
            await connection.execute(text(statement), params)
        await engine.dispose()

    asyncio.run(run())


class TestActivateRequiresPrimaryProject:
    """An inactive user cannot be made active unless they have a primary project."""

    @pytest.fixture
    def inactive_user_without_primary(self, existing_admin_client: Client, project_factory):
        project = project_factory()
        created = existing_admin_client.post("/users", json=user_data_f(200, project["id"]))
        assert created.status_code == 201, created.text
        user = created.json()

        assert existing_admin_client.patch(f"/users/{user['id']}", json={"active": False}).status_code == 200
        demote = existing_admin_client.patch(
            f"/users/{user['id']}/projects/{project['id']}", json={"is_primary": False}
        )
        assert demote.status_code == 200, demote.text

        yield user, project

        existing_admin_client.delete(f"/users/{user['id']}")
        existing_admin_client.delete(f"/projects/{project['id']}")

    def test_activate_without_primary_project_fails(self, existing_admin_client: Client, inactive_user_without_primary):
        user, _ = inactive_user_without_primary

        response = existing_admin_client.patch(f"/users/{user['id']}", json={"active": True})
        assert response.status_code == 400, response.text
        assert "primary project" in response.json()["detail"].lower()
        assert existing_admin_client.get(f"/users/{user['id']}").json()["active"] is False

    def test_activate_with_primary_project_succeeds(self, existing_admin_client: Client, inactive_user_without_primary):
        user, project = inactive_user_without_primary

        existing_admin_client.patch(f"/users/{user['id']}/projects/{project['id']}", json={"is_primary": True})
        response = existing_admin_client.patch(f"/users/{user['id']}", json={"active": True})
        assert response.status_code == 200, response.text
        assert response.json()["active"] is True

    def test_edit_inactive_user_without_primary_project_still_allowed(
        self, existing_admin_client: Client, inactive_user_without_primary
    ):
        """Only the inactive -> active change is checked."""
        user, _ = inactive_user_without_primary

        response = existing_admin_client.patch(f"/users/{user['id']}", json={"name": "Renamed User"})
        assert response.status_code == 200, response.text

    def test_existing_active_user_without_primary_can_be_edited(self, existing_admin_client: Client, project_factory):
        """Existing active users with no primary project are not blocked when active is unchanged."""
        project = project_factory()
        user = existing_admin_client.post("/users", json=user_data_f(201, project["id"])).json()
        try:
            # The API no longer lets this happen, so write the legacy state straight to the database
            _run_sql(
                "UPDATE user_projects SET is_primary = false WHERE user_id = :user_id",
                {"user_id": user["id"]},
                bypass_triggers=True,
            )

            response = existing_admin_client.patch(f"/users/{user['id']}", json={"active": True, "name": "Renamed User"})
            assert response.status_code == 200, response.text
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")
            existing_admin_client.delete(f"/projects/{project['id']}")


class TestActiveUserKeepsPrimaryProject:
    """An active user's primary membership can't be removed, except by deleting the project or the user."""

    def test_delete_primary_membership_of_active_user_rejected(self, existing_admin_client: Client, user):
        project_id = user["projects"][0]["project_id"]

        response = existing_admin_client.delete(f"/projects/{project_id}/users/{user['id']}")
        assert response.status_code == 400, response.text
        assert "primary project" in response.json()["detail"].lower()

        memberships = existing_admin_client.get(f"/users/{user['id']}/projects").json()
        assert project_id in [m["project_id"] for m in memberships]

    def test_delete_non_primary_membership_of_active_user_allowed(self, existing_admin_client: Client, user, project_factory):
        other = project_factory()
        try:
            added = existing_admin_client.post(
                f"/projects/{other['id']}/users",
                json={"user_id": user["id"], "is_primary": False, "role": RoleEnum.MEMBER.value},
            )
            assert added.status_code == 201, added.text

            response = existing_admin_client.delete(f"/projects/{other['id']}/users/{user['id']}")
            assert response.status_code == 204, response.text
        finally:
            existing_admin_client.delete(f"/projects/{other['id']}")

    def test_delete_primary_membership_of_inactive_user_allowed(self, existing_admin_client: Client, user):
        project_id = user["projects"][0]["project_id"]
        assert existing_admin_client.patch(f"/users/{user['id']}", json={"active": False}).status_code == 200

        response = existing_admin_client.delete(f"/projects/{project_id}/users/{user['id']}")
        assert response.status_code == 204, response.text

    def test_deleting_project_with_active_users_primary_membership_allowed(
        self, existing_admin_client: Client, user_factory, project_factory
    ):
        project = project_factory()
        user = user_factory(300, project["id"])
        try:
            response = existing_admin_client.delete(f"/projects/{project['id']}")
            assert response.status_code == 204, response.text

            assert existing_admin_client.get(f"/users/{user['id']}/projects").json() == []
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")

    def test_switching_primary_project_allowed(self, existing_admin_client: Client, user, project_factory):
        """Making another project primary demotes the old one, which is not an unset of the only primary."""
        old_primary_id = user["projects"][0]["project_id"]
        other = project_factory()
        try:
            existing_admin_client.post(
                f"/projects/{other['id']}/users",
                json={"user_id": user["id"], "is_primary": False, "role": RoleEnum.MEMBER.value},
            )
            response = existing_admin_client.patch(f"/users/{user['id']}/projects/{other['id']}", json={"is_primary": True})
            assert response.status_code == 200, response.text

            memberships = existing_admin_client.get(f"/users/{user['id']}/projects").json()
            assert [m["project_id"] for m in memberships if m["is_primary"]] == [other["id"]]
            assert old_primary_id in [m["project_id"] for m in memberships]
        finally:
            existing_admin_client.delete(f"/projects/{other['id']}")
