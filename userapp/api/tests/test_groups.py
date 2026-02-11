import random

group_data_f = lambda: {
    "name": f"test-group-{random.randint(0, 10000000)}",
    "point_of_contact": "test-contact",
    "unix_gid": random.randint(55000, 60000),
    "has_groupdir": True
}

class TestGroups:

    def test_needs_auth(self, nonadmin_client):
        """Test that authentication is required to access group endpoints"""

        response = nonadmin_client.get("/groups")
        assert response.status_code == 403, f"Getting groups without authentication should return a 401 status code. Got {response.content} instead."

        group_data = group_data_f()
        response = nonadmin_client.post(
            "/groups",
            json=group_data,
        )
        assert response.status_code == 403, f"Adding a group without authentication should return a 401 status code. Got {response.content} instead."

    def test_get_groups(self, admin_client):
        """Test getting groups from the database"""

        response = admin_client.get("/groups")

        assert response.status_code == 200, f"Getting groups should return a 200 status code. Got {response.content} instead."

        data = response.json()

        assert isinstance(data, list), f"Getting groups should return a list. Got {response.content} instead."

    def test_add_group(self, admin_client):
        """Test adding a group to the database"""

        group_data = group_data_f()

        response = admin_client.post(
            "/groups",
            json=group_data,
        )

        assert response.status_code == 201, f"Adding a group should return a 200 status code. Got {response.content} instead."

        data = response.json()

        assert data['name'] == group_data['name'], f"The returned group name does not match the input. Got {response.content} instead."
        assert data['point_of_contact'] == group_data['point_of_contact'], f"The returned point_of_contact does not match the input. Got {response.content} instead."
        assert data['unix_gid'] == group_data['unix_gid'], f"The returned unix_gid does not match the input. Got {response.content} instead."
        assert data['has_groupdir'] == group_data['has_groupdir'], f"The returned has_groupdir does not match the input. Got {response.content} instead."

    def test_add_invalid_group_name_spaces(self, admin_client):
        """Test adding a group with an invalid name"""

        group_data = group_data_f()

        new_group_data = {
            **group_data,
            "name": "invalid group name with spaces!"
        }

        response = admin_client.post(
            "/groups",
            json=new_group_data,
        )

        assert response.status_code == 422, f"Adding a group with an invalid name should return a 400 status code. Got {response.content} instead."

    def test_add_invalid_group_name_special_chars(self, admin_client):
        """Test adding a group with an invalid name"""

        group_data = group_data_f()

        new_group_data = {
            **group_data,
            "name": "invalid@group#name$"
        }

        response = admin_client.post(
            "/groups",
            json=new_group_data,
        )

        assert response.status_code == 422, f"Adding a group with an invalid name should return a 400 status code. Got {response.content} instead."

    def test_add_invalid_group_name_too_long(self, admin_client):
        """Test adding a group with an invalid name"""

        group_data = group_data_f()

        new_group_data = {
            **group_data,
            "name": "a" * 33
        }

        response = admin_client.post(
            "/groups",
            json=new_group_data,
        )

        assert response.status_code == 422, f"Adding a group with an invalid name should return a 400 status code. Got {response.content} instead."

    def test_add_duplicate_gid(self, admin_client):
        """Test adding a group with a duplicate unix_gid"""

        group_data = group_data_f()

        group_response = admin_client.get(
            "/groups?page_size=1"
        )
        group = group_response.json()[0]

        # Now, try to add another group with the same unix_gid
        new_group_data = {
            **group_data,
            "unix_gid": group['unix_gid']
        }

        response = admin_client.post(
            "/groups",
            json=new_group_data,
        )

        assert response.status_code == 400, f"Adding a group with a duplicate unix_gid should return a 400 status code. Got {response.content} instead."

    def test_add_colliding_uid_gid(self, admin_client):
        """Test adding a group with a colliding unix_gid with an existing user"""

        group_data = group_data_f()

        user_response = admin_client.get("/users?page_size=1")
        user = user_response.json()[0]

        new_group_data = {
            **group_data,
            "unix_gid": user['unix_uid']
        }

        response = admin_client.post(
            "/groups",
            json=new_group_data,
        )

        assert response.status_code == 400, f"Adding a group with a colliding unix_gid with an existing user should return a 400 status code. Got {response.content} instead."

    def test_automatic_allocation_of_gid(self, admin_client):
        """Test adding a group without specifying a unix_gid to check automatic allocation"""

        group_data = group_data_f()

        new_group_data = {**group_data}
        new_group_data.pop('unix_gid', None)

        response = admin_client.post(
            "/groups",
            json=new_group_data,
        )

        assert response.status_code == 201, f"Adding a group without unix_gid should return a 200 status code. Got {response.content} instead."

        data = response.json()

        assert 'unix_gid' in data, f"The returned group should have an automatically allocated unix_gid. Got {response.content} instead."
        assert isinstance(data['unix_gid'], int), f"The automatically allocated unix_gid should be an integer. Got {response.content} instead."

    def test_update_groups_with_bad_data(self, admin_client):
        group_response = admin_client.get(
            "/groups?page_size=1"
        )
        group = group_response.json()[0]
        group_id = group.pop('id')

        # Now, try to add another group with the same unix_gid
        new_group_data = {
            **group,
            "unix_gid": 600001
        }

        response = admin_client.put(
            f"/groups/{group_id}",
            json=new_group_data,
        )

        assert response.status_code == 400, f"Updating a group with a out of bounds unix_gid should return a 400 status code. Got {response.content} instead."

    def test_add_delete_user_to_group(self, admin_client, admin_user):
        """Test adding and deleting a user to/from a group"""

        user_response = admin_client.get(
            "/users?page_size=1"
        )
        user = user_response.json()[0]
        user_id = user.pop('id')

        group_response = admin_client.get(
            "/groups?page_size=1"
        )
        group = group_response.json()[0]
        group_id = group.pop('id')

        # Add user to group
        response = admin_client.post(
            f"/groups/{group_id}/users",
            json={
                "id": user_id
            }
        )
        assert response.status_code == 201, f"Adding a user to a group should return a 200 status code. Got {response.content} instead."

        # Now, delete the user from the group
        response = admin_client.delete(
            f"/groups/{group_id}/users/{user_id}"
        )
        assert response.status_code == 204, f"Deleting a user from a group should return a 204 status code. Got {response.content} instead."


    def test_get_group_users(self, admin_client):
        """Test getting users associated with a group"""

        user_response = admin_client.get(
            "/users?page_size=1000"
        )
        user = user_response.json()[0]
        user_id = user.pop('id')

        group_response = admin_client.get(
            "/groups?page_size=1000"
        )
        group = group_response.json()[0]
        group_id = group.pop('id')

        # Add user to group
        response = admin_client.post(
            f"/groups/{group_id}/users",
            json={
                "id": user_id
            }
        )
        assert response.status_code == 201, f"Adding a user to a group should return a 200 status code. Got {response.content} instead."

        response = admin_client.get(
            f"/groups/{group_id}/users"
        )
        assert response.status_code == 200, f"Getting users for a group should return a 200 status code. Got {response.content} instead."

        # Clean up by removing the user from the group, not essential for the test
        response = admin_client.delete(
            f"/groups/{group_id}/users/{user_id}"
        )
        assert response.status_code == 204, f"Deleting a user from a group should return a 204 status code. Got {response.content} instead."


    def test_remove_nonexistent_user_from_group(self, admin_client):
        """Test removing a user who is not associated with the group"""

        group_response = admin_client.get(
            "/groups?page_size=1"
        )
        group = group_response.json()[0]
        group_id = group.pop('id')

        # Attempt to remove a user with a high ID that likely doesn't exist
        response = admin_client.delete(
            f"/groups/{group_id}/users/9999999"
        )
        assert response.status_code == 404, f"Removing a non-associated user should return a 404 status code. Got {response.content} instead."


    def test_remove_user_from_group(self, admin_client):
        """Test removing a user from a group"""

        user_response = admin_client.get(
            "/users"
        )
        user = user_response.json()[0]
        user_id = user.pop('id')

        group_response = admin_client.get(
            "/groups"
        )
        group = group_response.json()[0]
        group_id = group.pop('id')

        # Add user to group
        response = admin_client.post(
            f"/groups/{group_id}/users",
            json={
                "id": user_id
            }
        )
        assert response.status_code == 201, f"Adding a user to a group should return a 200 status code. Got {response.content} instead."

        # Now, delete the user from the group
        response = admin_client.delete(
            f"/groups/{group_id}/users/{user_id}"
        )
        assert response.status_code == 204, f"Deleting a user from a group should return a 204 status code. Got {response.content} instead."

    def test_delete_group(self, admin_client):
        """Test deleting a group from the database"""

        group_data = group_data_f()

        # First, add a new group to ensure we have one to delete
        response = admin_client.post(
            "/groups",
            json=group_data,
        )

        assert response.status_code == 201, f"Adding a group should return a 200 status code. Got {response.content} instead"

        data = response.json()
        group_id = data['id']

        # Now, delete the group
        response = admin_client.delete(
            f"/groups/{group_id}"
        )

        assert response.status_code == 204, "Deleting a group should return a 200 status code"

        # Verify the group has been deleted
        response = admin_client.get(
            f"/groups/{group_id}"
        )

        assert response.status_code == 404, "Getting a deleted group should return a 404 status code"
