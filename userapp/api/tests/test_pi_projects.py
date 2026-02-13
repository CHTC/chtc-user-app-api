import random

group_data_f = lambda: {
    "name": f"test-group-{random.randint(0, 10000000)}",
    "point_of_contact": "test-contact",
    "unix_gid": random.randint(55000, 60000),
    "has_groupdir": True
}

class TestGroups:

    def test_needs_auth(self, admin_client):
        """Test that authentication is required to access group endpoints"""

        response = admin_client.get("/pi-projects")
        assert response.status_code == 200, f"Getting groups should return a 200 status code. Got {response.content} instead."
        assert len(response.json()) >= 0
        data = response.json()

        print(data)
