from userapp.core.models.enum import RoleEnum

from userapp.api.tests.main import basic_auth_client as client, api_client as unauthed_client


class TestProjectsAI:
    def test_create_project(self, client):
        project_data = {
            "name": "ai-project-test",
            "accounting_group": "ai-accounting",
            "status": "active"
        }
        response = client.post("/projects", json=project_data)
        assert response.status_code == 201, f"Expected 201, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert data["name"] == project_data["name"]
        assert data["accounting_group"] == project_data["accounting_group"]
        assert data["status"] == project_data["status"]

    def test_list_projects(self, client):
        response = client.get("/projects")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert isinstance(data, list)
        assert any("name" in project for project in data)

    def test_update_project(self, client):
        response = client.get("/projects?page_size=1")
        project = response.json()[0]
        project_id = project["id"]
        update_data = {"name": "ai-project-updated"}
        response = client.put(f"/projects/{project_id}", json=update_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        updated = response.json()
        assert updated["name"] == "ai-project-updated"

    def test_delete_project(self, client):
        project_data = {
            "name": "ai-project-delete",
            "accounting_group": "ai-accounting",
            "status": "active"
        }
        response = client.post("/projects", json=project_data)
        project_id = response.json()["id"]
        del_response = client.delete(f"/projects/{project_id}")
        assert del_response.status_code == 204, f"Expected 204, got {del_response.status_code}. Response: {del_response.content}"
        get_response = client.get(f"/projects/{project_id}")
        assert get_response.status_code == 404

    def test_add_user_to_project(self, client, user):
        project_data = {
            "name": "ai-project-user",
            "accounting_group": "ai-accounting",
            "status": "active"
        }
        response = client.post("/projects", json=project_data)
        project_id = response.json()["id"]
        add_user_data = {
            "user_id": user["id"],
            "role": RoleEnum.MEMBER.value,
            "is_primary": False
        }
        add_user_response = client.post(f"/projects/{project_id}/users", json=add_user_data)
        assert add_user_response.status_code == 201, f"Expected 201, got {add_user_response.status_code}. Response: {add_user_response.content}"

    def test_filter_projects_by_status(self, client):
        project_data_active = {"name": "ai-project-active", "accounting_group": "ai-accounting", "status": "active"}
        project_data_inactive = {"name": "ai-project-inactive", "accounting_group": "ai-accounting", "status": "inactive"}
        client.post("/projects", json=project_data_active)
        client.post("/projects", json=project_data_inactive)
        response = client.get("/projects?status=eq.active")
        assert response.status_code == 200
        data = response.json()
        assert any(p["status"] == "active" for p in data)
        response = client.get("/projects?status=eq.inactive")
        assert response.status_code == 200
        data = response.json()
        assert any(p["status"] == "inactive" for p in data)

    def test_project_permissions(self, unauthed_client):
        project_data = {"name": "ai-project-perm", "accounting_group": "ai-accounting", "status": "active"}
        response = unauthed_client.post("/projects", json=project_data)
        assert response.status_code in (401, 403), f"Expected 401/403 for unauthenticated, got {response.status_code}"

    def test_project_unique_constraint(self, client):
        project_data = {"name": "ai-project-unique", "accounting_group": "ai-accounting", "status": "active"}
        client.post("/projects", json=project_data)
        response = client.post("/projects", json=project_data)
        assert response.status_code == 400, f"Expected 400 for unique constraint, got {response.status_code}"

    def test_project_unicode_name(self, client):
        project_data = {"name": "ai-プロジェクト", "accounting_group": "ai-accounting", "status": "active"}
        response = client.post("/projects", json=project_data)
        # Should fail due to regex constraint
        assert response.status_code == 422

    def test_project_long_name(self, client):
        project_data = {"name": "a"*300, "accounting_group": "ai-accounting", "status": "active"}
        response = client.post("/projects", json=project_data)
        assert response.status_code == 422
