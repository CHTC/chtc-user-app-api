import asyncio
import pytest
import random

from httpx import Client
from sqlalchemy import text

from userapp.api.tests.conftest import _seed_db_url
from userapp.db import connect_engine


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


class TestSubmitNodeGroups:
    """A submit node's group is what carries access to it, so the two have to stay in step."""

    def test_create_submit_node_with_unknown_group_is_rejected(self, admin_client: Client):
        """group_id has to reference a real group."""

        response = admin_client.post(
            "/submit_nodes",
            json={"name": f"test-submit-{random.randint(0, 10**6)}", "group_id": 10 ** 8},
        )

        assert response.status_code == 404, (
            f"POST /submit_nodes with an unknown group_id should return 404, got {response.status_code}: {response.text}"
        )

    def test_submit_node_cannot_point_at_a_deleted_group(self, existing_admin_client: Client, group_factory):
        """A deleted group has no members, so a node on it would grant access to no one"""

        gone = group_factory()
        existing_admin_client.delete(f"/groups/{gone['id']}")
        live = group_factory()
        try:
            body = {"name": f"test-submit-{random.randint(0, 10**6)}", "group_id": gone['id']}
            assert existing_admin_client.post("/submit_nodes", json=body).status_code == 404

            node = existing_admin_client.post("/submit_nodes", json={**body, "group_id": live['id']}).json()
            try:
                response = existing_admin_client.put(f"/submit_nodes/{node['id']}", json={"name": node['name'], "group_id": gone['id']})
                assert response.status_code == 404, response.text
                assert existing_admin_client.get(f"/submit_nodes?id=eq.{node['id']}").json()[0]['group_id'] == live['id']
            finally:
                existing_admin_client.delete(f"/submit_nodes/{node['id']}")
        finally:
            existing_admin_client.delete(f"/groups/{live['id']}")

    def test_deleting_the_group_revokes_submit_node_access(self, admin_client: Client, user_factory, project: dict):
        """Deleting a group detaches its submit node and takes every user's access with it."""

        submit_node = create_submit_node(admin_client)
        user = user_factory(random.randint(11001, 12000), project['id'], submit_node_ids=[submit_node['id']])

        delete_response = admin_client.delete(f"/groups/{submit_node['group_id']}")

        assert delete_response.status_code == 204, (
            f"Admin DELETE /groups/{submit_node['group_id']} should return 204, got {delete_response.status_code}: {delete_response.text}"
        )

        node_response = admin_client.get(f"/submit_nodes?id=eq.{submit_node['id']}")
        assert node_response.status_code == 200, f"GET /submit_nodes should return 200, got {node_response.text}"
        assert node_response.json()[0]['group_id'] is None, "Deleting the group should leave the submit node without one"

        user_nodes_response = admin_client.get(f"/users/{user['id']}/submit_nodes")
        assert user_nodes_response.status_code == 200, f"GET /users/{user['id']}/submit_nodes should return 200, got {user_nodes_response.text}"
        assert submit_node['id'] not in [node['id'] for node in user_nodes_response.json()], "Deleting the group should revoke access to its submit node"

    def test_deleting_the_submit_node_keeps_group_membership(self, admin_client: Client, user_factory, project: dict):
        """Deleting a submit node leaves its group, and the users in it, alone."""

        submit_node = create_submit_node(admin_client)
        user = user_factory(random.randint(12001, 13000), project['id'], submit_node_ids=[submit_node['id']])

        delete_response = admin_client.delete(f"/submit_nodes/{submit_node['id']}")

        assert delete_response.status_code == 204, (
            f"Admin DELETE /submit_nodes/{submit_node['id']} should return 204, got {delete_response.status_code}: {delete_response.text}"
        )

        groups_response = admin_client.get(f"/users/{user['id']}/groups")
        assert groups_response.status_code == 200, f"GET /users/{user['id']}/groups should return 200, got {groups_response.text}"
        assert submit_node['group_id'] in [group['group_id'] for group in groups_response.json()], "Deleting a submit node should not remove its group membership"


