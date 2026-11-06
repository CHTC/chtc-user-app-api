import random

import pytest

from userapp.core.models.enum import EntityManagerEnum
from userapp.api.tests.conftest import audit_rows
from userapp.api.tests.fake_data import project_data_f


class TestProjects:

    def test_get_projects(self, admin_client):
        """Test getting projects from the database"""

        response = admin_client.get("/projects")

        assert response.status_code == 200, "Getting projects should return a 200 status code"

        data = response.json()

        assert isinstance(data, list), "The returned data should be a list of projects"

    def test_add_note(self, admin_client, filled_out_project, admin_user):
        """Test adding a note to the database"""

        note_data = {
            "ticket": "TICKET13",
            "note": "This is a test note.",
            "users": [*map(lambda u: u['id'], filled_out_project['users'])]
        }

        response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )

        assert response.status_code == 201, f"Adding a note should return a 201 status code, not {response.text}"

        data = response.json()

        assert data['ticket'] == note_data['ticket'], "The returned ticket does not match the input"
        assert data['note'] == note_data['note'], "The returned note does not match the input"
        assert data['author']['id'] == admin_user['id'], "The returned author does not match the identity of the requester"
        assert data['author']['name'] == admin_user['name'], "The returned author name does not match"
        assert data['author']['netid'] == admin_user['netid'], "The returned author netid does not match"
        assert set(map(lambda x: x['id'], data['users'])) == set(note_data['users']), "The returned users do not match the input"

    def test_get_notes(self, admin_client, filled_out_project, admin_user):
        """Test getting notes from the database"""

        # Create the note
        note_data = {
            "ticket": "TICKET13",
            "note": "This is a test note.",
            "users": [*map(lambda u: u['id'], filled_out_project['users'])]
        }
        response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert response.status_code == 201, "Adding a note should return a 201 status code"

        # Get the note
        note_response = admin_client.get(
            f"/projects/{filled_out_project['id']}/notes",
        )
        assert note_response.status_code == 200, f"Getting notes should return a 200 status code instead got {note_response.text}"

        notes = note_response.json()
        assert len(notes) > 0, "There should be at least one note returned"

        # Check the notes data
        note = notes[0]
        assert note['ticket'] == note_data['ticket'], "The returned ticket does not match"
        assert note['note'] == note_data['note'], "The returned note does not match"
        assert note['author']['id'] == admin_user['id'], "The returned author does not match the identity of the requester"
        assert note['author']['name'] == admin_user['name'], "The returned author name does not match"
        assert note['author']['netid'] == admin_user['netid'], "The returned author netid does not match"
        assert note['author']['is_admin'] == admin_user['is_admin'], "The returned author is_admin does not match"
        assert set(map(lambda x: x['id'], note['users'])) == set(note_data['users']), "The returned users do not match"


    def test_get_single_note(self, admin_client, filled_out_project):
        """Test getting a single note by ID"""

        # Create the note
        note_data = {
            "ticket": "TICKET13",
            "note": "This is a test note.",
            "users": [*map(lambda u: u['id'], filled_out_project['users'])]
        }
        response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert response.status_code == 201, "Adding a note should return a 201 status code"
        created_note = response.json()

        # Get the note by ID
        note_response = admin_client.get(
            f"/projects/{filled_out_project['id']}/notes/{created_note['id']}",
        )
        assert note_response.status_code == 200, f"Getting a note by ID should return a 200 status code instead got {note_response.text}"

        note = note_response.json()
        assert note['ticket'] == note_data['ticket'], "The returned ticket does not match"
        assert note['note'] == note_data['note'], "The returned note does not match"
        assert set(map(lambda x: x['id'], note['users'])) == set(note_data['users']), "The returned users do not match"

    def test_update_note(self, admin_client, filled_out_project):
        """Test updating a note"""

        # Create the note
        note_data = {
            "ticket": "TICKET13",
            "note": "This is a test note.",
            "users": [*map(lambda u: u['id'], filled_out_project['users'])]
        }
        response = admin_client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert response.status_code == 201, "Adding a note should return a 201 status code"
        created_note = response.json()

        # Update the note
        updated_note_data = {
            "ticket": "TICKET14",
            "note": "This is an updated test note.",
        }
        update_response = admin_client.put(
            f"/projects/{filled_out_project['id']}/notes/{created_note['id']}",
            json=updated_note_data,
        )
        assert update_response.status_code == 200, f"Updating a note should return a 200 status code instead got {update_response.text}"

        updated_note = update_response.json()
        assert updated_note['ticket'] == updated_note_data['ticket'], "The updated ticket does not match"
        assert updated_note['note'] == updated_note_data['note'], "The updated note does not match"

    def test_list_project_users(self, admin_client, filled_out_project):
        """Test listing users in a project"""

        response = admin_client.get(
            f"/projects/{filled_out_project['id']}/users"
        )
        assert response.status_code == 200, f"Getting the project should return a 200 status code, instead got {response.text}"
        project_users = response.json()

        assert len(project_users) == 2, "There should be at least one user in the project"


    def test_create_project_with_staff(self, admin_client, user_factory, project_factory):
        """Test that creating a project with staff1/staff2 returns UserGet objects"""

        project = project_factory()
        staff1 = user_factory(0, project['id'])
        staff2 = user_factory(1, project['id'])

        project_with_staff_data = project_data_f(staff1=staff1['id'], staff2=staff2['id'])
        response = admin_client.post("/projects", json=project_with_staff_data)
        assert response.status_code == 201, f"Creating a project with staff should return 201, got {response.text}"

        data = response.json()

        s1 = data['staff1']
        assert s1 is not None, "staff1 should not be null"
        assert s1['id'] == staff1['id'], "staff1 id does not match"
        assert s1['name'] == staff1['name'], "staff1 name does not match"
        assert s1['netid'] == staff1['netid'], "staff1 netid does not match"
        assert s1['is_admin'] == staff1['is_admin'], "staff1 is_admin does not match"

        s2 = data['staff2']
        assert s2 is not None, "staff2 should not be null"
        assert s2['id'] == staff2['id'], "staff2 id does not match"
        assert s2['name'] == staff2['name'], "staff2 name does not match"
        assert s2['netid'] == staff2['netid'], "staff2 netid does not match"
        assert s2['is_admin'] == staff2['is_admin'], "staff2 is_admin does not match"


