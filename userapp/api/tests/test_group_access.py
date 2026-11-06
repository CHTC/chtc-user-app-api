"""GET /groups/{id}/access: the access objects a group reaches directly and through groups it is a member of"""
import asyncio
import random

import pytest
from sqlalchemy import text

from userapp.api.tests.conftest import _make_auth_client, _seed_db_url
from userapp.db import connect_engine


def _sql(sql: str, **params) -> list[dict]:
    """Raw SQL against the test database, for reading the audit log without depending on its API"""

    async def run():
        engine = await connect_engine(_seed_db_url())
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(sql), params)
                return [dict(row._mapping) for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _metadata_audit(entity: str, entity_id: int) -> list[dict]:
    return _sql(
        "SELECT id, actor_id, group_id, details FROM audit_log "
        "WHERE action = 'metadata_changed' AND details->>'entity' = :e AND (details->>'entity_id')::int = :i "
        "ORDER BY id",
        e=entity, i=entity_id,
    )


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



@pytest.fixture
def node_for(existing_admin_client):
    created = []

    def _make(group_id: int) -> dict:
        response = existing_admin_client.post("/submit_nodes", json={"name": f"node-{random.randint(1, 10**8)}", "group_id": group_id})
        assert response.status_code == 201, response.text
        created.append(response.json())
        return response.json()

    yield _make
    for node in created:
        existing_admin_client.delete(f"/submit_nodes/{node['id']}")


def _access(client, group_id: int) -> dict:
    response = client.get(f"/groups/{group_id}/access")
    assert response.status_code == 200, response.text
    return response.json()


class TestGroupAccess:

    def test_group_with_nothing_attached(self, existing_admin_client, make_group):
        group = make_group()
        assert _access(existing_admin_client, group['id']) == {"projects": [], "submit_nodes": []}

    def test_objects_on_the_group_itself_have_no_via(self, existing_admin_client, make_group, node_for):
        group = make_group()
        node = node_for(group['id'])

        access = _access(existing_admin_client, group['id'])
        assert access['submit_nodes'] == [{"id": node['id'], "name": node['name'], "group_id": group['id'], "via": []}]

    def test_objects_reached_through_nested_membership(self, existing_admin_client, make_group, group_member, node_for):
        # a is a member of b, b is a member of c, and a is also a direct member of c
        a, b, c = make_group(), make_group(), make_group()
        group_member(b['id'], member_group_id=a['id'])
        group_member(c['id'], member_group_id=b['id'])
        group_member(c['id'], member_group_id=a['id'])
        on_a, on_b, on_c = node_for(a['id']), node_for(b['id']), node_for(c['id'])
        # Reaches a's members only if the relation is read in the right direction
        below = make_group()
        group_member(a['id'], member_group_id=below['id'])
        node_below = node_for(below['id'])

        access = _access(existing_admin_client, a['id'])
        assert {n['id']: n['via'] for n in access['submit_nodes']} == {
            on_a['id']: [],
            on_b['id']: [[b['id'], a['id']]],
            on_c['id']: [[c['id'], a['id']], [c['id'], b['id'], a['id']]],
        }
        assert node_below['id'] not in {n['id'] for n in access['submit_nodes']}
        assert [n['id'] for n in access['submit_nodes']] == sorted(n['id'] for n in access['submit_nodes'])

    def test_project_found_through_nested_membership(self, existing_admin_client, project, make_group, group_member):
        # The project's own groups are created with it; a new group inside its project group reaches the project
        project = existing_admin_client.get(f"/projects/{project['id']}").json()
        member = make_group()
        group_member(project['project_group_id'], member_group_id=member['id'])

        access = _access(existing_admin_client, member['id'])
        assert access['projects'] == [{
            "project_id": project['id'], "name": project['name'], "display_name": project['display_name'],
            "as": "project_group", "group_id": project['project_group_id'],
            "via": [[project['project_group_id'], member['id']]],
        }]

    def test_pi_group_and_project_group_are_separate_rows(self, existing_admin_client, project, make_group):
        project = existing_admin_client.get(f"/projects/{project['id']}").json()
        # The pi group is a member of the project group, so asking about it reaches the project both ways
        access = _access(existing_admin_client, project['pi_group_id'])
        rows = [(p['project_id'], p['as'], p['group_id'], p['via']) for p in access['projects']]
        assert rows == [
            (project['id'], "pi_group", project['pi_group_id'], []),
            (project['id'], "project_group", project['project_group_id'], [[project['project_group_id'], project['pi_group_id']]]),
        ]

    def test_deleting_a_group_removes_its_objects_from_the_summary(self, existing_admin_client, make_group, node_for):
        group = make_group()
        node_for(group['id'])
        existing_admin_client.delete(f"/groups/{group['id']}")
        # A deleted group has no page; its objects now reference nothing
        assert existing_admin_client.get(f"/groups/{group['id']}/access").status_code == 200
        assert _access(existing_admin_client, group['id'])['submit_nodes'] == []


class TestGroupAccessSecurity:

    def test_unknown_group_is_404(self, existing_admin_client):
        assert existing_admin_client.get("/groups/99999999/access").status_code == 404

    def test_owner_may_view_but_a_stranger_may_not(self, make_group, people, group_member, client_as):
        owners = make_group()
        base = make_group(owner_group_id=owners['id'])
        group_member(owners['id'], user_id=people[0]['id'])

        assert client_as(people[0]).get(f"/groups/{base['id']}/access").status_code == 200
        assert client_as(people[1]).get(f"/groups/{base['id']}/access").status_code == 403

    def test_anonymous_is_refused(self, api_client, make_group):
        assert api_client.get(f"/groups/{make_group()['id']}/access").status_code == 403