class TestSubmitNodesSecurity:

    def test_get_submit_nodes_requires_authentication(self, api_client: Client):
        """Unauthenticated requests to GET /submit_nodes should be rejected with 401."""

        response = api_client.get("/submit_nodes")

        assert response.status_code == 401, (
            f"Unauthenticated GET /submit_nodes should return 401, got {response.status_code}: {response.text}"
        )

    def test_get_submit_nodes_as_authenticated_user(self, nonadmin_client: Client):
        """Authenticated non-admin users should be able to list submit nodes."""

        response = nonadmin_client.get("/submit_nodes")

        assert response.status_code == 200, (
            f"Authenticated GET /submit_nodes should return 200, got {response.status_code}: {response.text}"
        )

    def test_create_submit_node_requires_admin(self, nonadmin_client: Client, project_factory, user_factory):
        """Non-admin users should not be able to create submit nodes."""

        submit_node_data = {
            "name": "Test Submit Node",
            "url": "https://submit.node.test",
            "description": "A test submit node"
        }

        response = nonadmin_client.post("/submit_nodes", json=submit_node_data)

        assert response.status_code == 403, (
            f"Non-admin POST /submit_nodes should return 403, got {response.status_code}: {response.text}"
        )

    def test_create_submit_node_as_admin(self, admin_client: Client):
        """Admin users should be able to create submit nodes."""

        submit_node_data = {
            "name": f"test-submit{random.randint(0,10**5)}.node",
        }

        response = admin_client.post("/submit_nodes", json=submit_node_data)

        assert response.status_code == 201, (
            f"Admin POST /submit_nodes should return 201, got {response.status_code}: {response.text}"
        )

    def test_delete_submit_node_requires_admin(self, nonadmin_client: Client):
        """Non-admin users should not be able to delete submit nodes."""

        # Attempt to delete as non-admin
        delete_response = nonadmin_client.delete(f"/submit_nodes/1")

        assert delete_response.status_code == 403, (
            f"Non-admin DELETE /submit_nodes/1 should return 403, got {delete_response.status_code}: {delete_response.text}"
        )

    def test_delete_submit_node_as_admin(self, admin_client: Client):
        """Admin users should be able to delete submit nodes."""

        # First create a submit node to delete
        submit_node_data = {
            "name": f"test-submit{random.randint(0,10**5)}.node",
        }

        create_response = admin_client.post("/submit_nodes", json=submit_node_data)
        assert create_response.status_code == 201, (
            f"Admin POST /submit_nodes should return 201, got {create_response.status_code}: {create_response.text}"
        )

        submit_node_id = create_response.json()['id']

        # Now delete the created submit node
        delete_response = admin_client.delete(f"/submit_nodes/{submit_node_id}")

        assert delete_response.status_code == 204, (
            f"Admin DELETE /submit_nodes/{submit_node_id} should return 204, got {delete_response.status_code}: {delete_response.text}"
        )

    def test_update_submit_node_as_admin(self, admin_client: Client):
        """Test admins can update submit nodes."""

        # First create a submit node to update
        submit_node_data = {
            "name": f"test-submit{random.randint(0,10**5)}.node",
        }

        create_response = admin_client.post("/submit_nodes", json=submit_node_data)
        assert create_response.status_code == 201, (
            f"Admin POST /submit_nodes should return 201, got {create_response.status_code}: {create_response.text}"
        )

        submit_node_id = create_response.json()['id']

        # Now update the created submit node
        updated_name = f"test-submit{random.randint(0,10**5)}.node"
        update_data = {
            "name": updated_name,
        }

        update_response = admin_client.put(f"/submit_nodes/{submit_node_id}", json=update_data)

        assert update_response.status_code == 200, (
            f"Admin PUT /submit_nodes/{submit_node_id} should return 200, got {update_response.status_code}: {update_response.text}"
        )
        assert update_response.json()['name'] == updated_name, (
            f"Updated submit node name should be '{updated_name}', got '{update_response.json()['name']}'"
        )




def _submit_node_audit(submit_node_id: int) -> list[dict]:
    """Reads the audit log with raw SQL so this module does not depend on the audit API"""

    async def run():
        engine = await connect_engine(_seed_db_url())
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT actor_id, group_id, details FROM audit_log WHERE action = 'metadata_changed' "
                        "AND details->>'entity' = 'submit_node' AND (details->>'entity_id')::int = :i ORDER BY id"
                    ),
                    {"i": submit_node_id},
                )
                return [dict(row._mapping) for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(run())


class TestSubmitNodeAudit:

    def test_changing_group_and_name_is_audited_against_the_new_group(self, existing_admin_client: Client, existing_admin_user: dict):
        submit_node = create_submit_node(existing_admin_client)
        new_group = existing_admin_client.post("/groups", json={"name": f"Test_Group_{random.randint(1, 10000000)}"}).json()
        new_name = f"test-submit-renamed-{random.randint(0, 10**6)}"

        response = existing_admin_client.put(
            f"/submit_nodes/{submit_node['id']}", json={"name": new_name, "group_id": new_group['id']},
        )
        assert response.status_code == 200, response.text

        [entry] = _submit_node_audit(submit_node['id'])
        assert entry['group_id'] == new_group['id']
        assert entry['actor_id'] == existing_admin_user['id']
        assert entry['details']['changes'] == {
            "name": {"old": submit_node['name'], "new": new_name},
            "group_id": {"old": submit_node['group_id'], "new": new_group['id']},
        }

    def test_clearing_the_group_is_audited(self, existing_admin_client: Client):
        submit_node = create_submit_node(existing_admin_client)
        response = existing_admin_client.put(
            f"/submit_nodes/{submit_node['id']}", json={"name": submit_node['name'], "group_id": None},
        )
        assert response.status_code == 200, response.text

        [entry] = _submit_node_audit(submit_node['id'])
        assert entry['group_id'] is None
        assert entry['details']['changes'] == {"group_id": {"old": submit_node['group_id'], "new": None}}

    def test_unchanged_put_writes_no_audit_entry(self, existing_admin_client: Client):
        submit_node = create_submit_node(existing_admin_client)
        response = existing_admin_client.put(
            f"/submit_nodes/{submit_node['id']}", json={"name": submit_node['name'], "group_id": submit_node['group_id']},
        )
        assert response.status_code == 200, response.text
        assert _submit_node_audit(submit_node['id']) == []

    def test_put_unknown_submit_node_is_404(self, existing_admin_client: Client):
        assert existing_admin_client.put("/submit_nodes/99999999", json={"name": "x"}).status_code == 404
