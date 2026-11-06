"""Group membership, ownership, administration structure, deletion and the audit trail"""
import asyncio
import random
from typing import Callable

import pytest
from sqlalchemy import text

from userapp.api.tests.conftest import _make_auth_client, _seed_db_url
from userapp.db import connect_engine


def _sql(sql: str, commit: bool = False, **params) -> list[dict]:
    """Run raw SQL against the test database. The audit log has no API in this wave."""

    async def run():
        engine = await connect_engine(_seed_db_url())
        try:
            async with engine.begin() if commit else engine.connect() as conn:
                result = await conn.execute(text(sql), params)
                return [dict(row._mapping) for row in result] if result.returns_rows else []
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _audit(group_id: int, action: str | None = None) -> list[dict]:
    rows = _sql(
        "SELECT id, action::text AS action, actor_id, group_id, member_user_id, member_group_id, caused_by, details "
        "FROM audit_log WHERE group_id = :g ORDER BY id",
        g=group_id,
    )
    return [r for r in rows if action is None or r["action"] == action]


@pytest.fixture
def make_group(existing_admin_client, group_factory):
    """Create groups that are soft-deleted again after the test"""

    created = []

    def _make(**fields) -> dict:
        group = group_factory(**fields)
        created.append(group)
        return group

    yield _make

    for group in created:
        existing_admin_client.delete(f"/groups/{group['id']}")


@pytest.fixture
def people(existing_admin_client, project, user_factory):
    """Four users that belong to no group, deleted after the test"""

    users = [user_factory(i, project['id']) for i in range(4)]
    yield users
    for user in users:
        existing_admin_client.delete(f"/users/{user['id']}")


@pytest.fixture
def client_as():
    """A client that is logged in as the given (non-staff) user"""

    generators = []

    def _make(user: dict):
        generator = _make_auth_client({"id": user["id"], "is_admin": False})
        client = next(generator)
        generators.append(generator)
        return client

    yield _make

    for generator in generators:
        generator.close()


def _member_ids(client, group_id: int) -> set[int]:
    response = client.get(f"/groups/{group_id}/members")
    assert response.status_code == 200, response.text
    return {m["user_id"] for m in response.json()}


