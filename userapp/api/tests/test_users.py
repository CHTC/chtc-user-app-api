import random

from httpx import Client

from userapp.api.tests.fake_data import user_data_f
from userapp.api.tests.main import basic_auth_client as client, admin_user, project, user, user_factory, project_factory, filled_out_project


class TestUsers:

    def test_list_users(self, client: Client, admin_user: dict, user_factory, project_factory):
        """Test listing users"""

        project = project_factory()

        # Create some users
        num_users = 5
        for _ in range(num_users):
            user_factory(_, project['id'])

        response = client.get("/users?is_pi=eq.true")

        assert response.status_code == 200, f"Listing users should return a 200 status code, instead got {response.text}"
        users_list = response.json()
        assert len(users_list) >= num_users, f"Users list should contain at least {num_users} users, found {len(users_list)}"

    def test_create_user(self, client: Client, project: dict):
        """Test creating a new user"""
        user_payload = user_data_f(1, project['id'])

        response = client.post(
            "/users",
            json=user_payload
        )

        assert response.status_code == 201, f"Creating a user should return a 201 status code, instead got {response.text}"
        created_user = response.json()
        for key in created_user:
            if not key in ["password", "id", "is_pi", "submit_nodes"]:  # Password is not returned in the response
                assert created_user[key] == user_payload[key], f"User {key} should match the payload"

        assert set(map(lambda x: x['submit_node_id'], user_payload['submit_nodes'])) == set(map(lambda x: x['submit_node_id'], created_user['submit_nodes']))

    def test_get_user_projects(self, client: Client, user_factory, filled_out_project: dict):
        """Test getting projects for a user"""
        user = user_factory(random.randint(1000, 2000), filled_out_project['id'])

        response = client.get(f"/users/{user['id']}/projects")

        assert response.status_code == 200, f"Getting user projects should return a 200 status code, instead got {response.text}"
        projects = response.json()
        assert len(projects) > 0, "User should have at least one project"
        assert any(proj['project_id'] == filled_out_project['id'] for proj in projects), "User's projects should include the filled out project"

    def test_get_user_submit_nodes(self, client: Client, user_factory, filled_out_project: dict):
        """Test getting submit nodes for a user"""
        user = user_factory(random.randint(2001, 3000), filled_out_project['id'])

        response = client.get(f"/users/{user['id']}/submit_nodes")

        assert response.status_code == 200, f"Getting user submit nodes should return a 200 status code, instead got {response.text}"
        submit_nodes = response.json()
        assert len(submit_nodes) > 0, "User should have at least one submit node"
        assert user['submit_nodes'][0]['submit_node_id'] in map(lambda x: x['submit_node_id'], submit_nodes), "User's submit nodes should include those from the filled out project"
