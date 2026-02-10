
class TestProjectsAI:
    def test_get_routes(self, admin_client):
        response = admin_client.get("/routes")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert isinstance(data, list)

        for r in data:
            assert "route" in r
            assert "method" in r
