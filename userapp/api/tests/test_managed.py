"""
Tests for managed-sync endpoints:
  PUT /managed/manifest/projects/{id}/users
  PUT /managed/morgridge-ad/projects/{id}/users
  PUT /managed/manifest/groups/{id}/users
  PUT /managed/morgridge-ad/groups/{id}/users

Both managers share identical business logic so each test class is
parametrized over the two managers to avoid duplicate code.
"""
import pytest

from userapp.api.tests.conftest import audit_rows
from userapp.core.models.enum import EntityManagerEnum

# ---------------------------------------------------------------------------
# Parametrize markers
# ---------------------------------------------------------------------------

MANAGERS = [
    pytest.param("manifest", EntityManagerEnum.MANIFEST, id="manifest"),
    pytest.param("morgridge-ad", EntityManagerEnum.MORGRIDGE_AD, id="morgridge_ad"),
]


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def project_url(prefix: str, project_id: int) -> str:
    return f"/managed/{prefix}/projects/{project_id}/users"


def group_url(prefix: str, group_id: int) -> str:
    return f"/managed/{prefix}/groups/{group_id}/users"


# ---------------------------------------------------------------------------
# Project sync tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("manager_prefix,manager_enum", MANAGERS)
class TestManagedProjectSync:
    """Tests for PUT /managed/{manager}/projects/{id}/users."""

    def test_requires_admin(self, nonadmin_client, project, manager_prefix, manager_enum):
        """Non-admin requests are rejected with 403."""
        response = nonadmin_client.put(project_url(manager_prefix, project["id"]), json=[])
        assert response.status_code == 403

    def test_nonexistent_project_returns_404(self, existing_admin_client, manager_prefix, manager_enum):
        """Returns 404 when the project does not exist."""
        response = existing_admin_client.put(project_url(manager_prefix, 999_999_999), json=[])
        assert response.status_code == 404

    def test_nonexistent_user_returns_404(self, existing_admin_client, project, manager_prefix, manager_enum):
        """Returns 404 when a user_id in the body does not exist."""
        response = existing_admin_client.put(
            project_url(manager_prefix, project["id"]),
            json=[{"user_id": 999_999_999, "is_primary": False}],
        )
        assert response.status_code == 404

    def test_duplicate_user_id_returns_422(self, existing_admin_client, project, manager_prefix, manager_enum):
        """Returns 422 when the same user_id appears more than once in the request.

        Duplicate detection runs before user-existence checks, so a non-existent
        id is sufficient here.
        """
        response = existing_admin_client.put(
            project_url(manager_prefix, project["id"]),
            json=[
                {"user_id": 1, "is_primary": False},
                {"user_id": 1, "is_primary": True},
            ],
        )
        assert response.status_code == 422

    def test_empty_list_on_clean_project_returns_empty(
        self, existing_admin_client, project, manager_prefix, manager_enum
    ):
        """PUT [] on a project that has no managed rows returns 200 with an empty list."""
        response = existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[])
        assert response.status_code == 200
        assert response.json() == []

    def test_sync_adds_users(
        self, existing_admin_client, project, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """Users in the request body that are not already in the project get added."""
        # Create user whose primary project is a *different* project so they
        # are not already a member of the test project.
        side_project = project_factory()
        user = user_factory(0, side_project["id"])
        try:
            response = existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "is_primary": False}],
            )
            assert response.status_code == 200, response.text
            data = response.json()
            matched = [r for r in data if r["id"] == user["id"]]
            assert len(matched) == 1, "Synced user should appear in the response"
            assert matched[0]["project_id"] == project["id"]
            assert matched[0]["direct"] is True
            # The sync claimed the project group
            assert existing_admin_client.get(f"/groups/{project['project_group_id']}").json()["managed_by"] == manager_enum.value
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")
            existing_admin_client.delete(f"/projects/{side_project['id']}")

    def test_sync_removes_users_absent_from_new_list(
        self, existing_admin_client, project, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """Users that were previously managed but are absent from the new PUT body are removed."""
        side_project = project_factory()
        user = user_factory(0, side_project["id"])
        try:
            # First sync: add the user
            existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "is_primary": False}],
            )
            # Second sync: empty list → user should be removed
            response = existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[])
            assert response.status_code == 200, response.text
            assert response.json() == []
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")
            existing_admin_client.delete(f"/projects/{side_project['id']}")

    def test_sync_updates_is_primary(
        self, existing_admin_client, project, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """is_primary sets the listed user's primary project, and clearing it on the same project unsets it."""
        side_project = project_factory()
        user = user_factory(0, side_project["id"])
        try:
            def primary():
                return existing_admin_client.get(f"/users/{user['id']}").json()["primary_project_id"]

            existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "is_primary": False}],
            )
            assert primary() == side_project["id"], "Not primary here leaves the other primary project alone"

            response = existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "is_primary": True}],
            )
            assert response.status_code == 200, response.text
            matched = [r for r in response.json() if r["id"] == user["id"]]
            assert len(matched) == 1
            assert matched[0]["is_primary"] is True
            assert primary() == project["id"]

            existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "is_primary": False}],
            )
            assert primary() is None, "Listing the user as not primary clears this project as their primary"
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")
            existing_admin_client.delete(f"/projects/{side_project['id']}")

    def test_removed_user_keeps_primary_project(
        self, existing_admin_client, project, plain_user_factory, manager_prefix, manager_enum
    ):
        user = plain_user_factory(0)
        existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[{"user_id": user["id"], "is_primary": True}])
        existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[])

        fetched = existing_admin_client.get(f"/users/{user['id']}").json()
        assert fetched["projects"] == [] and fetched["primary_project_id"] == project["id"]

    def test_primary_changes_are_audited_with_the_caller_as_actor(
        self, existing_admin_client, existing_admin_user, project, plain_user_factory, manager_prefix, manager_enum
    ):
        user = plain_user_factory(0)
        existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[{"user_id": user["id"], "is_primary": True}])

        rows = audit_rows(
            "member_user_id = :u OR (details->>'entity' = 'user' AND (details->>'entity_id')::int = :u)", u=user["id"],
        )
        assert [r["action"] for r in rows] == ["member_added", "metadata_changed"]
        assert rows[0]["details"] is None
        assert rows[1]["details"]["changes"] == {"primary_project_id": {"old": None, "new": project["id"]}}
        assert {r["actor_id"] for r in rows} == {existing_admin_user["id"]}

    def test_access_through_the_pi_group_does_not_block_a_direct_row(
        self, existing_admin_client, project, plain_user_factory, manager_prefix, manager_enum
    ):
        user = plain_user_factory(0)
        existing_admin_client.post(f"/projects/{project['id']}/pis", json={"user_id": user["id"]})

        response = existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[{"user_id": user["id"]}])
        assert response.status_code == 200, response.text
        assert [(r["id"], r["direct"], r["is_pi"]) for r in response.json()] == [(user["id"], True, True)]

    def test_project_without_a_project_group_returns_404(
        self, existing_admin_client, project, manager_prefix, manager_enum
    ):
        existing_admin_client.put(f"/projects/{project['id']}", json={"project_group_id": None})
        assert existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[]).status_code == 404

    def test_role_is_no_longer_accepted(self, existing_admin_client, project, user_factory, manager_prefix, manager_enum):
        response = existing_admin_client.put(
            project_url(manager_prefix, project["id"]),
            json=[{"user_id": 1, "role": "PI", "is_primary": False}],
        )
        assert response.status_code == 422

    def test_existing_direct_member_is_kept(
        self, existing_admin_client, project, user_factory, manager_prefix, manager_enum
    ):
        """A user who was added by hand and is also in the synced list stays, and is listed.

        user_factory creates users with their primary project set, which puts them in the
        project group as a direct member.
        """
        user = user_factory(0, project["id"])
        try:
            response = existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "is_primary": False}],
            )
            assert response.status_code == 200, response.text
            assert [r["id"] for r in response.json()] == [user["id"]]
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")

    def test_sync_replaces_every_direct_user_member(
        self, existing_admin_client, project, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """The group is managed as a whole: a sync removes direct user members it does not list,
        whoever added them. Member groups (the pi group) are left alone."""
        user_app = user_factory(0, project["id"])
        side_project = project_factory()
        user_managed = user_factory(1, side_project["id"])
        try:
            existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user_managed["id"], "is_primary": False}],
            )
            assert {m["id"] for m in existing_admin_client.get(f"/projects/{project['id']}/users").json()} == {user_managed["id"]}, \
                "user_app was not in the list, so the sync removed them"

            assert existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[]).json() == []
            assert existing_admin_client.get(f"/projects/{project['id']}/users").json() == []
            direct = existing_admin_client.get(f"/groups/{project['project_group_id']}/direct_members").json()
            assert [r["member_group"]["id"] for r in direct] == [project["pi_group_id"]], "the pi group stays a member"
        finally:
            existing_admin_client.delete(f"/users/{user_app['id']}")
            existing_admin_client.delete(f"/users/{user_managed['id']}")
            existing_admin_client.delete(f"/projects/{side_project['id']}")

    def test_group_managed_by_another_system_is_refused(
        self, existing_admin_client, project, plain_user_factory, manager_prefix, manager_enum
    ):
        other = next(m for m in EntityManagerEnum if m not in (EntityManagerEnum.APPLICATION, manager_enum))
        assert existing_admin_client.put(f"/groups/{project['project_group_id']}", json={"managed_by": other.value}).status_code == 200
        user = plain_user_factory(0)

        response = existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[{"user_id": user["id"]}])
        assert response.status_code == 409, response.text
        assert other.value in response.json()["detail"]
        assert existing_admin_client.get(f"/projects/{project['id']}/users").json() == []

    def test_claiming_the_group_is_audited_once(
        self, existing_admin_client, existing_admin_user, project, plain_user_factory, manager_prefix, manager_enum
    ):
        user = plain_user_factory(0)
        existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[{"user_id": user["id"]}])
        existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[])

        [entry] = audit_rows("action = 'metadata_changed' AND group_id = :g", g=project["project_group_id"])
        assert entry["actor_id"] == existing_admin_user["id"]
        assert entry["details"] == {
            "entity": "group", "entity_id": project["project_group_id"],
            "changes": {"managed_by": {"old": "APPLICATION", "new": manager_enum.value}}, "reason": "managed_sync",
        }