@pytest.fixture
def groups_of(existing_admin_client):
    """The three groups of a project: (pi, managers, project), read back through the API"""

    def _groups(project: dict) -> tuple[dict, dict, dict]:
        pi = existing_admin_client.get(f"/groups/{project['pi_group_id']}").json()
        project_group = existing_admin_client.get(f"/groups/{project['project_group_id']}").json()
        managers = existing_admin_client.get(f"/groups/{project_group['owner_group_id']}").json()
        return pi, managers, project_group

    return _groups


def _direct(client, group_id: int) -> dict[tuple, dict]:
    """Direct members of a group keyed by ('user'|'group', id)"""

    rows = client.get(f"/groups/{group_id}/direct_members").json()
    return {
        ("user", r["member_user"]["id"]) if r["member_user"] else ("group", r["member_group"]["id"]): r
        for r in rows
    }


def _audit(entity: str, entity_id: int) -> list[dict]:
    return [
        r for r in audit_rows("action = 'metadata_changed'")
        if r["details"].get("entity") == entity and r["details"].get("entity_id") == entity_id
    ]


class TestProjectCreation:

    def test_creates_the_three_groups(self, existing_admin_client, project, groups_of):
        pi, managers, project_group = groups_of(project)

        assert project['pi_group_id'] == pi['id'] and project['project_group_id'] == project_group['id']
        assert pi['owner_group_id'] is None, "The pi group is staff-owned"
        assert managers['owner_group_id'] == pi['id'], "The pi group owns the managers group"
        assert project_group['owner_group_id'] == managers['id'], "The managers group owns the project group"

        assert ("group", pi['id']) in _direct(existing_admin_client, managers['id']), "The pi group is a member of managers"
        assert ("group", pi['id']) in _direct(existing_admin_client, project_group['id']), "The pi group is a member of the project group"
        assert _direct(existing_admin_client, pi['id']) == {}, "Nobody is a PI until staff add one"

    def test_pi_ids_seed_the_pi_group(self, existing_admin_client, plain_user_factory):
        pis = [plain_user_factory(0), plain_user_factory(1)]
        response = existing_admin_client.post("/projects", json={**project_data_f(), "pi_ids": [p['id'] for p in pis] + [pis[0]['id']]})
        assert response.status_code == 201, response.text
        project = response.json()
        try:
            assert {k for k in _direct(existing_admin_client, project['pi_group_id'])} == {("user", p['id']) for p in pis}

            # PIs reach the project group through the pi group, so they show up as users of the project
            users = {u['id']: u for u in existing_admin_client.get(f"/projects/{project['id']}/users").json()}
            assert set(users) == {p['id'] for p in pis}
            assert all(u['is_pi'] and u['direct'] is False for u in users.values())
        finally:
            existing_admin_client.delete(f"/projects/{project['id']}")

    def test_pi_id_of_unknown_user_rolls_everything_back(self, existing_admin_client):
        data = project_data_f()
        response = existing_admin_client.post("/projects", json={**data, "pi_ids": [999999999]})
        assert response.status_code == 404, response.text
        names = [p['name'] for p in existing_admin_client.get("/projects", params={"name": f"eq.{data['name']}"}).json()]
        assert names == [], "The project must not survive the failed request"

    def test_only_the_missing_project_group_is_created(self, existing_admin_client, project, groups_of):
        pi, *_ = groups_of(project)
        response = existing_admin_client.post("/projects", json={**project_data_f(), "pi_group_id": pi['id']})
        assert response.status_code == 201, response.text
        second = response.json()
        try:
            assert second['pi_group_id'] == pi['id'], "The supplied pi group is used as is"
            assert second['project_group_id'] not in (None, project['project_group_id'])
            _, managers, project_group = groups_of(second)
            assert managers['owner_group_id'] == pi['id']
            assert ("group", pi['id']) in _direct(existing_admin_client, project_group['id'])
        finally:
            existing_admin_client.delete(f"/projects/{second['id']}")

    def test_only_the_missing_pi_group_is_created(self, existing_admin_client, project):
        response = existing_admin_client.post("/projects", json={**project_data_f(), "project_group_id": project['project_group_id']})
        assert response.status_code == 201, response.text
        second = response.json()
        try:
            assert second['project_group_id'] == project['project_group_id']
            assert second['pi_group_id'] not in (None, project['pi_group_id'])
            assert existing_admin_client.get(f"/groups/{second['pi_group_id']}").json()['owner_group_id'] is None
        finally:
            existing_admin_client.delete(f"/projects/{second['id']}")

    def test_projects_with_the_same_slug_get_numbered_groups(self, existing_admin_client, groups_of):
        """Project names are unique, but "Slug Twin 1" and "slug_twin_1" slug to the same group name"""

        n = random.randint(10**5, 10**6)
        created = []
        try:
            for name in (f"Slug Twin {n}", f"slug_twin_{n}"):
                response = existing_admin_client.post("/projects", json=project_data_f(name=name))
                assert response.status_code == 201, response.text
                created.append(response.json())
            first, second = (groups_of(p) for p in created)
            assert [g['name'] for g in first] == [f"slug_twin_{n}_pi", f"slug_twin_{n}_managers", f"slug_twin_{n}"]
            assert [g['name'] for g in second] == [f"slug_twin_{n}_pi_2", f"slug_twin_{n}_managers_2", f"slug_twin_{n}_2"]
        finally:
            for p in created:
                existing_admin_client.delete(f"/projects/{p['id']}")

    def test_supplied_group_must_exist_and_not_be_deleted(self, existing_admin_client, group_factory):
        assert existing_admin_client.post("/projects", json={**project_data_f(), "pi_group_id": 999999999}).status_code == 404

        gone = group_factory()
        existing_admin_client.delete(f"/groups/{gone['id']}")
        assert existing_admin_client.post("/projects", json={**project_data_f(), "project_group_id": gone['id']}).status_code == 404

    def test_requires_staff(self, nonadmin_client):
        assert nonadmin_client.post("/projects", json=project_data_f()).status_code == 403
        assert nonadmin_client.get("/projects").status_code == 403


