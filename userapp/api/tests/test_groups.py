import random

from userapp.core.models.enum import EntityManagerEnum

group_data_f = lambda: {
    "name": f"test-group-{random.randint(0, 10000000)}",
    "unix_gid": random.randint(55000, 60000),
    "description": "A test group",
}

class TestGroups:

    def test_needs_auth(self, api_client):
        """Anonymous callers are turned away from the group endpoints"""

        response = api_client.get("/groups")
        assert response.status_code == 403, f"Getting groups without authentication should return a 403 status code. Got {response.content} instead."

        response = api_client.post("/groups", json=group_data_f())
        assert response.status_code == 403, f"Adding a group without authentication should return a 403 status code. Got {response.content} instead."

    def test_nonadmin_cannot_create_group(self, nonadmin_client):
        response = nonadmin_client.post("/groups", json=group_data_f())
        assert response.status_code == 403, f"Adding a group as a non-admin should return a 403 status code. Got {response.content} instead."

    def test_nonadmin_lists_only_administrable_groups(self, nonadmin_client, admin_client):
        """A non-staff user with no owned groups sees an empty list, not a 403"""

        response = nonadmin_client.get("/groups")
        assert response.status_code == 200, f"Getting groups as a non-admin should return a 200 status code. Got {response.content} instead."
        assert response.json() == []

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

        assert response.status_code == 201, f"Adding a group should return a 201 status code. Got {response.content} instead."

        data = response.json()

        assert data['name'] == group_data['name'], f"The returned group name does not match the input. Got {response.content} instead."
        assert data['unix_gid'] == group_data['unix_gid'], f"The returned unix_gid does not match the input. Got {response.content} instead."
        assert data['description'] == group_data['description'], f"The returned description does not match the input. Got {response.content} instead."
        assert data['owner_group_id'] is None, "A group created without an owner is staff-only"
        assert data['deleted_at'] is None
        assert data['created_at'] and data['updated_at']
        assert 'has_groupdir' not in data and 'point_of_contact' not in data, "The removed columns should not be returned"

    def test_add_invalid_group_name_spaces(self, admin_client):
        """Test adding a group with an invalid name"""

        new_group_data = {**group_data_f(), "name": "invalid group name with spaces!"}

        response = admin_client.post("/groups", json=new_group_data)

        assert response.status_code == 422, f"Adding a group with an invalid name should return a 422 status code. Got {response.content} instead."

    def test_add_invalid_group_name_special_chars(self, admin_client):
        """Test adding a group with an invalid name"""

        new_group_data = {**group_data_f(), "name": "invalid@group#name$"}

        response = admin_client.post("/groups", json=new_group_data)

        assert response.status_code == 422, f"Adding a group with an invalid name should return a 422 status code. Got {response.content} instead."

    def test_add_invalid_group_name_too_long(self, admin_client):
        """Test adding a group with an invalid name"""

        new_group_data = {**group_data_f(), "name": "a" * 33}

        response = admin_client.post("/groups", json=new_group_data)

        assert response.status_code == 422, f"Adding a group with an invalid name should return a 422 status code. Got {response.content} instead."

    def test_add_duplicate_name(self, admin_client, group):
        response = admin_client.post("/groups", json={**group_data_f(), "name": group['name']})
        assert response.status_code == 400, f"Adding a group with a duplicate name should return a 400 status code. Got {response.content} instead."

    def test_add_duplicate_gid(self, admin_client):
        """Test adding a group with a duplicate unix_gid"""

        # Group 1 is seeded with a unix_gid by conftest
        group = admin_client.get("/groups/1").json()

        response = admin_client.post(
            "/groups",
            json={**group_data_f(), "unix_gid": group['unix_gid']},
        )

        assert response.status_code == 400, f"Adding a group with a duplicate unix_gid should return a 400 status code. Got {response.content} instead."

    def test_add_colliding_uid_gid(self, admin_client):
        """Test adding a group with a colliding unix_gid with an existing user"""

        user = admin_client.get("/users?page_size=1").json()[0]

        response = admin_client.post(
            "/groups",
            json={**group_data_f(), "unix_gid": user['unix_uid']},
        )

        assert response.status_code == 400, f"Adding a group with a colliding unix_gid with an existing user should return a 400 status code. Got {response.content} instead."

    def test_no_automatic_gid(self, admin_client):
        """A null unix_gid means the group is not a unix group, so none is allocated"""

        group_data = group_data_f()
        group_data.pop('unix_gid')

        response = admin_client.post("/groups", json=group_data)

        assert response.status_code == 201, f"Adding a group without unix_gid should return a 201 status code. Got {response.content} instead."
        assert response.json()['unix_gid'] is None

    def test_update_groups_with_bad_data(self, admin_client, group):
        response = admin_client.put(f"/groups/{group['id']}", json={"unix_gid": 600001})

        assert response.status_code == 400, f"Updating a group with a out of bounds unix_gid should return a 400 status code. Got {response.content} instead."

    def test_update_group_rejects_taken_name_colliding_gid_and_null_managed_by(self, admin_client, group, group_factory):
        other = group_factory()
        assert admin_client.put(f"/groups/{group['id']}", json={"name": other['name']}).status_code == 400

        user = admin_client.get("/users?page_size=1").json()[0]
        assert admin_client.put(f"/groups/{group['id']}", json={"unix_gid": user['unix_uid']}).status_code == 400

        response = admin_client.put(f"/groups/{group['id']}", json={"managed_by": None})
        assert response.status_code == 400 and "managed_by" in response.json()['detail']

        unchanged = admin_client.get(f"/groups/{group['id']}").json()
        assert unchanged['name'] == group['name'] and unchanged['unix_gid'] == group['unix_gid']
        assert unchanged['managed_by'] == EntityManagerEnum.APPLICATION.value

    def test_update_group(self, admin_client, group):
        response = admin_client.put(
            f"/groups/{group['id']}",
            json={"description": "new words", "name": f"renamed-{random.randint(0, 10**7)}"},
        )
        assert response.status_code == 200, f"Updating a group should return 200. Got {response.content} instead."
        data = response.json()
        assert data['description'] == "new words"
        assert data['name'].startswith("renamed-")

    def test_get_group_not_found(self, admin_client):
        response = admin_client.get("/groups/99999999")
        assert response.status_code == 404

    def test_add_delete_user_to_group(self, admin_client, group, user):
        """Test adding and deleting a user to/from a group"""

        response = admin_client.post(f"/groups/{group['id']}/members", json={"user_id": user['id']})
        assert response.status_code == 201, f"Adding a user to a group should return a 201 status code. Got {response.content} instead."
        assert response.json()['member_user']['id'] == user['id']
        assert response.json()['member_group'] is None

        response = admin_client.delete(f"/groups/{group['id']}/members/users/{user['id']}")
        assert response.status_code == 204, f"Deleting a user from a group should return a 204 status code. Got {response.content} instead."

    def test_add_member_twice_conflicts(self, admin_client, group, user, group_member):
        group_member(group['id'], user_id=user['id'])

        response = admin_client.post(f"/groups/{group['id']}/members", json={"user_id": user['id']})
        assert response.status_code == 409, f"Adding an existing member should return a 409 status code. Got {response.content} instead."

    def test_add_member_requires_exactly_one_of_user_or_group(self, admin_client, group, user):
        response = admin_client.post(f"/groups/{group['id']}/members", json={})
        assert response.status_code == 422

        response = admin_client.post(f"/groups/{group['id']}/members", json={"user_id": user['id'], "group_id": group['id']})
        assert response.status_code == 422

    def test_add_nonexistent_user_to_group(self, admin_client, group):
        response = admin_client.post(f"/groups/{group['id']}/members", json={"user_id": 9999999})
        assert response.status_code == 404

    def test_get_group_users(self, admin_client, group, user, group_member):
        """Test getting users with access through a group"""

        group_member(group['id'], user_id=user['id'])

        response = admin_client.get(f"/groups/{group['id']}/members")
        assert response.status_code == 200, f"Getting members for a group should return a 200 status code. Got {response.content} instead."

        members = response.json()
        assert [m['user_id'] for m in members] == [user['id']]
        assert members[0]['direct'] is True
        assert members[0]['paths'] == [[group['id']]]
        assert members[0]['path_names'] == [[group['name']]]

        response = admin_client.get(f"/groups/{group['id']}/direct_members")
        assert response.status_code == 200
        direct = response.json()
        assert len(direct) == 1
        assert direct[0]['member_user']['id'] == user['id']
        assert direct[0]['group_id'] == group['id']

    def test_group_members_filter(self, admin_client, group, user, group_member):
        group_member(group['id'], user_id=user['id'])

        response = admin_client.get(f"/groups/{group['id']}/members?user_id=eq.{user['id']}")
        assert response.status_code == 200
        assert len(response.json()) == 1

        response = admin_client.get(f"/groups/{group['id']}/members?user_id=eq.99999999")
        assert response.status_code == 200
        assert response.json() == []

    def test_remove_nonexistent_user_from_group(self, admin_client, group):
        """Test removing a user who is not associated with the group"""

        response = admin_client.delete(f"/groups/{group['id']}/members/users/9999999")
        assert response.status_code == 404, f"Removing a non-associated user should return a 404 status code. Got {response.content} instead."

    def test_memberships_carry_no_managed_by(self, admin_client, group, user):
        """managed_by is a property of the group; a membership row has none and ignores one that is sent"""

        response = admin_client.post(f"/groups/{group['id']}/members", json={"user_id": user['id'], "managed_by": "MANIFEST"})
        assert response.status_code == 201, f"Adding a user to a group should return 201, got {response.text}"
        assert 'managed_by' not in response.json()

        [matched] = [u for u in admin_client.get(f"/groups/{group['id']}/members").json() if u['user_id'] == user['id']]
        assert 'managed_by' not in matched
        assert admin_client.get(f"/groups/{group['id']}").json()['managed_by'] == EntityManagerEnum.APPLICATION.value

    def test_group_managed_by(self, admin_client, group_factory):
        """Staff set which system owns a group's membership, on creation or later"""

        group = group_factory(managed_by=EntityManagerEnum.MANIFEST.value)
        assert group['managed_by'] == EntityManagerEnum.MANIFEST.value

        response = admin_client.put(f"/groups/{group['id']}", json={"managed_by": EntityManagerEnum.MORGRIDGE_AD.value})
        assert response.status_code == 200, response.text
        assert response.json()['managed_by'] == EntityManagerEnum.MORGRIDGE_AD.value

        assert admin_client.put(f"/groups/{group['id']}", json={"managed_by": "NOT_A_SYSTEM"}).status_code == 422

    def test_removed_routes(self, admin_client, group, user):
        """The user-only membership routes were replaced by /members, and memberships have no managed_by to patch"""

        assert admin_client.get(f"/groups/{group['id']}/users").status_code in (404, 405)
        assert admin_client.patch(f"/users/{user['id']}/groups/{group['id']}", json={"managed_by": "MANIFEST"}).status_code in (404, 405)
        assert admin_client.patch(f"/groups/{group['id']}/members/users/{user['id']}", json={"managed_by": "MANIFEST"}).status_code in (404, 405)

    def test_delete_group(self, admin_client):
        """Test deleting a group from the database"""

        response = admin_client.post("/groups", json=group_data_f())
        assert response.status_code == 201, f"Adding a group should return a 201 status code. Got {response.content} instead"
        group_id = response.json()['id']

        response = admin_client.delete(f"/groups/{group_id}")
        assert response.status_code == 204, "Deleting a group should return a 204 status code"

        # Soft deleted: still readable by staff, with deleted_at set
        response = admin_client.get(f"/groups/{group_id}")
        assert response.status_code == 200
        assert response.json()['deleted_at'] is not None

        # ... but gone from the default listing
        listed = admin_client.get(f"/groups?id=eq.{group_id}").json()
        assert listed == []

        # Deleting twice is a 404
        assert admin_client.delete(f"/groups/{group_id}").status_code == 404

    def test_deleted_group_keeps_name_and_gid(self, admin_client):
        group_data = group_data_f()
        group_id = admin_client.post("/groups", json=group_data).json()['id']
        admin_client.delete(f"/groups/{group_id}")

        response = admin_client.post("/groups", json=group_data)
        assert response.status_code == 400, "A deleted group's name and unix_gid are never reused"


