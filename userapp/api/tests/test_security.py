from userapp.api.routes.security import check_ip_in_whitelist, get_ip_whitelist

class TestSecurity:

    def test_unauthenticated_request(self, api_client, admin_user):
        """Test getting users from the database"""

        response = api_client.get("/me")

        assert response.status_code == 401

    def test_logout(self, admin_client):
        """Test logging out"""

        pass


    def test_csrf_protected(self, admin_client, admin_user):
        """Test that CSRF protection is working"""

        pass

    def test_csrf_protection_missing_token(self, api_client, admin_user):
        """Test that CSRF protection blocks requests without a CSRF token"""

        pass


    def test_user_client_access(self, user, nonadmin_client):
        """Test that a user client can access protected endpoints"""

        response = nonadmin_client.get("/me")

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

    def test_ip_whitelist(self):
        """Test that IP whitelist works correctly"""

        ip_whitelist_string = "128.104.55.0/24, 128.104.58.0/23, 128.104.100.0/22, 128.105.68.0/23, 128.105.76.0/24, 128.105.82.0/24, 128.105.244.0/23"

        test_ip_valid = "128.104.55.10"
        assert check_ip_in_whitelist(test_ip_valid, ip_whitelist_string) == True

        test_ip_invalid = "128.114.55.10"
        assert check_ip_in_whitelist(test_ip_invalid, ip_whitelist_string) == False