class TestProjectPermissions:

    @pytest.fixture
    def roles(self, existing_admin_client, project, groups_of, plain_user_factory, client_as):
        """A project with a PI, a manager (member of the managers group) and an outsider"""

        pi, managers, _ = groups_of(project)
        people = {"pi": plain_user_factory(0), "manager": plain_user_factory(1), "outsider": plain_user_factory(2), "target": plain_user_factory(3)}
        assert existing_admin_client.post(f"/projects/{project['id']}/pis", json={"user_id": people["pi"]['id']}).status_code == 201
        assert existing_admin_client.post(f"/groups/{managers['id']}/members", json={"user_id": people["manager"]['id']}).status_code == 201
        return {"clients": {k: client_as(v) for k, v in people.items()}, "users": people, "project": project, "groups": (pi, managers)}

    def test_pi_can_edit_metadata_but_not_pointers(self, existing_admin_client, roles):
        project, pi_client = roles["project"], roles["clients"]["pi"]

        response = pi_client.put(f"/projects/{project['id']}", json={"description": "Edited by a PI", "last_contact": "2030-01-01T00:00:00"})
        assert response.status_code == 200, response.text
        assert response.json()['description'] == "Edited by a PI"

        for field, value in (
            ("pi_group_id", None), ("project_group_id", None), ("accounting_group", "other"),
            ("staff1", None), ("staff2", None), ("ticket", 4242), ("ticket", None),
        ):
            denied = pi_client.put(f"/projects/{project['id']}", json={field: value})
            assert denied.status_code == 403, f"A PI must not change {field}: {denied.text}"

        unchanged = existing_admin_client.get(f"/projects/{project['id']}").json()
        assert unchanged['pi_group_id'] == project['pi_group_id'] and unchanged['accounting_group'] == project['accounting_group']
        assert unchanged['ticket'] == project['ticket']

        # Staff may change the pointers and the ticket
        assert existing_admin_client.put(f"/projects/{project['id']}", json={"accounting_group": "staff-set"}).status_code == 200
        assert existing_admin_client.put(f"/projects/{project['id']}", json={"ticket": 4242}).json()['ticket'] == 4242

    def test_put_is_audited(self, existing_admin_client, roles):
        project = roles["project"]
        roles["clients"]["pi"].put(f"/projects/{project['id']}", json={"description": "Audited", "last_contact": "2031-02-03T00:00:00"})

        [entry] = _audit("project", project['id'])
        assert entry['actor_id'] == roles["users"]["pi"]['id']
        changes = entry['details']['changes']
        assert changes['description'] == {"old": project['description'], "new": "Audited"}
        assert changes['last_contact'] == {"old": project['last_contact'], "new": "2031-02-03T00:00:00"}, "Datetimes are stored as ISO strings"

        # A PUT that changes nothing writes nothing
        existing_admin_client.put(f"/projects/{project['id']}", json={"description": "Audited"})
        assert len(_audit("project", project['id'])) == 1

    def test_staff_pointer_change_must_name_a_live_group(self, existing_admin_client, roles):
        assert existing_admin_client.put(f"/projects/{roles['project']['id']}", json={"pi_group_id": 999999999}).status_code == 404

    def test_manager_adds_and_removes_members_but_cannot_edit(self, existing_admin_client, roles):
        project, manager, target = roles["project"], roles["clients"]["manager"], roles["users"]["target"]

        assert manager.post(f"/projects/{project['id']}/users", json={"user_id": target['id']}).status_code == 201
        assert target['id'] in {u['id'] for u in manager.get(f"/projects/{project['id']}/users").json()}
        assert manager.delete(f"/projects/{project['id']}/users/{target['id']}").status_code == 204

        assert manager.put(f"/projects/{project['id']}", json={"description": "nope"}).status_code == 403
        assert manager.post(f"/projects/{project['id']}/pis", json={"user_id": target['id']}).status_code == 403
        assert manager.delete(f"/projects/{project['id']}").status_code == 403

    def test_pi_manages_members_through_the_managers_group(self, roles):
        project, pi, target = roles["project"], roles["clients"]["pi"], roles["users"]["target"]
        # The pi group owns the managers group and is a member of it, so a PI administers the project group
        assert pi.post(f"/projects/{project['id']}/users", json={"user_id": target['id']}).status_code == 201

    def test_outsider_is_denied_everywhere(self, roles):
        project, outsider, target = roles["project"], roles["clients"]["outsider"], roles["users"]["target"]
        pid = project['id']

        assert outsider.get(f"/projects/{pid}").status_code == 403
        assert outsider.get(f"/projects/{pid}/users").status_code == 403
        assert outsider.get(f"/projects/{pid}/pis").status_code == 403
        assert outsider.put(f"/projects/{pid}", json={"description": "x"}).status_code == 403
        assert outsider.post(f"/projects/{pid}/users", json={"user_id": target['id']}).status_code == 403
        assert outsider.delete(f"/projects/{pid}/users/{target['id']}").status_code == 403
        assert outsider.post(f"/projects/{pid}/pis", json={"user_id": target['id']}).status_code == 403
        assert outsider.delete(f"/projects/{pid}").status_code == 403
        assert outsider.get("/projects").status_code == 403

    def test_unknown_project_is_404_for_non_staff(self, roles):
        assert roles["clients"]["outsider"].get("/projects/999999999").status_code == 404
        assert roles["clients"]["outsider"].put("/projects/999999999", json={"description": "x"}).status_code == 404

    def test_pi_and_manager_can_view_but_not_list(self, roles):
        project = roles["project"]
        for role in ("pi", "manager"):
            client = roles["clients"][role]
            assert client.get(f"/projects/{project['id']}").status_code == 200, role
            assert client.get(f"/projects/{project['id']}/users").status_code == 200, role
            assert client.get(f"/projects/{project['id']}/pis").status_code == 200, role
            assert client.get("/projects").status_code == 403, role
            assert client.get(f"/projects/{project['id']}/notes").status_code == 403, "Notes stay staff only"