class TestEffectiveMembership:

    def test_direct_and_nested_membership_with_paths(self, existing_admin_client, make_group, people, group_member):
        user = people[0]
        a, b, c = make_group(), make_group(), make_group()
        group_member(c['id'], user_id=user['id'])
        group_member(b['id'], member_group_id=c['id'])
        group_member(a['id'], member_group_id=b['id'])

        [row] = existing_admin_client.get(f"/groups/{a['id']}/members").json()
        assert row['user_id'] == user['id']
        assert row['direct'] is False
        assert row['paths'] == [[a['id'], b['id'], c['id']]]
        assert row['path_names'] == [[a['name'], b['name'], c['name']]]

        [row] = existing_admin_client.get(f"/groups/{b['id']}/members").json()
        assert row['direct'] is False
        assert row['paths'] == [[b['id'], c['id']]]

        [row] = existing_admin_client.get(f"/groups/{c['id']}/members").json()
        assert row['direct'] is True
        assert row['paths'] == [[c['id']]]

    def test_every_path_is_listed_shortest_first(self, existing_admin_client, make_group, people, group_member):
        user = people[0]
        a, b = make_group(), make_group()
        group_member(b['id'], user_id=user['id'])
        group_member(a['id'], member_group_id=b['id'])
        group_member(a['id'], user_id=user['id'])

        [row] = existing_admin_client.get(f"/groups/{a['id']}/members").json()
        assert row['direct'] is True
        assert row['paths'] == [[a['id']], [a['id'], b['id']]]
        assert row['path_names'] == [[a['name']], [a['name'], b['name']]]

    def test_a_user_appears_once_per_group_however_many_paths(self, existing_admin_client, make_group, people, group_member):
        user = people[0]
        top, left, right = make_group(), make_group(), make_group()
        group_member(left['id'], user_id=user['id'])
        group_member(right['id'], user_id=user['id'])
        group_member(top['id'], member_group_id=left['id'])
        group_member(top['id'], member_group_id=right['id'])

        rows = existing_admin_client.get(f"/groups/{top['id']}/members").json()
        assert len(rows) == 1
        assert sorted(rows[0]['paths']) == sorted([[top['id'], left['id']], [top['id'], right['id']]])

    def test_removing_a_member_only_removes_that_path(self, existing_admin_client, make_group, people, group_member):
        user = people[0]
        a, b = make_group(), make_group()
        group_member(b['id'], user_id=user['id'])
        group_member(a['id'], member_group_id=b['id'])
        group_member(a['id'], user_id=user['id'])

        # Dropping the user from b leaves their direct membership of a alone
        assert existing_admin_client.delete(f"/groups/{b['id']}/members/users/{user['id']}").status_code == 204
        [row] = existing_admin_client.get(f"/groups/{a['id']}/members").json()
        assert row['paths'] == [[a['id']]]
        assert _member_ids(existing_admin_client, b['id']) == set()

        # Dropping the group from a removes no one's direct membership
        assert existing_admin_client.delete(f"/groups/{a['id']}/members/groups/{b['id']}").status_code == 204
        assert _member_ids(existing_admin_client, a['id']) == {user['id']}
        assert existing_admin_client.get(f"/groups/{a['id']}/direct_members").json()[0]['member_user']['id'] == user['id']

    def test_removing_a_nonexistent_group_member_is_404(self, existing_admin_client, make_group):
        a, b = make_group(), make_group()
        response = existing_admin_client.delete(f"/groups/{a['id']}/members/groups/{b['id']}")
        assert response.status_code == 404

    def test_direct_members_lists_users_and_groups(self, existing_admin_client, make_group, people, group_member):
        a, b = make_group(), make_group()
        group_member(a['id'], user_id=people[0]['id'])
        group_member(a['id'], member_group_id=b['id'])

        rows = existing_admin_client.get(f"/groups/{a['id']}/direct_members").json()
        assert len(rows) == 2
        user_row = next(r for r in rows if r['member_user'])
        group_row = next(r for r in rows if r['member_group'])
        assert user_row['member_group'] is None and user_row['member_user']['id'] == people[0]['id']
        assert group_row['member_user'] is None and group_row['member_group']['id'] == b['id']
        assert group_row['group_id'] == a['id']

    def test_member_of(self, existing_admin_client, make_group, group_member):
        a, b, c = make_group(), make_group(), make_group()
        group_member(b['id'], member_group_id=a['id'])
        group_member(c['id'], member_group_id=b['id'])
        group_member(c['id'], member_group_id=a['id'])

        response = existing_admin_client.get(f"/groups/{a['id']}/member_of")
        assert response.status_code == 200, response.text
        by_group = {row['group']['id']: row['paths'] for row in response.json()}
        assert by_group == {
            b['id']: [[b['id'], a['id']]],
            c['id']: [[c['id'], a['id']], [c['id'], b['id'], a['id']]],
        }

        assert existing_admin_client.get(f"/groups/{c['id']}/member_of").json() == []
        assert existing_admin_client.get("/groups/99999999/member_of").status_code == 404

    def test_user_groups(self, existing_admin_client, make_group, people, group_member):
        user = people[0]
        a, b = make_group(), make_group()
        group_member(b['id'], user_id=user['id'])
        group_member(a['id'], member_group_id=b['id'])

        response = existing_admin_client.get(f"/users/{user['id']}/groups")
        assert response.status_code == 200, response.text
        rows = {r['group_id']: r for r in response.json()}
        # The user also belongs to the project group they were created with
        assert {a['id'], b['id']} <= set(rows)
        assert rows[b['id']]['direct'] is True
        assert rows[b['id']]['managed_by'] == 'APPLICATION', "the group's managed_by, not the membership's"
        assert rows[a['id']]['direct'] is False
        assert rows[a['id']]['paths'] == [[a['id'], b['id']]]
        assert rows[a['id']]['path_names'] == [[a['name'], b['name']]]
        assert rows[a['id']]['name'] == a['name']

        # The same rows come back on the user object
        full = existing_admin_client.get(f"/users/{user['id']}").json()
        assert {a['id'], b['id']} <= {g['group_id'] for g in full['groups']}

    def test_user_groups_visible_to_the_user_only(self, nonadmin_client, user, people, make_group, group_member):
        group_member(make_group()['id'], user_id=user['id'])

        response = nonadmin_client.get(f"/users/{user['id']}/groups")
        assert response.status_code == 200
        assert response.json(), "The user should see the group the fixture put them in"

        assert nonadmin_client.get(f"/users/{people[0]['id']}/groups").status_code == 403

    def test_deleting_a_user_drops_their_membership(self, existing_admin_client, make_group, user_factory, project, group_member):
        user = user_factory(9, project['id'])
        group = make_group()
        group_member(group['id'], user_id=user['id'])
        assert _member_ids(existing_admin_client, group['id']) == {user['id']}

        assert existing_admin_client.delete(f"/users/{user['id']}").status_code == 204
        assert _member_ids(existing_admin_client, group['id']) == set()


