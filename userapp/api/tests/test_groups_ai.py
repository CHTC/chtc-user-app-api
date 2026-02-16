from userapp.api.tests.conftest import admin_client as client, api_client as unauthed_client, admin_user


class TestGroupsAI:

    def test_filter_groups_by_name(self, client):
        group_data = {
            "name": "ai-group-filter",
            "point_of_contact": "ai-contact",
            "unix_gid": 55561,
            "has_groupdir": True
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
                "name": f"ai-group-page-{i}",
                "point_of_contact": "ai-contact",
                "unix_gid": 55570 + i,
                "has_groupdir": True
            })
        response = client.get("/groups?page=0&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2, f"Pagination failed, got {len(data)} groups."

    def test_automatic_gid_allocation(self, client):
        group_data = {
            "name": "ai-group-auto-gid",
            "point_of_contact": "ai-contact",
            "has_groupdir": True
        }
        response = client.post("/groups", json=group_data)
        assert response.status_code == 201, f"Expected 201, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert "unix_gid" in data and isinstance(data["unix_gid"], int), f"Automatic unix_gid not allocated. Got: {data}"

    def test_create_group_missing_optional_fields(self, client):
        group_data = {
            "name": "ai-group-minimal",
            "unix_gid": 55580
        }
        response = client.post("/groups", json=group_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == group_data["name"]
        assert data["unix_gid"] == group_data["unix_gid"]
        assert "point_of_contact" in data
        assert "has_groupdir" in data

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
            assert "unix_gid" in group
            assert "point_of_contact" in group
            assert "has_groupdir" in group

    def test_filter_groups_by_has_groupdir(self, client):
        group_data_true = {"name": "ai-group-true", "point_of_contact": "ai-contact", "unix_gid": 55600, "has_groupdir": True}
        group_data_false = {"name": "ai-group-false", "point_of_contact": "ai-contact", "unix_gid": 55601, "has_groupdir": False}
        client.post("/groups", json=group_data_true)
        client.post("/groups", json=group_data_false)
        response = client.get("/groups?has_groupdir=eq.true")
        assert response.status_code == 200
        data = response.json()
        assert any(g["has_groupdir"] is True for g in data)
        response = client.get("/groups?has_groupdir=eq.false")
        assert response.status_code == 200
        data = response.json()
        assert any(g["has_groupdir"] is False for g in data)

    def test_group_permissions(self, unauthed_client):
        group_data = {"name": "ai-group-perm", "point_of_contact": "ai-contact", "unix_gid": 55602, "has_groupdir": True}
        response = unauthed_client.post("/groups", json=group_data)
        assert response.status_code in (401, 403), f"Expected 401/403 for unauthenticated, got {response.status_code}"

    def test_group_unique_constraint(self, client):
        group_data = {"name": "ai-group-unique", "point_of_contact": "ai-contact", "unix_gid": 55603, "has_groupdir": True}
        client.post("/groups", json=group_data)
        response = client.post("/groups", json=group_data)
        assert response.status_code == 400, f"Expected 400 for unique constraint, got {response.status_code}"

    def test_group_unicode_name(self, client):
        group_data = {"name": "ai-グループ", "point_of_contact": "ai-contact", "unix_gid": 55604, "has_groupdir": True}
        response = client.post("/groups", json=group_data)
        # Should fail due to regex constraint
        assert response.status_code == 422

    def test_group_long_point_of_contact(self, client):
        group_data = {"name": "ai-group-long-contact", "point_of_contact": "a"*60, "unix_gid": 55605, "has_groupdir": True}
        response = client.post("/groups", json=group_data)
        assert response.status_code == 201 or response.status_code == 422
        # If accepted, check truncation or error
        if response.status_code == 201:
            data = response.json()
            assert len(data["point_of_contact"]) <= 60
