import random

from httpx import Client
import pytest
from pydantic import ValidationError

from userapp.api.tests.fake_data import user_data_f
from userapp.core.models.enum import RoleEnum
from userapp.core.schemas.general import JoinedProjectView
from userapp.core.schemas.users import UserGet, UserPost

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
        user_payload = user_data_f(1, project['id'])

        response = admin_client.post(
            "/users",
            json=user_payload
        )

        assert response.status_code == 201, f"Creating a user should return a 201 status code, instead got {response.text}"
        created_user = response.json()
        for key in created_user:
            if key not in ["id", "is_pi", "submit_nodes", "date", "notes", "projects", "groups", "auth_netid", "auth_username", "username", "user_forms"]:
                assert created_user[key] == user_payload[key], f"User {key} should match the payload"

        assert set(map(lambda x: x['submit_node_id'], user_payload['submit_nodes'])) == set(map(lambda x: x['submit_node_id'], created_user['submit_nodes']))

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

        new_name = f"Updated Name {random.randint(1, 100)}"
        update_payload = {
            "name": new_name,
            "phone1": "555-9999",
            "phone2": "",
            "position": "POSTDOC",
            "submit_nodes": [
                {
                    "submit_node_id": 2 # Default is 1
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
        assert updated_data['submit_nodes'][0]['submit_node_id'] == 2, "User submit node should be updated"

    def test_update_users_submit_nodes(self, admin_client: Client, user_factory, project_factory):
        """Test updating user's submit nodes"""

        project = project_factory()
        user = user_factory(10, project['id'])

        update_payload = {
            "submit_nodes": [
                {
                    "submit_node_id": 1
                },
                {
                    "submit_node_id": 2
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['submit_node_id'], updated_data['submit_nodes']))
        expected_submit_node_ids = set([1, 2])
        assert updated_submit_node_ids == expected_submit_node_ids, "User submit nodes should be updated correctly"

    def test_update_users_submit_nodes_twice(self, admin_client: Client, user_factory, project_factory):
        """Test updating user's submit nodes"""

        project = project_factory()
        user = user_factory(10, project['id'])

        update_payload = {
            "submit_nodes": [
                {
                    "submit_node_id": 1
                },
                {
                    "submit_node_id": 2
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['submit_node_id'], updated_data['submit_nodes']))
        expected_submit_node_ids = set([1, 2])
        assert updated_submit_node_ids == expected_submit_node_ids, "User submit nodes should be updated correctly"

        update_payload = {
            "submit_nodes": [
                {
                    "submit_node_id": 2
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['submit_node_id'], updated_data['submit_nodes']))
        expected_submit_node_ids = set([2])
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
        user = user_factory(random.randint(2001, 3000), filled_out_project['id'])

        response = admin_client.get(f"/users/{user['id']}/submit_nodes")

        assert response.status_code == 200, f"Getting user submit nodes should return a 200 status code, instead got {response.text}"
        submit_nodes = response.json()
        assert len(submit_nodes) > 0, "User should have at least one submit node"
        assert user['submit_nodes'][0]['submit_node_id'] in map(lambda x: x['submit_node_id'], submit_nodes), "User's submit nodes should include those from the filled out project"

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
            admin_client.post(f"/groups/{group_id}/users", json={"id": user['id']})

        response = admin_client.get(f"/users/{user['id']}/groups")

        assert response.status_code == 200, f"Getting user groups should return a 200 status code, instead got {response.text}"
        groups = response.json()
        assert len(groups) == len(group_ids), f"User should belong to {len(group_ids)} groups"
        assert all(group['id'] in group_ids for group in groups), "User's groups should match the added groups"

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
    def test_schema_computed_fields_follow_username_and_netid(self):
        netid_user = UserGet(**schema_user_data(active=True, username="testnetid", netid="testnetid"))
        username_user = UserGet(**schema_user_data(active=True, username="unixuser", netid="testnetid"))
        inactive_project_view = JoinedProjectView(
            **schema_project_view_data(active=False, username="unixuser", netid="testnetid", role=RoleEnum.MEMBER)
        )

        assert netid_user.auth_netid is True
        assert netid_user.auth_username is False
        assert username_user.auth_netid is False
        assert username_user.auth_username is True
        assert inactive_project_view.model_dump()["auth_netid"] is False
        assert inactive_project_view.model_dump()["auth_username"] is False

    def test_userpost_requires_netid_when_active(self):
        with pytest.raises(ValidationError) as exc_info:
            UserPost(**schema_user_data(username="testnetid", active=True, netid=None))

        assert "netid must be provided" in str(exc_info.value).lower()

    def test_create_active_user_defaults_username_to_netid(self, admin_client: Client, project_factory):
        project = project_factory()
        user_payload = user_data_f(101, project["id"])
        user_payload.pop("username")

        create_response = admin_client.post("/users", json=user_payload)
        assert create_response.status_code == 201, create_response.text
        created_user = create_response.json()

        assert created_user["username"] == created_user["netid"]
        assert created_user["auth_netid"] is True
        assert created_user["auth_username"] is False

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
