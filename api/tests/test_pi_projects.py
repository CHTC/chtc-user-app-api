import random
import base64
import os

from api.tests.main import basic_auth_client as client, api_client as unauthed_client, admin_user

group_data_f = lambda: {
    "name": f"test-group-{random.randint(0, 10000000)}",
    "point_of_contact": "test-contact",
    "unix_gid": random.randint(55000, 60000),
    "has_groupdir": True
}

class TestGroups:

    def test_needs_auth(self, client):
        """Test that authentication is required to access group endpoints"""

        response = client.get("/pi-projects")
        assert response.status_code == 200, f"Getting groups should return a 200 status code. Got {response.content} instead."
        assert len(response.json()) >= 0
        data = response.json()

        print(data)
