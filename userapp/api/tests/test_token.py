import os
from typing import Callable

from httpx import Client
from starlette.testclient import TestClient

from userapp.api.tests.main import basic_auth_client as client, api_client, token, user_auth_client as user_client, \
    admin_user, project, user_factory, project_factory, filled_out_project, token_auth_client, VALID_CIDR_RANGE, \
    BLACK_IP, WHITE_IP


class TestTokens:

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

    def test_use_token_bad_ip_none(self, token_auth_client: Callable[[str], TestClient]):
        """Test using token to authenticate"""

        del os.environ['TOKEN_IP_WHITELIST']

        with token_auth_client() as client:

            r = client.get(
                "/users"
            )

            assert r.status_code == 200

    def test_use_token_bad_ip_single(self, token_auth_client: Callable[[str], TestClient]):
        """Test using token to authenticate"""

        os.environ['TOKEN_IP_WHITELIST'] = VALID_CIDR_RANGE

        with token_auth_client(BLACK_IP) as client:

            r = client.get(
                "/users"
            )

            assert r.status_code == 403

    def test_use_token_good_ip_single(self, token_auth_client: Callable[[str], TestClient]):
        """Test using token to authenticate"""

        os.environ['TOKEN_IP_WHITELIST'] = VALID_CIDR_RANGE

        with token_auth_client(WHITE_IP) as client:
            r = client.get(
                "/users"
            )

            assert r.status_code == 200
