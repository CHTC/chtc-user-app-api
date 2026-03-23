import random

from userapp.api.tests.fake_data import project_data_f


def _assert_user(obj, expected_user, label):
    assert obj is not None, f"{label} should not be null"
    assert obj["id"] == expected_user["id"], f"{label} id does not match"
    assert obj["name"] == expected_user["name"], f"{label} name does not match"
    assert obj["netid"] == expected_user["netid"], f"{label} netid does not match"
    assert obj["email1"] == expected_user["email1"], f"{label} email1 does not match"
    assert obj["email2"] == expected_user["email2"], f"{label} email2 does not match"
    assert obj["phone1"] == expected_user["phone1"], f"{label} phone1 does not match"
    assert obj["phone2"] == expected_user["phone2"], f"{label} phone2 does not match"
    assert obj["is_admin"] == expected_user["is_admin"], f"{label} is_admin does not match"


class TestUserForeignKeys:

    def test_note_author_format(self, admin_client, filled_out_project, admin_user):
        """Getting a note returns an author field"""

        note_data = {
            "ticket": "TICKET01",
            "note": "Testing note author format.",
            "users": [u["id"] for u in filled_out_project["users"]],
        }
        create_response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert create_response.status_code == 201, (
            f"Creating a note should return 201, got {create_response.text}"
        )
        created_note = create_response.json()

        get_response = admin_client.get(
            f"/projects/{filled_out_project['id']}/notes/{created_note['id']}"
        )
        assert get_response.status_code == 200, (
            f"Getting a note should return 200, got {get_response.text}"
        )

        note = get_response.json()
        _assert_user(note["author"], admin_user, "note.author")

    def test_group_point_of_contact_format(self, admin_client, user):
        """Getting a group with a point_of_contact returns a proper UserGet object"""

        group_data = {
            "name": f"test-group-poc-format-{random.randint(1, 10000)}",
            "point_of_contact": user["id"],
            "has_groupdir": False,
        }
        create_response = admin_client.post("/groups", json=group_data)
        assert create_response.status_code == 201, (
            f"Creating a group should return 201, got {create_response.text}"
        )
        group_id = create_response.json()["id"]

        get_response = admin_client.get(f"/groups/{group_id}")
        assert get_response.status_code == 200, (
            f"Getting a group should return 200, got {get_response.text}"
        )

        group = get_response.json()
        _assert_user(group["point_of_contact"], user, "group.point_of_contact")

    def test_project_staff_format(self, admin_client, user_factory, project_factory):
        """Getting a project with staff1/staff2 returns proper UserGet objects"""

        project = project_factory()
        staff1 = user_factory(0, project["id"])
        staff2 = user_factory(1, project["id"])

        project_data = project_data_f(staff1=staff1["id"], staff2=staff2["id"])
        create_response = admin_client.post("/projects", json=project_data)
        assert create_response.status_code == 201, (
            f"Creating a project should return 201, got {create_response.text}"
        )
        project_id = create_response.json()["id"]

        get_response = admin_client.get(f"/projects/{project_id}")
        assert get_response.status_code == 200, (
            f"Getting a project should return 200, got {get_response.text}"
        )

        project_data = get_response.json()
        _assert_user(project_data["staff1"], staff1, "project.staff1")
        _assert_user(project_data["staff2"], staff2, "project.staff2")

    def test_update_note_author_format(self, admin_client, filled_out_project, admin_user):
        """Updating a note returns an author field with a proper UserGet object"""

        note_data = {
            "ticket": "TICKET02",
            "note": "Original note content.",
            "users": [u["id"] for u in filled_out_project["users"]],
        }
        create_response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert create_response.status_code == 201, (
            f"Creating a note should return 201, got {create_response.text}"
        )
        note_id = create_response.json()["id"]

        updated_note_data = {
            "ticket": "TICKET02",
            "note": "Updated note content.",
            "users": [u["id"] for u in filled_out_project["users"]],
        }
        update_response = admin_client.put(
            f"/projects/{filled_out_project['id']}/notes/{note_id}",
            json=updated_note_data,
        )
        assert update_response.status_code == 200, (
            f"Updating a note should return 200, got {update_response.text}"
        )

        note = update_response.json()
        assert note["note"] == updated_note_data["note"], "Updated note content does not match"
        _assert_user(note["author"], admin_user, "note.author")

    def test_update_group_point_of_contact_format(self, admin_client, user_factory, project_factory):
        """Updating a group's point_of_contact returns a proper UserGet object"""

        project = project_factory()
        original_poc = user_factory(0, project["id"])
        new_poc = user_factory(1, project["id"])

        group_data = {
            "name": f"test-group-poc-update-{random.randint(1, 10000)}",
            "point_of_contact": original_poc["id"],
            "has_groupdir": False,
        }
        create_response = admin_client.post("/groups", json=group_data)
        assert create_response.status_code == 201, (
            f"Creating a group should return 201, got {create_response.text}"
        )
        group_id = create_response.json()["id"]

        update_response = admin_client.put(
            f"/groups/{group_id}",
            json={"point_of_contact": new_poc["id"]},
        )
        assert update_response.status_code == 200, (
            f"Updating a group should return 200, got {update_response.text}"
        )

        group = update_response.json()
        _assert_user(group["point_of_contact"], new_poc, "group.point_of_contact")

    def test_update_project_staff_format(self, admin_client, user_factory, project_factory):
        """Updating a project's staff1/staff2 returns proper UserGet objects"""

        project = project_factory()
        original_staff1 = user_factory(0, project["id"])
        original_staff2 = user_factory(1, project["id"])
        new_staff1 = user_factory(2, project["id"])
        new_staff2 = user_factory(3, project["id"])

        project_data = project_data_f(staff1=original_staff1["id"], staff2=original_staff2["id"])
        create_response = admin_client.post("/projects", json=project_data)
        assert create_response.status_code == 201, (
            f"Creating a project should return 201, got {create_response.text}"
        )
        project_id = create_response.json()["id"]

        update_response = admin_client.put(
            f"/projects/{project_id}",
            json={"staff1": new_staff1["id"], "staff2": new_staff2["id"]},
        )
        assert update_response.status_code == 200, (
            f"Updating a project should return 200, got {update_response.text}"
        )

        updated_project = update_response.json()
        _assert_user(updated_project["staff1"], new_staff1, "project.staff1")
        _assert_user(updated_project["staff2"], new_staff2, "project.staff2")
