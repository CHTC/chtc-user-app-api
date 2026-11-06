"""Read-only audit log routes: global, per group and per user"""
import random
from datetime import datetime, timedelta

import pytest

from userapp.api.tests.conftest import _make_auth_client


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
    users = [user_factory(i, project['id']) for i in range(3)]
    yield users
    for user in users:
        existing_admin_client.delete(f"/users/{user['id']}")


@pytest.fixture
def client_as():
    generators = []

    def _make(user: dict):
        generator = _make_auth_client({"id": user["id"], "is_admin": False})
        client = next(generator)
        generators.append(generator)
        return client

    yield _make

    for generator in generators:
        generator.close()


def _entries(client, url: str, **params) -> list[dict]:
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_global_routes_are_staff_only(api_client, nonadmin_client, existing_admin_client, make_group, people, group_member):
    group = make_group()
    group_member(group['id'], user_id=people[0]['id'])
    entry = _entries(existing_admin_client, "/audit_log", group_id=f"eq.{group['id']}")[0]

    for url in ("/audit_log", f"/audit_log/{entry['id']}"):
        assert nonadmin_client.get(url).status_code == 403
        assert api_client.get(url).status_code == 403
        assert existing_admin_client.get(url).status_code == 200


def test_unknown_entry_is_404(existing_admin_client):
    assert existing_admin_client.get("/audit_log/999999999").status_code == 404


def test_newest_first_and_total_count(existing_admin_client, make_group, people, group_member):
    group = make_group()
    for person in people:
        group_member(group['id'], user_id=person['id'])

    response = existing_admin_client.get("/audit_log", params={"group_id": f"eq.{group['id']}"})
    assert response.status_code == 200
    rows = response.json()
    # group_created, then three member_added
    assert response.headers["X-Total-Count"] == "4" == str(len(rows))
    ids = [r['id'] for r in rows]
    assert ids == sorted(ids, reverse=True)
    assert [r['action'] for r in rows] == ["member_added"] * 3 + ["group_created"]

    page = existing_admin_client.get("/audit_log", params={"group_id": f"eq.{group['id']}", "page_size": 2, "page": 1})
    assert [r['id'] for r in page.json()] == ids[2:]
    assert page.headers["X-Total-Count"] == "4"


def test_filters(existing_admin_client, make_group, people, group_member):
    group = make_group()
    other = make_group()
    group_member(group['id'], user_id=people[0]['id'])
    group_member(other['id'], user_id=people[0]['id'])

    added = _entries(existing_admin_client, "/audit_log", action="eq.member_added", group_id=f"eq.{group['id']}")
    assert len(added) == 1
    assert added[0]['member_user_id'] == people[0]['id']

    created = _entries(existing_admin_client, "/audit_log", action="eq.group_created", group_id=f"eq.{other['id']}")
    assert [r['group_id'] for r in created] == [other['id']]

    future = (datetime.utcnow() + timedelta(days=1)).isoformat()
    assert _entries(existing_admin_client, "/audit_log", group_id=f"eq.{group['id']}", occurred_at=f"gt.{future}") == []
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    assert len(_entries(existing_admin_client, "/audit_log", group_id=f"eq.{group['id']}", occurred_at=f"gt.{past}")) == 2
    assert existing_admin_client.get("/audit_log", params={"occurred_at": "gt.yesterday"}).status_code == 400


def test_get_one_nests_actor_member_and_ids(existing_admin_client, existing_admin_user, make_group, people, group_member):
    group = make_group()
    inner = make_group()
    group_member(group['id'], user_id=people[0]['id'])
    group_member(group['id'], member_group_id=inner['id'])

    rows = _entries(existing_admin_client, "/audit_log", action="eq.member_added", group_id=f"eq.{group['id']}")
    by_kind = {("user" if r['member_user_id'] else "group"): r for r in rows}

    user_entry = existing_admin_client.get(f"/audit_log/{by_kind['user']['id']}").json()
    assert user_entry['actor']['id'] == existing_admin_user['id']
    assert user_entry['actor_id'] == existing_admin_user['id']
    assert user_entry['member_user']['id'] == people[0]['id']
    assert user_entry['member_group'] is None
    assert user_entry['details'] is None

    group_entry = existing_admin_client.get(f"/audit_log/{by_kind['group']['id']}").json()
    assert group_entry['member_group']['id'] == inner['id']
    assert group_entry['member_user'] is None


def test_group_route_shows_group_as_target_and_as_member(existing_admin_client, make_group, group_member):
    x = make_group()
    y = make_group()
    group_member(y['id'], member_group_id=x['id'])

    for group in (x, y):
        rows = _entries(existing_admin_client, f"/groups/{group['id']}/audit_log")
        added = [r for r in rows if r['action'] == "member_added"]
        assert len(added) == 1
        assert (added[0]['group_id'], added[0]['member_group_id']) == (y['id'], x['id'])
    # x also has its own creation entry; y's does not leak into x's log
    x_rows = _entries(existing_admin_client, f"/groups/{x['id']}/audit_log")
    assert {r['group_id'] for r in x_rows} == {x['id'], y['id']}
    assert x_rows[0]['id'] > x_rows[-1]['id']

    # filters and the total apply on top of the group condition
    only = existing_admin_client.get(f"/groups/{x['id']}/audit_log", params={"action": "eq.group_created"})
    assert only.headers["X-Total-Count"] == "1"


