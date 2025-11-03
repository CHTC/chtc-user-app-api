import random
import base64
import os

from api.tests.main import basic_auth_client as client, admin_user

class TestListing:

    def test_listing_default(self, client):
        """Test getting object lists from the database with default parameters"""

        response = client.get("/groups")

        assert response.status_code == 200

        data = response.json()

        assert isinstance(data, list)
        assert len(data) > 0

    def test_listing_with_pagination(self, client):
        """Test getting object lists from the database with pagination parameters"""

        response0 = client.get("/groups?page=0&page_size=1")
        response1 = client.get("/groups?page=1&page_size=1")

        assert set(g['id'] for g in response0.json()) != set(g['id'] for g in response1.json()), "Pagination is not working correctly, page 0 and page 1 returned the same data"

    def test_listing_with_invalid_pagination(self, client):
        """Test getting object lists from the database with invalid pagination parameters"""

        response = client.get("/groups?page=-1&page_size=1")

        assert response.status_code == 400, "Invalid pagination parameters should return a 400 status code"

        response = client.get("/groups?page=0&page_size=-1")

        assert response.status_code == 400, "Invalid pagination parameters should return a 400 status code"

    def test_filtering(self, client):
        """Test filtering object lists from the database"""

        # Assuming there is a group with name 'admin'
        response = client.get("/groups?name=eq.admin")

        assert response.status_code == 200

        data = response.json()

        assert all(g['name'] == 'admin' for g in data), "Filtering by name did not return the expected results"

    def test_ordering(self, client):
        """Test ordering object lists from the database"""

        response = client.get("/groups?name=order_by.asc&page_size=10")

        assert response.status_code == 200

        data = response.json()

        names = [g['name'] for g in data]

        assert names == sorted(names, key=lambda x: x.lower()), "Ordering by name ascending did not return the expected results"

class TestGetOne:

    def test_get_one(self, client):
        """Test getting a single existing group from the database"""

        # First, get a list of groups to find a valid ID
        list_response = client.get("/groups")

        assert list_response.status_code == 200

        data = list_response.json()

        assert len(data) > 0, "No groups found in the database to test getting a single group"

        group_id = data[0]['id']

        # Now, get the single group by ID
        response = client.get(f"/groups/{group_id}")

        assert response.status_code == 200

        group_data = response.json()

        assert group_data['id'] == group_id, "The returned group ID does not match the requested ID"

class TestUpdateOne:

    def test_update_one(self, client):
        """Test updating a single existing group in the database"""

        # First, get a list of groups to find a valid ID
        list_response = client.get("/groups")

        assert list_response.status_code == 200

        data = list_response.json()

        assert len(data) > 0, "No groups found in the database to test updating a single group"

        group_id = data[0]['id']

        # Now, update the single group by ID
        update_data = {
            "name": f"updated-group-{random.randint(1000, 9999)}"
        }

        response = client.put(f"/groups/{group_id}", json=update_data)

        assert response.status_code == 200

        updated_group_data = response.json()

        assert updated_group_data['id'] == group_id, "The returned group ID does not match the requested ID"
        assert updated_group_data['name'] == update_data['name'], "The group name was not updated correctly"