# ---------------------------------------------------------------------------
# Group sync tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("manager_prefix,manager_enum", MANAGERS)
class TestManagedGroupSync:
    """Tests for PUT /managed/{manager}/groups/{id}/users."""

    def test_requires_admin(self, nonadmin_client, group, manager_prefix, manager_enum):
        """Non-admin requests are rejected with 403."""
        response = nonadmin_client.put(group_url(manager_prefix, group["id"]), json=[])
        assert response.status_code == 403

    def test_nonexistent_group_returns_404(self, existing_admin_client, manager_prefix, manager_enum):
        """Returns 404 when the group does not exist."""
        response = existing_admin_client.put(group_url(manager_prefix, 999_999_999), json=[])
        assert response.status_code == 404

    def test_nonexistent_user_returns_404(self, existing_admin_client, group, manager_prefix, manager_enum):
        """Returns 404 when a user_id in the body does not exist."""
        response = existing_admin_client.put(
            group_url(manager_prefix, group["id"]),
            json=[{"user_id": 999_999_999}],
        )
        assert response.status_code == 404

    def test_duplicate_user_id_returns_422(self, existing_admin_client, group, manager_prefix, manager_enum):
        """Returns 422 when the same user_id appears more than once in the request.

        Duplicate detection runs before user-existence checks, so a non-existent
        id is sufficient here.
        """
        response = existing_admin_client.put(
            group_url(manager_prefix, group["id"]),
            json=[{"user_id": 1}, {"user_id": 1}],
        )
        assert response.status_code == 422

    def test_empty_list_on_clean_group_returns_empty(
        self, existing_admin_client, group, manager_prefix, manager_enum
    ):
        """PUT [] on a group that has no managed rows returns 200 with an empty list."""
        response = existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[])
        assert response.status_code == 200
        assert response.json() == []

    def test_sync_adds_users(
        self, existing_admin_client, group, project, user_factory, manager_prefix, manager_enum
    ):
        """Users in the request body that are not already in the group get added.

        user_factory does NOT add users to groups, so the created user is
        guaranteed to be free to be claimed by the managed sync.
        """
        user = user_factory(0, project["id"])
        try:
            response = existing_admin_client.put(
                group_url(manager_prefix, group["id"]),
                json=[{"user_id": user["id"]}],
            )
            assert response.status_code == 200, response.text
            data = response.json()
            matched = [r for r in data if r["user_id"] == user["id"]]
            assert len(matched) == 1, "Synced user should appear in the response"
            assert matched[0]["group_id"] == group["id"]
            assert matched[0]["direct"] is True
            assert existing_admin_client.get(f"/groups/{group['id']}").json()["managed_by"] == manager_enum.value
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")

    def test_sync_removes_users_absent_from_new_list(
        self, existing_admin_client, group, project, user_factory, manager_prefix, manager_enum
    ):
        """Users that were previously managed but are absent from the new PUT body are removed."""
        user = user_factory(0, project["id"])
        try:
            # First sync: add the user
            existing_admin_client.put(
                group_url(manager_prefix, group["id"]),
                json=[{"user_id": user["id"]}],
            )
            # Second sync: empty list → user should be removed
            response = existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[])
            assert response.status_code == 200, response.text
            assert response.json() == []
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")

    def test_existing_direct_member_is_kept(
        self, existing_admin_client, group, project, user_factory, manager_prefix, manager_enum
    ):
        """A user who was added by hand and is also in the synced list stays, and is listed."""
        user = user_factory(0, project["id"])
        add_resp = existing_admin_client.post(f"/groups/{group['id']}/members", json={"user_id": user["id"]})
        assert add_resp.status_code == 201, add_resp.text
        try:
            response = existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[{"user_id": user["id"]}])
            assert response.status_code == 200, response.text
            assert [r["user_id"] for r in response.json()] == [user["id"]]
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")

    def test_sync_replaces_every_direct_user_member(
        self, existing_admin_client, group, project, user_factory, group_member, manager_prefix, manager_enum
    ):
        """The group is managed as a whole: users not in the list are removed, member groups stay"""
        user_app = user_factory(0, project["id"])
        user_managed = user_factory(1, project["id"])
        add_resp = existing_admin_client.post(f"/groups/{group['id']}/members", json={"user_id": user_app["id"]})
        assert add_resp.status_code == 201, add_resp.text
        member_group = group_member(group['id'], member_group_id=project['pi_group_id'])
        try:
            response = existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[{"user_id": user_managed["id"]}])
            assert {r["user_id"] for r in response.json()} == {user_managed["id"]}
            assert {m["user_id"] for m in existing_admin_client.get(f"/groups/{group['id']}/members").json()} == {user_managed["id"]}

            existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[])
            direct = existing_admin_client.get(f"/groups/{group['id']}/direct_members").json()
            assert [r["id"] for r in direct] == [member_group["id"]], "the member group is not the sync's to remove"
        finally:
            existing_admin_client.delete(f"/users/{user_app['id']}")
            existing_admin_client.delete(f"/users/{user_managed['id']}")

    def test_access_through_a_member_group_survives_the_sync(
        self, existing_admin_client, group_factory, group_member, plain_user_factory, manager_prefix, manager_enum
    ):
        """A user the sync drops keeps the access a member group gives them: the sync owns direct user rows only"""
        group, inner = group_factory(), group_factory()
        user = plain_user_factory(0)
        group_member(inner["id"], user_id=user["id"])
        group_member(group["id"], member_group_id=inner["id"])

        response = existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[{"user_id": user["id"]}])
        assert response.status_code == 200, response.text
        assert [(r["user_id"], r["direct"]) for r in response.json()] == [(user["id"], True)]

        assert existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[]).json() == []
        [row] = existing_admin_client.get(f"/groups/{group['id']}/members").json()
        assert row["user_id"] == user["id"] and row["direct"] is False
        assert row["paths"] == [[group["id"], inner["id"]]]

    def test_staff_handing_the_group_back_lets_the_next_sync_reclaim_it(
        self, existing_admin_client, group_factory, plain_user_factory, manager_prefix, manager_enum
    ):
        group = group_factory()
        user = plain_user_factory(0)
        existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[{"user_id": user["id"]}])
        assert existing_admin_client.put(f"/groups/{group['id']}", json={"managed_by": "APPLICATION"}).status_code == 200

        # The group is the application's again, so the next sync claims it once more and replaces the members
        response = existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[])
        assert response.status_code == 200, response.text
        assert existing_admin_client.get(f"/groups/{group['id']}").json()["managed_by"] == manager_enum.value
        assert existing_admin_client.get(f"/groups/{group['id']}/members").json() == []
        claims = [
            r for r in audit_rows("action = 'metadata_changed' AND group_id = :g", g=group["id"])
            if r["details"].get("reason") == "managed_sync"
        ]
        assert [c["details"]["changes"]["managed_by"]["new"] for c in claims] == [manager_enum.value, manager_enum.value]

    def test_refused_sync_leaves_no_audit_row(
        self, existing_admin_client, group_factory, plain_user_factory, manager_prefix, manager_enum
    ):
        other = next(m for m in EntityManagerEnum if m not in (EntityManagerEnum.APPLICATION, manager_enum))
        group = group_factory(managed_by=other.value)
        user = plain_user_factory(0)
        mark = audit_rows()
        assert existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[{"user_id": user["id"]}]).status_code == 409
        assert audit_rows() == mark

    def test_group_managed_by_another_system_is_refused(
        self, existing_admin_client, group_factory, plain_user_factory, manager_prefix, manager_enum
    ):
        other = next(m for m in EntityManagerEnum if m not in (EntityManagerEnum.APPLICATION, manager_enum))
        group = group_factory(managed_by=other.value)
        user = plain_user_factory(0)

        response = existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[{"user_id": user["id"]}])
        assert response.status_code == 409, response.text
        assert existing_admin_client.get(f"/groups/{group['id']}/members").json() == []
        assert existing_admin_client.get(f"/groups/{group['id']}").json()["managed_by"] == other.value



