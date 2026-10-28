from userapp.api.util import route_method_lookup
from userapp.main import create_app


class TestProjectsAI:
    def test_get_routes(self, admin_client):
        response = admin_client.get("/routes")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        data = response.json()
        assert isinstance(data, list)

        for r in data:
            assert "route" in r
            assert "method" in r


class TestIncludedRoutes:
    """app.routes is a tree of included routers since FastAPI 0.137; routes inside them must still be found."""

    def test_get_routes_lists_routes_from_included_routers(self, admin_client):
        response = admin_client.get("/routes")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.content}"
        routes = {(r["route"], r["method"]) for r in response.json()}
        assert ("/projects", "GET") in routes
        assert ("/tokens/{token_id}/permissions", "POST") in routes
        assert ("/forms/user-applications", "POST") in routes

    def test_route_method_lookup_finds_routes_from_included_routers(self):
        routes = create_app().routes

        assert route_method_lookup(routes, "/tokens/{token_id}/permissions", "POST") is True
        assert route_method_lookup(routes, "/projects", "GET") is True

    def test_route_method_lookup_rejects_unknown_route_and_method(self):
        routes = create_app().routes

        assert route_method_lookup(routes, "/does-not-exist", "GET") is False
        assert route_method_lookup(routes, "/projects", "TRACE") is False


class TestDocs:
    """The API sits behind an unknown path prefix, so the docs must load the schema by a relative URL."""

    def test_swagger_ui_loads_schema_relatively(self, api_client):
        response = api_client.get("/docs")

        assert response.status_code == 200
        assert "'./openapi.json'" in response.text

    def test_redoc_loads_schema_relatively(self, api_client):
        response = api_client.get("/redoc")

        assert response.status_code == 200
        assert 'spec-url="./openapi.json"' in response.text

    def test_openapi_server_is_relative(self, api_client):
        response = api_client.get("/openapi.json")

        assert response.status_code == 200
        assert response.json()["servers"] == [{"url": "."}]
