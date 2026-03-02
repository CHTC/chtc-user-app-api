import random


class TestNotes:

    def test_add_note_with_author(self, admin_client, admin_user, filled_out_project):
        """Test that creating a note returns a proper UserGet object for author"""

        note_data = {
            "ticket": f"TKT{random.randint(1000, 9999)}",
            "note": "Testing note author format.",
            "users": [u["id"] for u in filled_out_project["users"]],
        }

        response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert response.status_code == 201, f"Adding a note should return a 201 status code. Got {response.content} instead."

        data = response.json()
        author = data["author"]

        assert author is not None, "author should not be null"
        assert author["id"] == admin_user["id"], "The returned author id does not match the authenticated user"
        assert author["name"] == admin_user["name"], "The returned author name does not match"
        assert author["netid"] == admin_user["netid"], "The returned author netid does not match"
        assert author["is_admin"] == admin_user["is_admin"], "The returned author is_admin does not match"

    def test_get_note_with_author(self, admin_client, admin_user, filled_out_project):
        """Test that getting a note returns a proper UserGet object for author"""

        note_data = {
            "ticket": f"TKT{random.randint(1000, 9999)}",
            "note": "Testing note GET author format.",
            "users": [u["id"] for u in filled_out_project["users"]],
        }

        create_response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert create_response.status_code == 201, f"Creating a note should return 201, got {create_response.text}"
        note_id = create_response.json()["id"]

        get_response = admin_client.get(
            f"/projects/{filled_out_project['id']}/notes/{note_id}"
        )
        assert get_response.status_code == 200, f"Getting a note should return 200, got {get_response.text}"

        data = get_response.json()
        author = data["author"]

        assert author is not None, "author should not be null"
        assert author["id"] == admin_user["id"], "The returned author id does not match the authenticated user"
        assert author["name"] == admin_user["name"], "The returned author name does not match"
        assert author["netid"] == admin_user["netid"], "The returned author netid does not match"
        assert author["is_admin"] == admin_user["is_admin"], "The returned author is_admin does not match"

    def test_update_note_with_author(self, admin_client, admin_user, filled_out_project):
        """Test that updating a note returns a proper UserGet object for author"""

        note_data = {
            "ticket": f"TKT{random.randint(1000, 9999)}",
            "note": "Original note content.",
            "users": [u["id"] for u in filled_out_project["users"]],
        }

        create_response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert create_response.status_code == 201, f"Creating a note should return 201, got {create_response.text}"
        note_id = create_response.json()["id"]

        update_response = admin_client.put(
            f"/projects/{filled_out_project['id']}/notes/{note_id}",
            json={**note_data, "note": "Updated note content."},
        )
        assert update_response.status_code == 200, f"Updating a note should return 200, got {update_response.text}"

        data = update_response.json()
        author = data["author"]

        assert author is not None, "author should not be null"
        assert author["id"] == admin_user["id"], "The returned author id does not match the authenticated user"
        assert author["name"] == admin_user["name"], "The returned author name does not match"
        assert author["netid"] == admin_user["netid"], "The returned author netid does not match"
        assert author["is_admin"] == admin_user["is_admin"], "The returned author is_admin does not match"
