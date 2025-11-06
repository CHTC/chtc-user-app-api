import pytest

from api.tests.main import basic_auth_client as client, api_client as unauthed_client, admin_user


class TestUsersAI:
    def test_create_user(self, client):
        user_data = {
            "username": "ai-user-test",
            "name": "AI User",
            "email1": "aiuser@example.com",
            "password": "securepassword",
            "primary_project_id": 1,
            "primary_project_role": "MEMBER"
        }
        response = client.post("/users", json=user_data)
        assert response.status_code == 201, f"Expected 201, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert data["username"] == user_data["username"]
        assert data["name"] == user_data["name"]
        assert data["email1"] == user_data["email1"]

    def test_list_users(self, client):
        response = client.get("/users")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert isinstance(data, list)
        assert any("username" in user for user in data)

    def test_update_user(self, client):
        response = client.get("/users?page_size=1")
        user = response.json()[0]
        user_id = user["id"]
        update_data = {"name": "AI User Updated"}
        response = client.put(f"/users/{user_id}", json=update_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        updated = response.json()
        assert updated["name"] == "AI User Updated"

    def test_delete_user(self, client):
        user_data = {
            "username": "ai-user-delete",
            "name": "AI User",
            "email1": "aiuserdelete@example.com",
            "password": "securepassword",
            "primary_project_id": 1,
            "primary_project_role": "MEMBER"
        }
        response = client.post("/users", json=user_data)
        user_id = response.json()["id"]
        del_response = client.delete(f"/users/{user_id}")
        assert del_response.status_code == 204, f"Expected 204, got {del_response.status_code}. Response: {del_response.content}"
        get_response = client.get(f"/users/{user_id}")
        assert get_response.status_code == 404

    def test_filter_users_by_email(self, client):
        user_data1 = {"username": "ai-user-email1", "name": "AI User1", "email1": "aiuser1@example.com", "password": "securepassword", "primary_project_id": 1, "primary_project_role": "MEMBER"}
        user_data2 = {"username": "ai-user-email2", "name": "AI User2", "email1": "aiuser2@example.com", "password": "securepassword", "primary_project_id": 1, "primary_project_role": "MEMBER"}
        client.post("/users", json=user_data1)
        client.post("/users", json=user_data2)
        response = client.get("/users?email1=eq.aiuser1@example.com")
        assert response.status_code == 200
        data = response.json()
        assert any(u["email1"] == "aiuser1@example.com" for u in data)

    def test_user_permissions(self, unauthed_client):
        user_data = {"username": "ai-user-perm", "name": "AI User", "email1": "aiuserperm@example.com", "password": "securepassword", "primary_project_id": 1, "primary_project_role": "MEMBER"}
        response = unauthed_client.post("/users", json=user_data)
        assert response.status_code in (401, 403), f"Expected 401/403 for unauthenticated, got {response.status_code}"

    def test_user_unique_constraint(self, client):
        user_data = {"username": "ai-user-unique", "name": "AI User", "email1": "aiuserunique@example.com", "password": "securepassword", "primary_project_id": 1, "primary_project_role": "MEMBER"}
        client.post("/users", json=user_data)
        response = client.post("/users", json=user_data)
        assert response.status_code == 400, f"Expected 400 for unique constraint, got {response.status_code}"

    def test_user_unicode_name(self, client):
        user_data = {"username": "ai-user-unicode", "name": "ユーザーAI", "email1": "aiuserunicode@example.com", "password": "securepassword", "primary_project_id": 1, "primary_project_role": "MEMBER"}
        response = client.post("/users", json=user_data)
        # Should fail due to validator
        assert response.status_code == 422

    def test_user_long_username(self, client):
        user_data = {"username": "a"*300, "name": "AI User", "email1": "aiuserlong@example.com", "password": "securepassword", "primary_project_id": 1, "primary_project_role": "MEMBER"}
        response = client.post("/users", json=user_data)
        assert response.status_code == 422
import pytest

class TestGroupsAI:
    def test_create_group(self, client):
        group_data = {
            "name": "ai-group-test",
            "point_of_contact": "ai-contact",
            "unix_gid": 55555,
            "has_groupdir": True
        }
        response = client.post("/groups", json=group_data)
        assert response.status_code == 201, f"Expected 201, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert data["name"] == group_data["name"]
        assert data["point_of_contact"] == group_data["point_of_contact"]
        assert data["unix_gid"] == group_data["unix_gid"]
        assert data["has_groupdir"] == group_data["has_groupdir"]

    def test_list_groups(self, client):
        response = client.get("/groups")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert isinstance(data, list)
        assert any("name" in group for group in data)

    def test_update_group(self, client):
        response = client.get("/groups?page_size=1")
        group = response.json()[0]
        group_id = group["id"]
        update_data = {"name": "ai-group-updated"}
        response = client.put(f"/groups/{group_id}", json=update_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        updated = response.json()
        assert updated["name"] == "ai-group-updated"

    def test_delete_group(self, client):
        group_data = {
            "name": "ai-group-delete",
            "point_of_contact": "ai-contact",
            "unix_gid": 55556,
            "has_groupdir": True
        }
        response = client.post("/groups", json=group_data)
        group_id = response.json()["id"]
        del_response = client.delete(f"/groups/{group_id}")
        assert del_response.status_code == 204, f"Expected 204, got {del_response.status_code}. Response: {del_response.content}"
        get_response = client.get(f"/groups/{group_id}")
        assert get_response.status_code == 404
