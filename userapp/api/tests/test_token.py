from httpx import Client


from userapp.api.tests.main import basic_auth_client as client, api_client, token, user_auth_client as user_client, admin_user, project, user_factory, project_factory, filled_out_project


class TestUsers:

    def test_create_token(self, client: Client):
        """Test create token"""

        r = client.post("/tokens", json={
                    "description": "Test Token"
        })

        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["description"] == "Test Token"
        assert "token" in data
        assert data["created_by"] is not None
        assert "created_at" in data
        assert data["expires_at"] is None

    def test_use_token(self, token: str, api_client: Client):
        """Test using token to authenticate"""

        r = api_client.get("/users", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200