# ---------------------------------------------------------------------------
# One primary project per user
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("manager_prefix,manager_enum", MANAGERS)
class TestManagedPrimaryProject:
    """is_primary is users.primary_project_id, so one project is primary per user by construction."""

    def test_sync_primary_demotes_other_primary(
        self, existing_admin_client, project, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """Syncing a user in as primary clears their previous primary project."""
        side_project = project_factory()
        user = user_factory(0, side_project["id"])
        try:
            response = existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "is_primary": True}],
            )
            assert response.status_code == 200, response.text

            memberships = existing_admin_client.get(f"/users/{user['id']}/projects").json()
            primary_ids = [m["project_id"] for m in memberships if m["is_primary"]]
            assert primary_ids == [project["id"]]
            assert side_project["id"] in [m["project_id"] for m in memberships], "old membership must remain"
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")
            existing_admin_client.delete(f"/projects/{side_project['id']}")

    def test_last_sync_wins_across_projects(
        self, existing_admin_client, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """When two projects are synced as primary for one user, the later sync is the one that stays primary."""
        first = project_factory()
        second = project_factory()
        user = user_factory(0, first["id"])
        try:
            for project_id in (first["id"], second["id"]):
                response = existing_admin_client.put(
                    project_url(manager_prefix, project_id),
                    json=[{"user_id": user["id"], "is_primary": True}],
                )
                assert response.status_code == 200, response.text

            memberships = existing_admin_client.get(f"/users/{user['id']}/projects").json()
            primary_ids = [m["project_id"] for m in memberships if m["is_primary"]]
            assert primary_ids == [second["id"]]
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")
            existing_admin_client.delete(f"/projects/{first['id']}")
            existing_admin_client.delete(f"/projects/{second['id']}")