class TestCycles:

    def test_group_cannot_be_member_of_itself(self, existing_admin_client, make_group):
        a = make_group()
        response = existing_admin_client.post(f"/groups/{a['id']}/members", json={"group_id": a['id']})
        assert response.status_code == 400
        assert response.json()['detail'] == "A group cannot be a member of itself"

    def test_direct_cycle_is_rejected(self, existing_admin_client, make_group, group_member):
        a, b = make_group(), make_group()
        group_member(a['id'], member_group_id=b['id'])

        response = existing_admin_client.post(f"/groups/{b['id']}/members", json={"group_id": a['id']})
        assert response.status_code == 400
        assert "membership cycle" in response.json()['detail']

    def test_transitive_cycle_is_rejected(self, existing_admin_client, make_group, group_member):
        a, b, c = make_group(), make_group(), make_group()
        group_member(a['id'], member_group_id=b['id'])
        group_member(b['id'], member_group_id=c['id'])

        response = existing_admin_client.post(f"/groups/{c['id']}/members", json={"group_id": a['id']})
        assert response.status_code == 400
        assert "membership cycle" in response.json()['detail']

        # A diamond is not a cycle
        d = make_group()
        group_member(a['id'], member_group_id=c['id'])
        group_member(d['id'], member_group_id=c['id'])

    def test_rejected_cycle_changes_nothing(self, existing_admin_client, make_group, group_member):
        a, b = make_group(), make_group()
        group_member(a['id'], member_group_id=b['id'])
        existing_admin_client.post(f"/groups/{b['id']}/members", json={"group_id": a['id']})

        assert existing_admin_client.get(f"/groups/{b['id']}/direct_members").json() == []
        assert _audit(b['id'], 'member_added') == []

    def test_group_cannot_own_itself(self, existing_admin_client, make_group):
        a = make_group()
        response = existing_admin_client.put(f"/groups/{a['id']}", json={"owner_group_id": a['id']})
        assert response.status_code == 400
        assert response.json()['detail'] == "A group cannot own itself"

    def test_ownership_loop_is_rejected(self, existing_admin_client, make_group):
        o, m = make_group(), make_group()
        assert existing_admin_client.put(f"/groups/{m['id']}", json={"owner_group_id": o['id']}).status_code == 200

        # O owns M, so M cannot own O: that would let M promote itself
        response = existing_admin_client.put(f"/groups/{o['id']}", json={"owner_group_id": m['id']})
        assert response.status_code == 400
        assert "ownership loop" in response.json()['detail']

    def test_transitive_ownership_loop_is_rejected(self, existing_admin_client, make_group):
        a, b, c = make_group(), make_group(), make_group()
        assert existing_admin_client.put(f"/groups/{b['id']}", json={"owner_group_id": a['id']}).status_code == 200
        assert existing_admin_client.put(f"/groups/{c['id']}", json={"owner_group_id": b['id']}).status_code == 200

        response = existing_admin_client.put(f"/groups/{a['id']}", json={"owner_group_id": c['id']})
        assert response.status_code == 400
        assert "ownership loop" in response.json()['detail']

        assert existing_admin_client.get(f"/groups/{a['id']}").json()['owner_group_id'] is None

    def test_owner_must_exist(self, existing_admin_client, make_group):
        a = make_group()
        assert existing_admin_client.put(f"/groups/{a['id']}", json={"owner_group_id": 99999999}).status_code == 404

    def test_staff_can_clear_the_owner(self, existing_admin_client, make_group):
        o = make_group()
        b = make_group(owner_group_id=o['id'])
        response = existing_admin_client.put(f"/groups/{b['id']}", json={"owner_group_id": None})
        assert response.status_code == 200
        assert response.json()['owner_group_id'] is None


