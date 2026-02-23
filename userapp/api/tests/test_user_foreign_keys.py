from userapp.api.tests.fake_data import project_data_f


USER_MIN_FIELDS = {"id", "name", "netid"}


def _assert_user_min(obj, expected_user, label):
    assert obj is not None, f"{label} should not be null"
    assert set(obj.keys()) == USER_MIN_FIELDS, (
        f"{label} should have exactly fields {USER_MIN_FIELDS}, got {set(obj.keys())}"
    )
    assert obj["id"] == expected_user["id"], f"{label} id does not match"
    assert obj["name"] == expected_user["name"], f"{label} name does not match"
    assert obj["netid"] == expected_user["netid"], f"{label} netid does not match"


class TestUserForeignKeys:

    def test_note_author_format(self, admin_client, filled_out_project, admin_user):
        """Getting a note returns an author field that is a proper UserMin object"""

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
        _assert_user_min(note["author"], admin_user, "note.author")

    def test_group_point_of_contact_format(self, admin_client, user):
        """Getting a group with a point_of_contact returns a proper UserMin object"""

        group_data = {
            "name": "test-group-poc-format",
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
        _assert_user_min(group["point_of_contact"], user, "group.point_of_contact")

    def test_project_staff_format(self, admin_client, user_factory, project_factory):
        """Getting a project with staff1/staff2 returns proper UserMin objects"""

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
        _assert_user_min(project_data["staff1"], staff1, "project.staff1")
        _assert_user_min(project_data["staff2"], staff2, "project.staff2")