class TestUnixGidAllocation:
    """POST /groups/{id}/unix_gid hands out the lowest free gid, as the old insert trigger did"""

    def test_allocates_lowest_free_gid(self, existing_admin_client, group_factory):
        first = group_factory()
        second = group_factory()
        try:
            response = existing_admin_client.post(f"/groups/{first['id']}/unix_gid")
            assert response.status_code == 200, response.text
            gid = response.json()['unix_gid']
            assert 40000 <= gid <= 60000
            assert existing_admin_client.get(f"/groups/{first['id']}").json()['unix_gid'] == gid

            # Nothing in range below the allocated gid is free: every lower gid belongs to a group or a user
            lower_gids = {g['unix_gid'] for g in existing_admin_client.get(
                "/groups", params={"unix_gid": f"lt.{gid}", "include_deleted": "true", "page_size": 100000},
            ).json()}
            lower_uids = {u['unix_uid'] for u in existing_admin_client.get(
                "/users", params={"unix_uid": f"lt.{gid}", "page_size": 100000},
            ).json()}
            assert set(range(40000, gid)) <= lower_gids | lower_uids

            # The next group skips the gid just handed out
            next_gid = existing_admin_client.post(f"/groups/{second['id']}/unix_gid").json()['unix_gid']
            assert next_gid > gid

            entry = existing_admin_client.get("/audit_log", params={"group_id": f"eq.{first['id']}", "action": "eq.metadata_changed"}).json()[0]
            assert entry['details']['changes'] == {"unix_gid": {"old": None, "new": gid}}
        finally:
            existing_admin_client.delete(f"/groups/{first['id']}")
            existing_admin_client.delete(f"/groups/{second['id']}")

    def test_group_with_a_gid_is_refused(self, existing_admin_client, group_factory):
        group = group_factory(unix_gid=random.randint(55000, 60000))
        try:
            response = existing_admin_client.post(f"/groups/{group['id']}/unix_gid")
            assert response.status_code == 409
            assert existing_admin_client.get(f"/groups/{group['id']}").json()['unix_gid'] == group['unix_gid']
        finally:
            existing_admin_client.delete(f"/groups/{group['id']}")

    def test_nonadmin_cannot_allocate(self, nonadmin_client, group):
        assert nonadmin_client.post(f"/groups/{group['id']}/unix_gid").status_code == 403

    def test_unknown_group(self, existing_admin_client):
        assert existing_admin_client.post("/groups/999999999/unix_gid").status_code == 404
