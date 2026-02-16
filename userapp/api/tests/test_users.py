import random

from httpx import Client

from userapp.api.tests.fake_data import user_data_f

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
            if key not in ["id", "is_pi", "submit_nodes", "date", "notes", "projects", "groups", "auth_netid", "auth_username"]:
                assert created_user[key] == user_payload[key], f"User {key} should match the payload"

        assert set(map(lambda x: x['submit_node_id'], user_payload['submit_nodes'])) == set(map(lambda x: x['submit_node_id'], created_user['submit_nodes']))

    def test_get_user(self, admin_client: Client, user_factory, project_factory):
        """Test getting a user by ID"""

        project = project_factory()
        user = user_factory(5, project['id'])

        user_response = admin_client.get(f"/users/{user['id']}")

        assert user_response.status_code == 200, f"Getting a user should return a 200 status code, instead got {user_response.text}"
        fetched_user = user_response.json()
        assert fetched_user['id'] == user['id'], "Fetched user ID should match the created user ID"
        assert fetched_user['name'] == user['name'], "Fetched user name should match the created user name"

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
                    "submit_node_id": 19
                },
                {
                    "submit_node_id": 20
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['submit_node_id'], updated_data['submit_nodes']))
        expected_submit_node_ids = set([19, 20])
        assert updated_submit_node_ids == expected_submit_node_ids, "User submit nodes should be updated correctly"

    def test_update_users_submit_nodes_twice(self, admin_client: Client, user_factory, project_factory):
        """Test updating user's submit nodes"""

        project = project_factory()
        user = user_factory(10, project['id'])

        update_payload = {
            "submit_nodes": [
                {
                    "submit_node_id": 19
                },
                {
                    "submit_node_id": 20
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['submit_node_id'], updated_data['submit_nodes']))
        expected_submit_node_ids = set([19, 20])
        assert updated_submit_node_ids == expected_submit_node_ids, "User submit nodes should be updated correctly"

        update_payload = {
            "submit_nodes": [
                {
                    "submit_node_id": 1
                },
                {
                    "submit_node_id": 20
                }
            ]
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 200, f"Updating a user's submit nodes should return a 200 status code, instead got {user_payload.text}"

        updated_data = user_payload.json()
        updated_submit_node_ids = set(map(lambda x: x['submit_node_id'], updated_data['submit_nodes']))
        expected_submit_node_ids = set([1, 20])
        assert updated_submit_node_ids == expected_submit_node_ids, "User submit nodes should be updated correctly"



    def test_nullify_email1(self, admin_client: Client, user_factory, project_factory):

        project = project_factory()
        user = user_factory(10, project['id'])

        update_payload = {
            "email1": ""
        }

        user_payload = admin_client.patch(f"/users/{user['id']}", json=update_payload)

        assert user_payload.status_code == 400, f"Cannot nullify email1, should return a 500 status code, instead got {user_payload.text}"

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