import pytest
import random

from httpx import Client

from userapp.api.tests.main import basic_auth_client as client, user_auth_client as user_client, user, admin_user, project_factory, user_factory


class TestSubmitNodesSecurity:

    def test_get_submit_nodes_requires_authentication(self, api_client: Client):
        """Unauthenticated requests to GET /submit_nodes should be rejected with 401."""

        response = api_client.get("/submit_nodes")

        assert response.status_code == 401, (
            f"Unauthenticated GET /submit_nodes should return 401, got {response.status_code}: {response.text}"
        )

    def test_get_submit_nodes_as_authenticated_user(self, user_client: Client):
        """Authenticated non-admin users should be able to list submit nodes."""

        response = user_client.get("/submit_nodes")

        assert response.status_code == 200, (
            f"Authenticated GET /submit_nodes should return 200, got {response.status_code}: {response.text}"
        )

    def test_create_submit_node_requires_admin(self, user_client: Client, project_factory, user_factory):
        """Non-admin users should not be able to create submit nodes."""

        submit_node_data = {
            "name": "Test Submit Node",
            "url": "https://submit.node.test",
            "description": "A test submit node"
        }

        response = user_client.post("/submit_nodes", json=submit_node_data)

        assert response.status_code == 403, (
            f"Non-admin POST /submit_nodes should return 403, got {response.status_code}: {response.text}"
        )

    def test_create_submit_node_as_admin(self, client: Client):
        """Admin users should be able to create submit nodes."""

        submit_node_data = {
            "name": f"test-submit{random.randint(0,10**5)}.node",
        }

        response = client.post("/submit_nodes", json=submit_node_data)

        assert response.status_code == 201, (
            f"Admin POST /submit_nodes should return 201, got {response.status_code}: {response.text}"
        )

    def test_delete_submit_node_requires_admin(self, user_client: Client):
        """Non-admin users should not be able to delete submit nodes."""

        # Attempt to delete as non-admin
        delete_response = user_client.delete(f"/submit_nodes/1")

        assert delete_response.status_code == 403, (
            f"Non-admin DELETE /submit_nodes/1 should return 403, got {delete_response.status_code}: {delete_response.text}"
        )

    def test_delete_submit_node_as_admin(self, client: Client):
        """Admin users should be able to delete submit nodes."""

        # First create a submit node to delete
        submit_node_data = {
            "name": f"test-submit{random.randint(0,10**5)}.node",
        }

        create_response = client.post("/submit_nodes", json=submit_node_data)
        assert create_response.status_code == 201, (
            f"Admin POST /submit_nodes should return 201, got {create_response.status_code}: {create_response.text}"
        )

        submit_node_id = create_response.json()['id']

        # Now delete the created submit node
        delete_response = client.delete(f"/submit_nodes/{submit_node_id}")

        assert delete_response.status_code == 204, (
            f"Admin DELETE /submit_nodes/{submit_node_id} should return 204, got {delete_response.status_code}: {delete_response.text}"
        )

    def test_update_submit_node_as_admin(self, client: Client):
        """Test admins can update submit nodes."""

        # First create a submit node to update
        submit_node_data = {
            "name": f"test-submit{random.randint(0,10**5)}.node",
        }

        create_response = client.post("/submit_nodes", json=submit_node_data)
        assert create_response.status_code == 201, (
            f"Admin POST /submit_nodes should return 201, got {create_response.status_code}: {create_response.text}"
        )

        submit_node_id = create_response.json()['id']

        # Now update the created submit node
        updated_name = f"test-submit{random.randint(0,10**5)}.node"
        update_data = {
            "name": updated_name,
        }

        update_response = client.put(f"/submit_nodes/{submit_node_id}", json=update_data)

        assert update_response.status_code == 200, (
            f"Admin PUT /submit_nodes/{submit_node_id} should return 200, got {update_response.status_code}: {update_response.text}"
        )
        assert update_response.json()['name'] == updated_name, (
            f"Updated submit node name should be '{updated_name}', got '{update_response.json()['name']}'"
        )