class TestOwnersAdministerGroups:

    @pytest.fixture
    def owned(self, existing_admin_client, make_group, people, group_member):
        """B owned by O. people[0] is an owner, people[1] is nobody."""
        o = make_group()
        b = make_group(owner_group_id=o['id'])
        group_member(o['id'], user_id=people[0]['id'])
        return {"owners": o, "base": b, "owner": people[0], "stranger": people[1]}

    def test_owner_can_view_add_and_remove_members(self, owned, people, client_as):
        client = client_as(owned['owner'])
        base_id = owned['base']['id']

        assert client.get(f"/groups/{base_id}").status_code == 200
        assert client.get(f"/groups/{base_id}/members").status_code == 200
        assert client.get(f"/groups/{base_id}/direct_members").status_code == 200

        response = client.post(f"/groups/{base_id}/members", json={"user_id": people[2]['id']})
        assert response.status_code == 201, response.text
        assert _member_ids(client, base_id) == {people[2]['id']}

        assert client.delete(f"/groups/{base_id}/members/users/{people[2]['id']}").status_code == 204
        assert _member_ids(client, base_id) == set()

    def test_owner_can_add_a_group_member(self, owned, make_group, client_as):
        client = client_as(owned['owner'])
        other = make_group()

        response = client.post(f"/groups/{owned['base']['id']}/members", json={"group_id": other['id']})
        assert response.status_code == 201, response.text
        assert client.delete(f"/groups/{owned['base']['id']}/members/groups/{other['id']}").status_code == 204

    def test_owner_cannot_edit_group_metadata(self, owned, client_as):
        """Owning a group means editing its members; its metadata, the description included, is staff only"""

        client = client_as(owned['owner'])
        url = f"/groups/{owned['base']['id']}"

        for body in (
            {"description": "managed by owners"},
            {"name": "sneaky-rename"},
            {"unix_gid": 59999},
            {"owner_group_id": None},
            {"owner_group_id": owned['owners']['id']},
            {"managed_by": "MANIFEST"},
        ):
            response = client.put(url, json=body)
            assert response.status_code == 403, f"{body} should be refused for an owner, got {response.text}"
        assert client.post(f"{url}/unix_gid").status_code == 403

        group = client.get(url).json()
        assert group['name'] == owned['base']['name']
        assert group['owner_group_id'] == owned['owners']['id']
        assert group['description'] == owned['base']['description']

    def test_owner_cannot_create_delete_or_hand_over_membership_management(self, owned, people, client_as):
        client = client_as(owned['owner'])
        base_id = owned['base']['id']

        assert client.post("/groups", json={"name": f"owner-made-{random.randint(0, 10**7)}"}).status_code == 403
        assert client.delete(f"/groups/{base_id}").status_code == 403

    def test_owner_cannot_touch_the_group_that_owns_theirs(self, owned, people, client_as):
        client = client_as(owned['owner'])
        owners_id = owned['owners']['id']

        # O has no owner, so only staff edit who the owners are
        assert client.post(f"/groups/{owners_id}/members", json={"user_id": people[2]['id']}).status_code == 403
        assert client.get(f"/groups/{owners_id}").status_code == 403

    def test_non_owner_is_refused(self, owned, people, client_as):
        client = client_as(owned['stranger'])
        base_id = owned['base']['id']

        assert client.get(f"/groups/{base_id}").status_code == 403
        assert client.get(f"/groups/{base_id}/members").status_code == 403
        assert client.get(f"/groups/{base_id}/direct_members").status_code == 403
        assert client.get(f"/groups/{base_id}/member_of").status_code == 403
        assert client.post(f"/groups/{base_id}/members", json={"user_id": people[2]['id']}).status_code == 403
        assert client.delete(f"/groups/{base_id}/members/users/{people[2]['id']}").status_code == 403
        assert client.put(f"/groups/{base_id}", json={"description": "x"}).status_code == 403

    def test_group_listing_shows_only_what_the_user_administers(self, owned, make_group, client_as):
        client = client_as(owned['owner'])
        make_group()  # unrelated

        listed = client.get("/groups?page_size=1000")
        assert listed.status_code == 200
        assert [g['id'] for g in listed.json()] == [owned['base']['id']]

    def test_removed_owner_loses_access(self, existing_admin_client, owned, client_as):
        client = client_as(owned['owner'])
        assert client.get(f"/groups/{owned['base']['id']}").status_code == 200

        existing_admin_client.delete(f"/groups/{owned['owners']['id']}/members/users/{owned['owner']['id']}")
        assert client.get(f"/groups/{owned['base']['id']}").status_code == 403

    def test_owners_through_a_nested_group(self, existing_admin_client, owned, people, make_group, group_member, client_as):
        """Effective members of the owner group are owners, however they got there"""
        team = make_group()
        group_member(team['id'], user_id=people[3]['id'])
        group_member(owned['owners']['id'], member_group_id=team['id'])

        client = client_as(people[3])
        assert client.get(f"/groups/{owned['base']['id']}").status_code == 200