def test_group_route_unknown_group_is_404(existing_admin_client):
    assert existing_admin_client.get("/groups/999999999/audit_log").status_code == 404


def test_group_owner_can_read_and_stranger_cannot(existing_admin_client, client_as, make_group, people, group_member):
    group = make_group(administration="owners")
    owners_id = existing_admin_client.get(f"/groups/{group['id']}").json()['owner_group_id']
    group_member(owners_id, user_id=people[0]['id'])

    rows = _entries(client_as(people[0]), f"/groups/{group['id']}/audit_log")
    assert "group_created" in [r['action'] for r in rows]

    assert client_as(people[1]).get(f"/groups/{group['id']}/audit_log").status_code == 403


def test_deleted_group_log_is_readable_by_staff(existing_admin_client, group_factory):
    group = group_factory()
    assert existing_admin_client.delete(f"/groups/{group['id']}").status_code == 204

    rows = _entries(existing_admin_client, f"/groups/{group['id']}/audit_log")
    assert [r['action'] for r in rows] == ["group_deleted", "group_created"]


def test_user_route_as_member_and_as_actor(existing_admin_client, existing_admin_user, client_as, make_group, people, group_member):
    group = make_group()
    group_member(group['id'], user_id=people[0]['id'])

    as_member = _entries(existing_admin_client, f"/users/{people[0]['id']}/audit_log", action="eq.member_added", group_id=f"eq.{group['id']}")
    assert [(r['group_id'], r['member_user_id']) for r in as_member] == [(group['id'], people[0]['id'])]

    # The staff user did the adding and the creating
    as_actor = _entries(existing_admin_client, f"/users/{existing_admin_user['id']}/audit_log", group_id=f"eq.{group['id']}")
    assert {r['action'] for r in as_actor} == {"group_created", "member_added"}
    assert all(r['actor_id'] == existing_admin_user['id'] for r in as_actor)

    # A non-staff user reads their own log only
    own = client_as(people[0])
    assert any(r['group_id'] == group['id'] for r in _entries(own, f"/users/{people[0]['id']}/audit_log"))
    assert own.get(f"/users/{people[1]['id']}/audit_log").status_code == 403


def test_user_route_shows_primary_project_changes(existing_admin_client, client_as, people, project):
    """The user is the member of their own primary-project entries, so their log is complete"""
    user = people[0]  # created with the project as primary
    assert existing_admin_client.patch(f"/users/{user['id']}", json={"primary_project_id": None}).status_code == 200

    own = _entries(client_as(user), f"/users/{user['id']}/audit_log", action="eq.metadata_changed")
    changes = [r['details']['changes']['primary_project_id'] for r in own if r['details'].get('entity') == 'user']
    assert sorted(changes, key=lambda c: c['old'] or 0) == [
        {"old": None, "new": project['id']}, {"old": project['id'], "new": None},
    ]
    assert all(r['member_user_id'] == user['id'] for r in own)


def test_user_route_unknown_user_is_404(existing_admin_client):
    assert existing_admin_client.get("/users/999999999/audit_log").status_code == 404


def test_caused_by_chain_from_group_deletion(existing_admin_client, make_group, people, group_member):
    group = make_group()
    member_of = make_group()
    group_member(group['id'], user_id=people[0]['id'])
    group_member(member_of['id'], member_group_id=group['id'])
    assert existing_admin_client.delete(f"/groups/{group['id']}").status_code == 204

    rows = _entries(existing_admin_client, f"/groups/{group['id']}/audit_log")
    deleted = next(r for r in rows if r['action'] == "group_deleted")
    removed = [r for r in rows if r['action'] == "member_removed"]
    assert len(removed) == 2
    for row in removed:
        assert row['caused_by'] == deleted['id']
        assert row['details']['reason'] == "group_deleted"
        # the pointer resolves through the global route
        assert existing_admin_client.get(f"/audit_log/{row['caused_by']}").json()['action'] == "group_deleted"


def test_details_round_trip_as_json(existing_admin_client, make_group):
    group = make_group()
    gid = random.randint(41000, 59000)
    response = existing_admin_client.put(f"/groups/{group['id']}", json={"description": "new text", "unix_gid": gid})
    assert response.status_code == 200, response.text

    changed = _entries(existing_admin_client, "/audit_log", action="eq.metadata_changed", group_id=f"eq.{group['id']}")
    assert len(changed) == 1
    assert changed[0]['details'] == {
        "entity": "group",
        "entity_id": group['id'],
        "changes": {
            "description": {"old": None, "new": "new text"},
            "unix_gid": {"old": None, "new": gid},
        },
    }