class TestProjectMembers:

    def test_primary_project_survives_removal(self, existing_admin_client, project, user_factory):
        member = user_factory(0, project['id'])
        try:
            assert existing_admin_client.get(f"/users/{member['id']}").json()['primary_project_id'] == project['id']

            assert existing_admin_client.delete(f"/projects/{project['id']}/users/{member['id']}").status_code == 204

            fresh = existing_admin_client.get(f"/users/{member['id']}").json()
            assert fresh['primary_project_id'] == project['id'], "The primary project does not need a current membership"
            assert fresh['projects'] == []
        finally:
            existing_admin_client.delete(f"/users/{member['id']}")

    def test_direct_members_are_flagged(self, existing_admin_client, project, plain_user_factory):
        first = plain_user_factory(0)
        assert existing_admin_client.post(f"/projects/{project['id']}/users", json={"user_id": first['id']}).status_code == 201

        users = {u['id']: u for u in existing_admin_client.get(f"/projects/{project['id']}/users").json()}
        assert users[first['id']]['direct'] is True and users[first['id']]['created_at'] is not None
        assert users[first['id']]['is_pi'] is False

    def test_adding_twice_conflicts_and_unknown_user_404s(self, existing_admin_client, project, plain_user_factory):
        member = plain_user_factory(0)
        assert existing_admin_client.post(f"/projects/{project['id']}/users", json={"user_id": member['id']}).status_code == 201
        assert existing_admin_client.post(f"/projects/{project['id']}/users", json={"user_id": member['id']}).status_code == 409
        assert existing_admin_client.post(f"/projects/{project['id']}/users", json={"user_id": 999999999}).status_code == 404

    def test_removal_reports_access_through_another_group(self, existing_admin_client, project, groups_of, plain_user_factory):
        pi_only, outsider = plain_user_factory(0), plain_user_factory(1)
        pi, *_ = groups_of(project)
        assert existing_admin_client.post(f"/projects/{project['id']}/pis", json={"user_id": pi_only['id']}).status_code == 201

        response = existing_admin_client.delete(f"/projects/{project['id']}/users/{pi_only['id']}")
        assert response.status_code == 404
        assert "not a direct member" in response.json()['detail']
        assert f"access comes through {pi['name']}" in response.json()['detail']

        # The failed removal changed nothing: the PI still has access
        assert pi_only['id'] in {u['id'] for u in existing_admin_client.get(f"/projects/{project['id']}/users").json()}

        # Nobody at all is a different message
        response = existing_admin_client.delete(f"/projects/{project['id']}/users/{outsider['id']}")
        assert response.status_code == 404
        assert "access comes through" not in response.json()['detail']

    def test_removing_a_direct_member_keeps_access_through_another_group(self, existing_admin_client, project, plain_user_factory):
        both = plain_user_factory(0)
        pid = project['id']
        existing_admin_client.post(f"/projects/{pid}/pis", json={"user_id": both['id']})
        existing_admin_client.post(f"/projects/{pid}/users", json={"user_id": both['id']})

        assert existing_admin_client.delete(f"/projects/{pid}/users/{both['id']}").status_code == 204
        [row] = existing_admin_client.get(f"/projects/{pid}/users").json()
        assert row['id'] == both['id'] and row['direct'] is False and row['is_pi'] is True

    def test_project_without_a_project_group(self, existing_admin_client, project, plain_user_factory):
        member = plain_user_factory(0)
        assert existing_admin_client.put(f"/projects/{project['id']}", json={"project_group_id": None}).status_code == 200
        assert existing_admin_client.post(f"/projects/{project['id']}/users", json={"user_id": member['id']}).status_code == 400
        assert existing_admin_client.get(f"/projects/{project['id']}/users").json() == []