class TestDefaultAdministrationStructure:

    def _groups_by_name(self, client, *names):
        found = {}
        for name in names:
            [group] = client.get(f"/groups?name=eq.{name}").json()
            found[name] = group
        return found

    def test_owners_and_managers(self, existing_admin_client, make_group):
        base = make_group(administration="owners_and_managers")
        found = self._groups_by_name(existing_admin_client, f"{base['name']}_owners", f"{base['name']}_managers")
        owners, managers = found[f"{base['name']}_owners"], found[f"{base['name']}_managers"]

        # O is owned by staff, O owns M, M owns B
        assert owners['owner_group_id'] is None
        assert managers['owner_group_id'] == owners['id']
        assert base['owner_group_id'] == managers['id']

        # O is a member of M, and nothing else is a member of anything
        [row] = existing_admin_client.get(f"/groups/{managers['id']}/direct_members").json()
        assert row['member_group']['id'] == owners['id'] and row['member_user'] is None
        assert existing_admin_client.get(f"/groups/{owners['id']}/direct_members").json() == []
        assert existing_admin_client.get(f"/groups/{base['id']}/direct_members").json() == []

        # Administrators are not members of B
        assert _member_ids(existing_admin_client, base['id']) == set()

        # The generated groups are plain groups with no unix_gid
        assert owners['unix_gid'] is None and managers['unix_gid'] is None

        for generated in (owners, managers):
            existing_admin_client.delete(f"/groups/{generated['id']}")

    def test_owners_only(self, existing_admin_client, make_group):
        base = make_group(administration="owners")
        [owners] = existing_admin_client.get(f"/groups?name=eq.{base['name']}_owners").json()

        assert owners['owner_group_id'] is None
        assert base['owner_group_id'] == owners['id']
        assert existing_admin_client.get(f"/groups?name=eq.{base['name']}_managers").json() == []

        existing_admin_client.delete(f"/groups/{owners['id']}")

    def test_administration_cannot_be_combined_with_an_owner(self, existing_admin_client, make_group):
        owner = make_group()
        response = existing_admin_client.post("/groups", json={
            "name": f"conflict-{random.randint(0, 10**7)}",
            "owner_group_id": owner['id'],
            "administration": "owners",
        })
        assert response.status_code == 400

    def test_unknown_administration_is_rejected(self, existing_admin_client):
        response = existing_admin_client.post("/groups", json={"name": "never", "administration": "everyone"})
        assert response.status_code == 422

    def test_generated_names_are_truncated_and_deduplicated(self, existing_admin_client, make_group):
        # 25 shared characters: "<prefix>_owners" is exactly 32, so both groups want the same owners name
        prefix = "y" * 20 + str(random.randint(10000, 99999))
        first = make_group(name=prefix + "AAAAAAA", administration="owners")
        second = make_group(name=prefix + "BBBBBBB", administration="owners")

        first_owners = existing_admin_client.get(f"/groups/{first['owner_group_id']}").json()
        second_owners = existing_admin_client.get(f"/groups/{second['owner_group_id']}").json()
        assert first_owners['name'] == prefix + "_owners"
        assert len(second_owners['name']) <= 32
        assert second_owners['name'] != first_owners['name']
        assert second_owners['name'].endswith("_2")

        existing_admin_client.delete(f"/groups/{first_owners['id']}")
        existing_admin_client.delete(f"/groups/{second_owners['id']}")

    def test_who_can_edit_what_in_the_chain(self, existing_admin_client, make_group, people, group_member, client_as):
        base = make_group(administration="owners_and_managers")
        managers = existing_admin_client.get(f"/groups/{base['owner_group_id']}").json()
        owners = existing_admin_client.get(f"/groups/{managers['owner_group_id']}").json()
        group_member(owners['id'], user_id=people[0]['id'])      # an owner
        group_member(managers['id'], user_id=people[1]['id'])    # a manager

        owner_client = client_as(people[0])
        manager_client = client_as(people[1])

        # Owners edit B (they are members of M) and M (they own it)
        assert owner_client.post(f"/groups/{base['id']}/members", json={"user_id": people[2]['id']}).status_code == 201
        assert owner_client.post(f"/groups/{managers['id']}/members", json={"user_id": people[3]['id']}).status_code == 201

        # Managers edit B but cannot add managers, because they do not own M
        assert manager_client.delete(f"/groups/{base['id']}/members/users/{people[2]['id']}").status_code == 204
        assert manager_client.post(f"/groups/{base['id']}/members", json={"user_id": people[2]['id']}).status_code == 201
        assert manager_client.post(f"/groups/{managers['id']}/members", json={"user_id": people[2]['id']}).status_code == 403

        for generated in (owners, managers):
            existing_admin_client.delete(f"/groups/{generated['id']}")


