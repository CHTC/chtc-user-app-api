"""GET /unix_groups: live groups with a unix_gid and their flattened effective members"""
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



def _gid() -> int:
    # Deleted groups keep their gid forever, so draw from a wide range
    return random.randint(41000, 54999)


def _by_id(client) -> dict:
    response = client.get("/unix_groups")
    assert response.status_code == 200, response.text
    return {g['id']: g for g in response.json()}


class TestUnixGroups:

    def test_members_are_flattened_distinct_and_sorted(self, existing_admin_client, make_group, people, group_member):
        top, inner = make_group(unix_gid=_gid()), make_group()
        # people[0] reaches top twice (directly and through inner) but is listed once
        group_member(top['id'], user_id=people[0]['id'])
        group_member(inner['id'], user_id=people[0]['id'])
        group_member(inner['id'], user_id=people[1]['id'])
        group_member(top['id'], member_group_id=inner['id'])

        groups = _by_id(existing_admin_client)
        assert groups[top['id']] == {
            "id": top['id'], "name": top['name'], "unix_gid": top['unix_gid'],
            "members": sorted([people[0]['username'], people[1]['username']]),
        }
        # inner has no gid, so it is not a unix group however many members it has
        assert inner['id'] not in groups

    def test_group_without_members_has_empty_list(self, existing_admin_client, make_group):
        group = make_group(unix_gid=_gid())
        assert _by_id(existing_admin_client)[group['id']]['members'] == []

    def test_deleted_groups_are_omitted(self, existing_admin_client, make_group):
        group = make_group(unix_gid=_gid())
        assert group['id'] in _by_id(existing_admin_client)
        existing_admin_client.delete(f"/groups/{group['id']}")
        assert group['id'] not in _by_id(existing_admin_client)

    def test_users_without_a_username_are_skipped(self, existing_admin_client, make_group, people, group_member):
        group = make_group(unix_gid=_gid())
        group_member(group['id'], user_id=people[0]['id'])
        group_member(group['id'], user_id=people[1]['id'])
        assert existing_admin_client.patch(f"/users/{people[1]['id']}", json={"username": None}).status_code == 200

        assert _by_id(existing_admin_client)[group['id']]['members'] == [people[0]['username']]

    def test_groups_are_sorted_by_gid(self, existing_admin_client, make_group):
        make_group(unix_gid=_gid()), make_group(unix_gid=_gid())
        gids = [g['unix_gid'] for g in existing_admin_client.get("/unix_groups").json()]
        assert gids == sorted(gids)

    def test_removed_member_disappears(self, existing_admin_client, make_group, people, group_member):
        group = make_group(unix_gid=_gid())
        group_member(group['id'], user_id=people[0]['id'])
        existing_admin_client.delete(f"/groups/{group['id']}/members/users/{people[0]['id']}")
        assert _by_id(existing_admin_client)[group['id']]['members'] == []


class TestUnixGroupsSecurity:

    def test_non_staff_is_refused(self, nonadmin_client):
        assert nonadmin_client.get("/unix_groups").status_code == 403

    def test_anonymous_is_refused(self, api_client):
        assert api_client.get("/unix_groups").status_code == 403