class TestProjectPis:

    def test_add_list_remove(self, existing_admin_client, project, plain_user_factory):
        pi = plain_user_factory(0)
        pid = project['id']

        assert existing_admin_client.post(f"/projects/{pid}/pis", json={"user_id": pi['id']}).status_code == 201
        assert existing_admin_client.post(f"/projects/{pid}/pis", json={"user_id": pi['id']}).status_code == 409

        [row] = existing_admin_client.get(f"/projects/{pid}/pis").json()
        assert row['user_id'] == pi['id'] and row['direct'] is True and row['group_id'] == project['pi_group_id']

        assert existing_admin_client.delete(f"/projects/{pid}/pis/{pi['id']}").status_code == 204
        assert existing_admin_client.get(f"/projects/{pid}/pis").json() == []
        assert existing_admin_client.delete(f"/projects/{pid}/pis/{pi['id']}").status_code == 404

    def test_pi_route_reports_indirect_membership(self, existing_admin_client, project, group, plain_user_factory):
        member = plain_user_factory(0)
        existing_admin_client.post(f"/groups/{group['id']}/members", json={"user_id": member['id']})
        existing_admin_client.post(f"/groups/{project['pi_group_id']}/members", json={"group_id": group['id']})

        [row] = existing_admin_client.get(f"/projects/{project['id']}/pis").json()
        assert row['direct'] is False
        response = existing_admin_client.delete(f"/projects/{project['id']}/pis/{member['id']}")
        assert response.status_code == 404 and f"access comes through {group['name']}" in response.json()['detail']