class TestProjectGroups:

    def test_project_creation_builds_the_project_groups(self, existing_admin_client, project, people):
        full = existing_admin_client.get(f"/projects/{project['id']}").json()
        pi_id, project_group_id = full['pi_group_id'], full['project_group_id']
        assert pi_id and project_group_id

        pi = existing_admin_client.get(f"/groups/{pi_id}").json()
        project_group = existing_admin_client.get(f"/groups/{project_group_id}").json()
        managers = existing_admin_client.get(f"/groups/{project_group['owner_group_id']}").json()

        # pi has no owner and owns managers, managers owns the project group
        assert pi['owner_group_id'] is None
        assert managers['owner_group_id'] == pi_id
        assert project_group['owner_group_id'] == managers['id']
        assert pi['name'].endswith("_pi") and managers['name'].endswith("_managers")

        # pi is a member of both managers and the project group
        for group_id in (managers['id'], project_group_id):
            group_rows = existing_admin_client.get(f"/groups/{group_id}/direct_members").json()
            assert [r['member_group']['id'] for r in group_rows if r['member_group']] == [pi_id]

    def test_users_created_with_a_project_are_members_of_its_group(self, existing_admin_client, project, people):
        project_group_id = existing_admin_client.get(f"/projects/{project['id']}").json()['project_group_id']

        members = existing_admin_client.get(f"/groups/{project_group_id}/members").json()
        assert {m['user_id'] for m in members} == {p['id'] for p in people}
        assert all(m['direct'] for m in members)

        user = existing_admin_client.get(f"/users/{people[0]['id']}").json()
        assert user['primary_project_id'] == project['id']
        assert [p['project_id'] for p in user['projects']] == [project['id']]
        assert user['projects'][0]['is_primary'] is True


class TestSoftDelete:

    @pytest.fixture
    def web(self, existing_admin_client, make_group, people, group_member):
        """victim, with a user member and a group member, that is itself a member of parent and owns child"""
        parent, child, inner = make_group(), make_group(), make_group()
        victim = make_group()
        group_member(victim['id'], user_id=people[0]['id'])
        group_member(inner['id'], user_id=people[1]['id'])
        group_member(victim['id'], member_group_id=inner['id'])
        group_member(parent['id'], member_group_id=victim['id'])
        assert existing_admin_client.put(f"/groups/{child['id']}", json={"owner_group_id": victim['id']}).status_code == 200
        return {"victim": victim, "parent": parent, "child": child, "inner": inner}

    def test_delete_removes_memberships_in_both_directions(self, existing_admin_client, web, people):
        client = existing_admin_client
        assert _member_ids(client, web['parent']['id']) == {people[0]['id'], people[1]['id']}

        assert client.delete(f"/groups/{web['victim']['id']}").status_code == 204

        assert client.get(f"/groups/{web['victim']['id']}/direct_members").json() == []
        assert client.get(f"/groups/{web['parent']['id']}/direct_members").json() == []
        assert _member_ids(client, web['parent']['id']) == set()
        # The group that was inside is untouched
        assert _member_ids(client, web['inner']['id']) == {people[1]['id']}
        # No longer in the users' groups either
        assert web['victim']['id'] not in {g['group_id'] for g in client.get(f"/users/{people[0]['id']}/groups").json()}

    def test_delete_clears_ownership(self, existing_admin_client, web):
        existing_admin_client.delete(f"/groups/{web['victim']['id']}")

        child = existing_admin_client.get(f"/groups/{web['child']['id']}").json()
        assert child['owner_group_id'] is None, "A group whose owner is deleted becomes staff-only"
        # Deleting a group does not delete the groups it owned
        assert child['deleted_at'] is None

    def test_delete_clears_access_references(self, existing_admin_client, web, project):
        victim_id = web['victim']['id']
        submit_node = existing_admin_client.post("/submit_nodes", json={"name": f"sn-{random.randint(0, 10**7)}", "group_id": victim_id}).json()
        assert existing_admin_client.put(f"/projects/{project['id']}", json={"pi_group_id": victim_id}).status_code == 200

        try:
            assert existing_admin_client.delete(f"/groups/{victim_id}").status_code == 204

            assert existing_admin_client.get(f"/submit_nodes?id=eq.{submit_node['id']}").json()[0]['group_id'] is None
            assert existing_admin_client.get(f"/projects/{project['id']}").json()['pi_group_id'] is None

            changes = {(r['details']['entity'], r['details']['entity_id']) for r in _audit(victim_id, 'metadata_changed')}
            assert changes == {('submit_node', submit_node['id']), ('project', project['id'])}
        finally:
            existing_admin_client.delete(f"/submit_nodes/{submit_node['id']}")

    def test_delete_writes_audit_rows_with_caused_by_chains(self, existing_admin_client, existing_admin_user, web, people):
        victim_id = web['victim']['id']
        existing_admin_client.delete(f"/groups/{victim_id}")

        [deleted] = _audit(victim_id, 'group_deleted')
        assert deleted['actor_id'] == existing_admin_user['id']
        assert deleted['caused_by'] is None

        # Both of the group's members, and its membership in parent
        removed = _sql(
            "SELECT group_id, member_user_id, member_group_id, caused_by, details FROM audit_log "
            "WHERE action = 'member_removed' AND caused_by = :c ORDER BY id",
            c=deleted['id'],
        )
        assert {(r['group_id'], r['member_user_id'], r['member_group_id']) for r in removed} == {
            (victim_id, people[0]['id'], None),
            (victim_id, None, web['inner']['id']),
            (web['parent']['id'], None, victim_id),
        }
        assert all(r['details']['reason'] == 'group_deleted' for r in removed)

        # The owned group's owner reference
        [owner_change] = [r for r in _audit(web['child']['id'], 'owner_group_changed') if r['caused_by'] == deleted['id']]
        assert owner_change['details'] == {"old": victim_id, "new": None, "reason": "group_deleted"}

    def test_deleted_groups_are_hidden_unless_requested(self, existing_admin_client, web):
        victim_id = web['victim']['id']
        existing_admin_client.delete(f"/groups/{victim_id}")

        assert existing_admin_client.get(f"/groups?id=eq.{victim_id}").json() == []
        assert existing_admin_client.get(f"/groups?id=eq.{victim_id}&include_deleted=false").json() == []
        [with_deleted] = existing_admin_client.get(f"/groups?id=eq.{victim_id}&include_deleted=true").json()
        assert with_deleted['deleted_at'] is not None

    def test_deleted_group_cannot_be_used(self, existing_admin_client, web, people):
        victim_id = web['victim']['id']
        existing_admin_client.delete(f"/groups/{victim_id}")

        assert existing_admin_client.post(f"/groups/{victim_id}/members", json={"user_id": people[2]['id']}).status_code == 404
        assert existing_admin_client.post(f"/groups/{web['parent']['id']}/members", json={"group_id": victim_id}).status_code == 404
        assert existing_admin_client.put(f"/groups/{web['child']['id']}", json={"owner_group_id": victim_id}).status_code == 404
        assert existing_admin_client.put(f"/groups/{victim_id}", json={"description": "zombie"}).status_code == 404
        assert existing_admin_client.put(f"/groups/{victim_id}", json={"managed_by": "MANIFEST"}).status_code == 404
        new_name = f"orphan-{random.randint(0, 10**7)}"
        assert existing_admin_client.post("/groups", json={"name": new_name, "owner_group_id": victim_id}).status_code == 404
        assert existing_admin_client.get(f"/groups?name=eq.{new_name}").json() == [], "nothing was created"
        assert existing_admin_client.get(f"/groups/{web['inner']['id']}/member_of").json() == []

    def test_deleted_group_stops_granting_ownership(self, existing_admin_client, make_group, people, group_member, client_as):
        owners = make_group()
        base = make_group(owner_group_id=owners['id'])
        group_member(owners['id'], user_id=people[0]['id'])
        client = client_as(people[0])
        assert client.get(f"/groups/{base['id']}").status_code == 200

        existing_admin_client.delete(f"/groups/{owners['id']}")
        assert client.get(f"/groups/{base['id']}").status_code == 403


