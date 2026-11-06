import random

from userapp.api.tests.conftest import admin_client as client, api_client as unauthed_client, admin_user


class TestGroupsAI:

    def test_filter_groups_by_name(self, client):
        group_data = {
            "name": f"ai-group-filter-{random.randint(100000, 999999)}",
            "unix_gid": random.randint(56000, 59900),
        }
        client.post("/groups", json=group_data)
        response = client.get(f"/groups?name=eq.{group_data['name']}")
        assert response.status_code == 200
        data = response.json()
        assert any(g["name"] == group_data["name"] for g in data), f"Group with name filter not found. Got: {data}"

    def test_pagination_groups(self, client):
        # Create multiple groups for pagination
        for i in range(3):
            client.post("/groups", json={
                "name": f"ai-group-page-{random.randint(100000, 999999)}-{i}",
            })
        response = client.get("/groups?page=0&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2, f"Pagination failed, got {len(data)} groups."
        assert int(response.headers["X-Total-Count"]) >= 3

    def test_create_group_missing_optional_fields(self, client):
        group_data = {"name": f"ai-group-minimal-{random.randint(100000, 999999)}"}
        response = client.post("/groups", json=group_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == group_data["name"]
        assert data["unix_gid"] is None
        assert data["owner_group_id"] is None
        assert data["description"] is None
        assert data["managed_by"] == "APPLICATION"

    def test_create_group_managed_by_an_external_system(self, client):
        response = client.post("/groups", json={
            "name": f"ai-group-managed-{random.randint(100000, 999999)}",
            "managed_by": "MANIFEST",
        })
        assert response.status_code == 201
        assert response.json()["managed_by"] == "MANIFEST"

    def test_delete_nonexistent_group(self, client):
        response = client.delete("/groups/99999999")
        assert response.status_code == 404, f"Expected 404 for non-existent group, got {response.status_code}"

    def test_response_structure(self, client):
        response = client.get("/groups?page_size=1")
        assert response.status_code == 200
        data = response.json()
        if data:
            group = data[0]
            assert isinstance(group["id"], int)
            assert isinstance(group["name"], str)
            for key in ("unix_gid", "owner_group_id", "description", "managed_by", "deleted_at", "created_at", "updated_at"):
                assert key in group, f"{key} missing from {group}"
            assert "point_of_contact" not in group
            assert "has_groupdir" not in group

    def test_filter_groups_by_owner(self, client, group_factory):
        owner = group_factory()
        owned = group_factory(owner_group_id=owner["id"])
        response = client.get(f"/groups?owner_group_id=eq.{owner['id']}")
        assert response.status_code == 200
        assert [g["id"] for g in response.json()] == [owned["id"]]

    def test_group_permissions(self, unauthed_client):
        group_data = {"name": "ai-group-perm", "unix_gid": 55602}
        response = unauthed_client.post("/groups", json=group_data)
        assert response.status_code in (401, 403), f"Expected 401/403 for unauthenticated, got {response.status_code}"

    def test_group_unique_constraint(self, client):
        group_data = {"name": f"ai-group-unique-{random.randint(100000, 999999)}", "unix_gid": random.randint(56000, 59900)}
        assert client.post("/groups", json=group_data).status_code == 201
        response = client.post("/groups", json=group_data)
        assert response.status_code == 400, f"Expected 400 for unique constraint, got {response.status_code}"
