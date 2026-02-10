import os
from typing import Callable

from httpx import Client
from starlette.testclient import TestClient

from userapp.api.tests.conftest import BLACK_IP, VALID_CIDR_RANGE, WHITE_IP


class TestTokens:

    def test_create_token_non_admin(self, nonadmin_client: Client):
        """Test create token as non-admin"""

        r = nonadmin_client.post("/tokens", json={
                    "description": "Test Token"
        })

        assert r.status_code == 403

    def test_create_token(self, admin_client: Client):
        """Test create token"""

        r = admin_client.post("/tokens", json={
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

    def test_get_tokens(self, admin_client: Client):
        """Test get tokens"""

        r = admin_client.get("/tokens")

        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_use_token_bad_ip_none(self, token_client: Callable[[str], TestClient]):
        """Test using token to authenticate"""

        del os.environ['TOKEN_IP_WHITELIST']

        with token_client() as client:

            r = client.get(
                "/users"
            )

            assert r.status_code == 200

    def test_use_token_bad_ip_single(self, token_client: Callable[[str], TestClient]):
        """Test using token to authenticate"""

        os.environ['TOKEN_IP_WHITELIST'] = VALID_CIDR_RANGE

        with token_client(BLACK_IP) as client:

            r = client.get(
                "/users"
            )

            assert r.status_code == 403

    def test_use_token_good_ip_single(self, token_client: Callable[[str], TestClient]):
        """Test using token to authenticate"""

        os.environ['TOKEN_IP_WHITELIST'] = VALID_CIDR_RANGE

        with token_client(WHITE_IP) as client:
            r = client.get(
                "/users"
            )

            assert r.status_code == 200

    # Assumes token can GET /users
    def test_use_token_on_unauthed_route(self, token_client: Callable[[str], TestClient]):
        """Test using token to authenticate on an unauthed route"""

        with token_client() as client:
            r = client.get(
                "/groups"
            )

            assert r.status_code == 403

    # Assumes token can GET /users
    def test_use_token_on_unauthed_method(self, token, token_client: Callable[[str], TestClient]):
        """Test using token to authenticate on an unauthed route"""

        with token_client() as client:
            r = client.post(
                f"/tokens/{token['id']}/permissions",
                json={
                    "route": "/tokens",
                    "method": "POST"
                }
            )

            assert r.status_code == 403

    def test_use_token_on_variable_route(self, token, token_client: Callable[[str], TestClient]):
        """Test using token to authenticate on an unauthed route"""

        with token_client() as client:
            r = client.get(
                f"/tokens/{token['id']}"
            )

            assert r.status_code == 200

    def test_use_token_on_variable_route_no_permission(self, token, token_client: Callable[[str], TestClient]):
        """Test using token to authenticate on an unauthed route"""

        with token_client() as client:
            r = client.get(
                f"/groups/{token['id'] + 9999}"
            )

            assert r.status_code == 403

    def test_create_token_permission(self, token, admin_client: TestClient):
        """Test creating a token permission"""

        r = admin_client.post(
            f"/tokens/{token['id']}/permissions",
            json={
                "route": "/users",
                "method": "GET"
            }
        )

        assert r.status_code == 201
        data = r.json()
        assert data["route"] == "/users"
        assert data["method"] == "GET"

    def test_create_token_permission_invalid_route(self, admin_client: TestClient, token):
        """Test creating a token permission with an invalid route"""

        r = admin_client.post(
            f"/tokens/{token['id']}/permissions",
            json={
                "route": "/invalidroute",
                "method": "GET"
            }
        )

        assert r.status_code == 400

    def test_create_token_permission_invalid_method(self, token, admin_client: TestClient):
        """Test creating a token permission with an invalid method"""

        r = admin_client.post(
            f"/tokens/{token['id']}/permissions",
            json={
                "route": "/users",
                "method": "INVALIDMETHOD"
            }
        )

        assert r.status_code == 400

    def test_add_permission_nonadmin(self, token, nonadmin_client: TestClient):
        """Test creating a token permission as non-admin"""

        r = nonadmin_client.post(
            f"/tokens/{token['id']}/permissions",
            json={
                "route": "/users",
                "method": "GET"
            }
        )

        assert r.status_code == 403

    def test_delete_token_then_use(self, token, token_client: Callable[[str], TestClient], admin_client: TestClient):
        """Test deleting a token then trying to use it"""

        r = admin_client.delete(
            f"/tokens/{token['id']}"
        )
        assert r.status_code == 204

        with token_client() as client:
            r = client.get(
                "/users"
            )

            assert r.status_code == 403

    def test_adding_permission_from_routes_endpoint(self, token, admin_client: TestClient):
        """Test adding a permission to a token from the /routes endpoint"""

        # First get the list of routes to find a valid route and method
        r = admin_client.get("/routes")
        assert r.status_code == 200
        routes = r.json()
        assert isinstance(routes, list)
        assert len(routes) > 0

        # Find a route that is not the tokens route and has a GET method
        route_info = next((route for route in routes if route["route"] != "/tokens" and route['method'] == "GET"), None)
        assert route_info is not None, "No suitable route found for testing"

        r = admin_client.post(
            f"/tokens/{token['id']}/permissions",
            json={
                "route": route_info["route"],
                "method": route_info["method"]
            }
        )

        assert r.status_code == 201