class TestProjectGroupMembers:
    """Groups as direct members of the project group (/groups) and the pi group (/pi_groups)"""

    def test_add_list_remove_on_project_group(self, existing_admin_client, project, group, groups_of, plain_user_factory):
        member = plain_user_factory(0)
        pid = project['id']
        existing_admin_client.post(f"/groups/{group['id']}/members", json={"user_id": member['id']})

        added = existing_admin_client.post(f"/projects/{pid}/groups", json={"group_id": group['id']})
        assert added.status_code == 201, added.text
        assert added.json()['member_group']['id'] == group['id'] and added.json()['group_id'] == project['project_group_id']
        assert existing_admin_client.post(f"/projects/{pid}/groups", json={"group_id": group['id']}).status_code == 409

        # The pi group was added to the project group at creation, so it is listed alongside
        pi, _, _ = groups_of(project)
        rows = existing_admin_client.get(f"/projects/{pid}/groups").json()
        assert {r['member_group']['id'] for r in rows} == {pi['id'], group['id']}
        assert all(r['member_user'] is None for r in rows)

        # The group's user reaches the project through it
        [user_row] = [u for u in existing_admin_client.get(f"/projects/{pid}/users").json() if u['id'] == member['id']]
        assert user_row['direct'] is False, "access is through the group, not a direct row"
        [path] = [r for r in existing_admin_client.get(f"/groups/{project['project_group_id']}/members").json() if r['user_id'] == member['id']]
        assert path['direct'] is False and path['path_names'][0][-1] == group['name']

        assert existing_admin_client.delete(f"/projects/{pid}/groups/{group['id']}").status_code == 204
        assert {r['member_group']['id'] for r in existing_admin_client.get(f"/projects/{pid}/groups").json()} == {pi['id']}
        assert member['id'] not in {u['id'] for u in existing_admin_client.get(f"/projects/{pid}/users").json()}
        assert existing_admin_client.delete(f"/projects/{pid}/groups/{group['id']}").status_code == 404

    def test_add_list_remove_on_pi_group(self, existing_admin_client, project, group, plain_user_factory):
        pi_user = plain_user_factory(0)
        pid = project['id']
        existing_admin_client.post(f"/groups/{group['id']}/members", json={"user_id": pi_user['id']})

        assert existing_admin_client.get(f"/projects/{pid}/pi_groups").json() == []
        added = existing_admin_client.post(f"/projects/{pid}/pi_groups", json={"group_id": group['id']})
        assert added.status_code == 201, added.text
        assert added.json()['group_id'] == project['pi_group_id']
        [row] = existing_admin_client.get(f"/projects/{pid}/pi_groups").json()
        assert row['member_group']['id'] == group['id']

        [pi_row] = existing_admin_client.get(f"/projects/{pid}/pis").json()
        assert pi_row['user_id'] == pi_user['id'] and pi_row['direct'] is False

        assert existing_admin_client.delete(f"/projects/{pid}/pi_groups/{group['id']}").status_code == 204
        assert existing_admin_client.get(f"/projects/{pid}/pi_groups").json() == []
        assert existing_admin_client.get(f"/projects/{pid}/pis").json() == []

    def test_unknown_group_and_cycles_are_rejected(self, existing_admin_client, project, groups_of):
        pid = project['id']
        _, managers, project_group = groups_of(project)
        assert existing_admin_client.post(f"/projects/{pid}/groups", json={"group_id": 999999999}).status_code == 404
        assert existing_admin_client.post(f"/projects/{pid}/groups", json={"group_id": project_group['id']}).status_code == 400
        # The managers group may join the project group (nothing above it contains the project group)
        assert existing_admin_client.post(f"/projects/{pid}/groups", json={"group_id": managers['id']}).status_code == 201
        # But the project group cannot join the pi group, which is already a member of the project group
        assert existing_admin_client.post(f"/projects/{pid}/pi_groups", json={"group_id": project_group['id']}).status_code == 400

    def test_project_without_groups(self, existing_admin_client, project, group):
        pid = project['id']
        assert existing_admin_client.put(f"/projects/{pid}", json={"project_group_id": None, "pi_group_id": None}).status_code == 200
        for route in ("groups", "pi_groups"):
            assert existing_admin_client.get(f"/projects/{pid}/{route}").json() == []
            assert existing_admin_client.post(f"/projects/{pid}/{route}", json={"group_id": group['id']}).status_code == 400
            assert existing_admin_client.delete(f"/projects/{pid}/{route}/{group['id']}").status_code == 400

    def test_group_membership_is_audited(self, existing_admin_client, project, group):
        pid = project['id']
        existing_admin_client.post(f"/projects/{pid}/groups", json={"group_id": group['id']})
        existing_admin_client.delete(f"/projects/{pid}/groups/{group['id']}")
        actions = [
            r['action'] for r in audit_rows(f"group_id = {project['project_group_id']} AND member_group_id = {group['id']}")
        ]
        assert actions == ['member_added', 'member_removed']


