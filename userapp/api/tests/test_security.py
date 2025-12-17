import base64

from userapp.api.tests.main import basic_auth_client as client, user_auth_client as user_client, api_client, admin_user, project_factory, user_factory, user

class TestSecurity:

    def test_unauthenticated_request(self, api_client, admin_user):
        """Test getting users from the database"""

        response = api_client.get("/me")

        assert response.status_code == 401


    def test_login(self, api_client, admin_user):
        """Test logging in to get a token"""

        response = api_client.post(
            "/login",
            json={
                "username": admin_user['username'],
                "password": admin_user['password']
            }
        )

        assert response.status_code == 200
        assert "login_token" in response.cookies


    def test_login_and_request(self, api_client, admin_user):
        """Test logging in to get a token and using it to make an authenticated request"""

        response = api_client.post(
            "/login",
            json={
                "username": admin_user['username'],
                "password": admin_user['password']
            }
        )

        assert response.status_code == 200
        assert "login_token" in response.cookies

        # Use the token to make an authenticated request
        response = api_client.get("/me", cookies=response.cookies)

        assert response.status_code == 200
        data = response.json()
        assert data['username'] == admin_user['username']


    def test_logout(self, api_client, admin_user):
        """Test logging in to get a token and then logging out"""

        response = api_client.post(
            "/login",
            json={
                "username": admin_user['username'],
                "password": admin_user['password']
            }
        )

        assert response.status_code == 200
        assert "login_token" in response.cookies

        # Logout
        response = api_client.post("/logout", cookies=response.cookies)

        assert response.status_code == 200

        # Try to make an authenticated request
        response = api_client.get("/me", cookies=response.cookies)

        assert response.status_code == 401

    def test_invalid_login(self, api_client):
        """Test logging in with invalid credentials"""

        response = api_client.post(
            "/login",
            json={
                "username": "nonexistentuser",
                "password": "wrongpassword"
            }
        )

        assert response.status_code == 404


    def test_csrf_protected(self, api_client, admin_user):
        """Test that CSRF protection is working"""

        response = api_client.post(
            "/login",
            json={
                "username": admin_user['username'],
                "password": admin_user['password']
            }
        )

        assert response.status_code == 200
        assert "login_token" in response.cookies
        assert "csrf_token" in response.cookies

        # Attempt to make an authenticated request without CSRF token
        response = api_client.post(
            "/me",
            cookies={
                "login_token": response.cookies["login_token"]
            },
            headers={"X-CSRF-Token": response.cookies["csrf_token"]}
        )

        assert response.status_code == 200


    def test_csrf_protection_missing_token(self, api_client, admin_user):
        """Test that CSRF protection blocks requests without a CSRF token"""

        response = api_client.post(
            "/login",
            json={
                "username": admin_user['username'],
                "password": admin_user['password']
            }
        )

        assert response.status_code == 200
        assert "login_token" in response.cookies

        # Attempt to make an authenticated request without CSRF token
        response = api_client.post(
            "/me",
            cookies={
                "login_token": response.cookies["login_token"]
            }
        )

        assert response.status_code == 403


    def test_basic_authentication(self, api_client, admin_user):
        """Test basic authentication"""

        credentials = f"{admin_user['username']}:{admin_user['password']}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        response = api_client.get(
            "/me",
            headers={
                "Authorization": f"Basic {encoded_credentials}"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data['username'] == admin_user['username']


    def test_basic_authentication_invalid(self, api_client):
        """Test basic authentication with invalid credentials"""

        credentials = "nonexistentuser:wrongpassword"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        response = api_client.get(
            "/me",
            headers={
                "Authorization": f"Basic {encoded_credentials}"
            }
        )
        assert response.status_code == 404


    def test_new_user_login(self, client, user_factory, project_factory):
        """Test logging in with a newly created user"""

        project = project_factory()
        user = user_factory(1, project['id'])

        response = client.post(
            "/login",
            json={
                "username": user['username'],
                "password": user['password']
            }
        )

        assert response.status_code == 200
        assert "login_token" in response.cookies

    def test_user_client_access(self, user, user_client):
        """Test that a user client can access protected endpoints"""

        response = user_client.get("/me")

        assert response.status_code == 200
        data = response.json()
        assert data['username'] == user['username']

    def test_hash_password(self):
        """Test that password hashing and verification works correctly"""

        from userapp.api.routes.security import create_password_hash, verify_password

        password = "password"
        hashed_password = create_password_hash(password)

        assert verify_password(password, hashed_password) is True
        assert verify_password("WrongPassword", hashed_password) is False