class TestAuditTrail:

    def test_member_added_and_removed(self, existing_admin_client, existing_admin_user, make_group, people):
        group = make_group()
        user = people[0]
        other = make_group()

        existing_admin_client.post(f"/groups/{group['id']}/members", json={"user_id": user['id']})
        existing_admin_client.post(f"/groups/{group['id']}/members", json={"group_id": other['id']})
        existing_admin_client.delete(f"/groups/{group['id']}/members/users/{user['id']}")
        existing_admin_client.delete(f"/groups/{group['id']}/members/groups/{other['id']}")

        added = _audit(group['id'], 'member_added')
        assert [(r['member_user_id'], r['member_group_id']) for r in added] == [(user['id'], None), (None, other['id'])]
        assert added[0]['actor_id'] == existing_admin_user['id']
        assert all(r['details'] is None for r in added), "A plain membership change carries no details"

        removed = _audit(group['id'], 'member_removed')
        assert [(r['member_user_id'], r['member_group_id']) for r in removed] == [(user['id'], None), (None, other['id'])]

    def test_failed_writes_leave_no_audit_row(self, existing_admin_client, make_group, people, group_member):
        group = make_group()
        group_member(group['id'], user_id=people[0]['id'])
        existing_admin_client.post(f"/groups/{group['id']}/members", json={"user_id": people[0]['id']})  # 409
        existing_admin_client.delete(f"/groups/{group['id']}/members/users/{people[1]['id']}")  # 404

        assert len(_audit(group['id'], 'member_added')) == 1
        assert _audit(group['id'], 'member_removed') == []

    def test_group_created(self, existing_admin_client, existing_admin_user, make_group):
        group = make_group(description="d")

        [created] = _audit(group['id'], 'group_created')
        assert created['actor_id'] == existing_admin_user['id']
        assert created['details'] == {"name": group['name'], "owner_group_id": None}

    def test_group_created_with_administration_chains_to_the_base_group(self, existing_admin_client, make_group):
        base = make_group(administration="owners_and_managers")
        managers_id = base['owner_group_id']
        owners_id = existing_admin_client.get(f"/groups/{managers_id}").json()['owner_group_id']

        [base_entry] = _audit(base['id'], 'group_created')
        assert base_entry['caused_by'] is None

        [owners_entry] = _audit(owners_id, 'group_created')
        [managers_entry] = _audit(managers_id, 'group_created')
        assert owners_entry['caused_by'] == base_entry['id'] and managers_entry['caused_by'] == base_entry['id']
        assert owners_entry['details']['created_for'] == {"entity": "group", "entity_id": base['id'], "role": "owners"}
        assert managers_entry['details']['created_for'] == {"entity": "group", "entity_id": base['id'], "role": "managers"}

        # Making O a member of M is audited too, as part of the same creation
        [added] = _audit(managers_id, 'member_added')
        assert added['member_group_id'] == owners_id and added['caused_by'] == base_entry['id']

        for group_id in (managers_id, owners_id):
            existing_admin_client.delete(f"/groups/{group_id}")

    def test_project_groups_are_audited(self, existing_admin_client, project):
        full = existing_admin_client.get(f"/projects/{project['id']}").json()
        roles = {}
        for group_id in (full['pi_group_id'], full['project_group_id']):
            [entry] = _audit(group_id, 'group_created')
            assert entry['details']['created_for']['entity'] == 'project'
            assert entry['details']['created_for']['entity_id'] == project['id']
            roles[entry['details']['created_for']['role']] = group_id
        assert roles == {"pi": full['pi_group_id'], "project": full['project_group_id']}

    def test_owner_group_changed(self, existing_admin_client, existing_admin_user, make_group):
        a, b = make_group(), make_group()
        group = make_group()

        existing_admin_client.put(f"/groups/{group['id']}", json={"owner_group_id": a['id']})
        existing_admin_client.put(f"/groups/{group['id']}", json={"owner_group_id": b['id']})
        existing_admin_client.put(f"/groups/{group['id']}", json={"owner_group_id": b['id']})  # no change
        existing_admin_client.put(f"/groups/{group['id']}", json={"owner_group_id": None})

        changes = _audit(group['id'], 'owner_group_changed')
        assert [r['details'] for r in changes] == [
            {"old": None, "new": a['id']},
            {"old": a['id'], "new": b['id']},
            {"old": b['id'], "new": None},
        ]
        assert all(r['actor_id'] == existing_admin_user['id'] for r in changes)

    def test_metadata_changed(self, existing_admin_client, existing_admin_user, make_group):
        group = make_group(description="before")

        gid = random.randint(56000, 59000)
        existing_admin_client.put(f"/groups/{group['id']}", json={"description": "after", "unix_gid": gid})
        existing_admin_client.put(f"/groups/{group['id']}", json={"description": "after"})  # no change

        [entry] = _audit(group['id'], 'metadata_changed')
        assert entry['actor_id'] == existing_admin_user['id']
        assert entry['details'] == {
            "entity": "group",
            "entity_id": group['id'],
            "changes": {
                "description": {"old": "before", "new": "after"},
                "unix_gid": {"old": None, "new": gid},
            },
        }

    def test_owner_member_add_is_attributed_to_the_owner(self, existing_admin_client, make_group, people, group_member, client_as):
        owners = make_group()
        base = make_group(owner_group_id=owners['id'])
        group_member(owners['id'], user_id=people[0]['id'])

        client = client_as(people[0])
        client.post(f"/groups/{base['id']}/members", json={"user_id": people[1]['id']})

        assert _audit(base['id'], 'member_added')[0]['actor_id'] == people[0]['id']

    def test_group_managed_by_change_is_audited(self, existing_admin_client, make_group):
        group = make_group()
        existing_admin_client.put(f"/groups/{group['id']}", json={"managed_by": "MANIFEST"})

        [entry] = _audit(group['id'], 'metadata_changed')
        assert entry['details'] == {"entity": "group", "entity_id": group['id'], "changes": {"managed_by": {"old": "APPLICATION", "new": "MANIFEST"}}}


class TestMembershipLock:

    def test_service_functions_share_the_documented_lock_key(self):
        from userapp.core.services import membership
        assert membership.EFFECTIVE_MEMBERSHIP_LOCK_KEY == 0x55534552

    def test_slugify_and_names(self):
        from userapp.core.services.membership import slugify_group_name
        assert slugify_group_name("Genome Lab!!") == "genome_lab"
        assert slugify_group_name("--a  b--") == "a_b"
        assert slugify_group_name("Ünï") == "n"