class TestProjectGroupMemberPermissions:

    @pytest.fixture
    def roles(self, existing_admin_client, project, groups_of, plain_user_factory, client_as, group):
        pi, managers, _ = groups_of(project)
        people = {"pi": plain_user_factory(0), "manager": plain_user_factory(1), "outsider": plain_user_factory(2)}
        assert existing_admin_client.post(f"/projects/{project['id']}/pis", json={"user_id": people["pi"]['id']}).status_code == 201
        assert existing_admin_client.post(f"/groups/{managers['id']}/members", json={"user_id": people["manager"]['id']}).status_code == 201
        return {"clients": {k: client_as(v) for k, v in people.items()}, "project": project, "group": group}

    def test_pi_and_manager_manage_project_groups_but_not_pi_groups(self, roles):
        pid, gid = roles["project"]['id'], roles["group"]['id']
        for role in ("pi", "manager"):
            client = roles["clients"][role]
            assert client.get(f"/projects/{pid}/groups").status_code == 200, role
            assert client.get(f"/projects/{pid}/pi_groups").status_code == 200, role
            assert client.post(f"/projects/{pid}/groups", json={"group_id": gid}).status_code == 201, role
            assert client.delete(f"/projects/{pid}/groups/{gid}").status_code == 204, role
            assert client.post(f"/projects/{pid}/pi_groups", json={"group_id": gid}).status_code == 403, role
            assert client.delete(f"/projects/{pid}/pi_groups/{gid}").status_code == 403, role

    def test_outsider_is_denied(self, roles):
        pid, gid, outsider = roles["project"]['id'], roles["group"]['id'], roles["clients"]["outsider"]
        for route in ("groups", "pi_groups"):
            assert outsider.get(f"/projects/{pid}/{route}").status_code == 403
            assert outsider.post(f"/projects/{pid}/{route}", json={"group_id": gid}).status_code == 403
            assert outsider.delete(f"/projects/{pid}/{route}/{gid}").status_code == 403


class TestProjectDeletion:

    def test_delete_removes_the_project_and_keeps_its_groups(self, existing_admin_client, user_factory, project_factory):
        """Deleting a project removes the row; its groups and their memberships stay, primary projects are cleared"""

        project = project_factory()
        member = user_factory(0, project['id'])
        try:
            assert existing_admin_client.delete(f"/projects/{project['id']}").status_code == 204
            assert existing_admin_client.get(f"/projects/{project['id']}").status_code == 404
            assert existing_admin_client.delete(f"/projects/{project['id']}").status_code == 404

            for group_id in (project['pi_group_id'], project['project_group_id']):
                assert existing_admin_client.get(f"/groups/{group_id}").status_code == 200, "Groups are not deleted with the project"
            assert member['id'] in {m['user_id'] for m in existing_admin_client.get(f"/groups/{project['project_group_id']}/members").json()}
            assert existing_admin_client.get(f"/users/{member['id']}").json()['primary_project_id'] is None
            assert existing_admin_client.get(f"/users/{member['id']}/projects").json() == []
        finally:
            existing_admin_client.delete(f"/users/{member['id']}")

    def test_delete_unknown_project(self, existing_admin_client):
        assert existing_admin_client.delete("/projects/999999999").status_code == 404
