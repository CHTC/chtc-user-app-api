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

from userapp.core.models.enum import EntityManagerEnum, RoleEnum

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
            assert matched[0]["managed_by"] == manager_enum.value
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

    def test_sync_updates_role_and_is_primary(
        self, existing_admin_client, project, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """An existing managed membership is updated when role or is_primary changes."""
        side_project = project_factory()
        user = user_factory(0, side_project["id"])
        try:
            # Add as MEMBER / not primary
            existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "role": RoleEnum.MEMBER.value, "is_primary": False}],
            )
            # Update to PI / primary
            response = existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "role": RoleEnum.PI.value, "is_primary": True}],
            )
            assert response.status_code == 200, response.text
            matched = [r for r in response.json() if r["id"] == user["id"]]
            assert len(matched) == 1
            assert matched[0]["role"] == RoleEnum.PI.value
            assert matched[0]["is_primary"] is True
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")
            existing_admin_client.delete(f"/projects/{side_project['id']}")

    def test_application_claimed_user_is_silently_skipped(
        self, existing_admin_client, project, user_factory, manager_prefix, manager_enum
    ):
        """A user already managed by APPLICATION in the same project is silently skipped.

        user_factory creates users with their primary project set, which results
        in an APPLICATION-managed UserProject row for that project.
        """
        user = user_factory(0, project["id"])
        try:
            response = existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user["id"], "is_primary": False}],
            )
            assert response.status_code == 200, response.text
            matched = [r for r in response.json() if r["id"] == user["id"]]
            assert len(matched) == 0, "APPLICATION-managed user should be silently skipped"
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")

    def test_does_not_remove_application_managed_members(
        self, existing_admin_client, project, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """APPLICATION-managed memberships are untouched even when the managed sync clears its own rows."""
        # user_app is in the project with APPLICATION managed_by (via primary project assignment)
        user_app = user_factory(0, project["id"])
        # user_managed is in a different primary project so they are not yet in the test project
        side_project = project_factory()
        user_managed = user_factory(1, side_project["id"])
        try:
            # Add user_managed via managed sync
            existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user_managed["id"], "is_primary": False}],
            )
            # Sync with empty list – removes user_managed but must NOT touch user_app
            existing_admin_client.put(project_url(manager_prefix, project["id"]), json=[])

            members_resp = existing_admin_client.get(f"/projects/{project['id']}/users")
            assert members_resp.status_code == 200
            member_ids = [m["id"] for m in members_resp.json()]
            assert user_app["id"] in member_ids, "APPLICATION-managed member should not be removed"
        finally:
            existing_admin_client.delete(f"/users/{user_app['id']}")
            existing_admin_client.delete(f"/users/{user_managed['id']}")
            existing_admin_client.delete(f"/projects/{side_project['id']}")

    def test_response_only_includes_rows_for_this_manager(
        self, existing_admin_client, project, project_factory, user_factory, manager_prefix, manager_enum
    ):
        """The PUT response only includes rows owned by the called manager, not APPLICATION rows."""
        user_app = user_factory(0, project["id"])  # APPLICATION
        side_project = project_factory()
        user_managed = user_factory(1, side_project["id"])  # will be added as managed
        try:
            response = existing_admin_client.put(
                project_url(manager_prefix, project["id"]),
                json=[{"user_id": user_managed["id"], "is_primary": False}],
            )
            assert response.status_code == 200, response.text
            returned_ids = {r["id"] for r in response.json()}
            assert user_app["id"] not in returned_ids, "APPLICATION member should not appear in response"
            assert user_managed["id"] in returned_ids, "Managed member should appear in response"
        finally:
            existing_admin_client.delete(f"/users/{user_app['id']}")
            existing_admin_client.delete(f"/users/{user_managed['id']}")
            existing_admin_client.delete(f"/projects/{side_project['id']}")


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
            assert matched[0]["managed_by"] == manager_enum.value
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

    def test_application_claimed_user_is_silently_skipped(
        self, existing_admin_client, group, project, user_factory, manager_prefix, manager_enum
    ):
        """A user already managed by APPLICATION in the same group is silently skipped."""
        user = user_factory(0, project["id"])
        # Explicitly add user via the APPLICATION route first
        add_resp = existing_admin_client.post(
            f"/groups/{group['id']}/users", json={"user_id": user["id"]}
        )
        assert add_resp.status_code == 201, add_resp.text
        try:
            response = existing_admin_client.put(
                group_url(manager_prefix, group["id"]),
                json=[{"user_id": user["id"]}],
            )
            assert response.status_code == 200, response.text
            matched = [r for r in response.json() if r["user_id"] == user["id"]]
            assert len(matched) == 0, "APPLICATION-managed user should be silently skipped"
        finally:
            existing_admin_client.delete(f"/users/{user['id']}")

    def test_does_not_remove_application_managed_members(
        self, existing_admin_client, group, project, user_factory, manager_prefix, manager_enum
    ):
        """APPLICATION-managed group memberships are untouched when the managed sync clears its own rows."""
        user_app = user_factory(0, project["id"])
        user_managed = user_factory(1, project["id"])
        # Add user_app to the group via the APPLICATION route
        add_resp = existing_admin_client.post(
            f"/groups/{group['id']}/users", json={"user_id": user_app["id"]}
        )
        assert add_resp.status_code == 201, add_resp.text
        try:
            # Add user_managed via managed sync
            existing_admin_client.put(
                group_url(manager_prefix, group["id"]),
                json=[{"user_id": user_managed["id"]}],
            )
            # Sync with empty list – removes user_managed but must NOT touch user_app
            existing_admin_client.put(group_url(manager_prefix, group["id"]), json=[])

            members_resp = existing_admin_client.get(f"/groups/{group['id']}/users")
            assert members_resp.status_code == 200
            member_ids = [m["user_id"] for m in members_resp.json()]
            assert user_app["id"] in member_ids, "APPLICATION-managed member should not be removed"
        finally:
            existing_admin_client.delete(f"/users/{user_app['id']}")
            existing_admin_client.delete(f"/users/{user_managed['id']}")

    def test_response_only_includes_rows_for_this_manager(
        self, existing_admin_client, group, project, user_factory, manager_prefix, manager_enum
    ):
        """The PUT response only includes rows owned by the called manager, not APPLICATION rows."""
        user_app = user_factory(0, project["id"])
        user_managed = user_factory(1, project["id"])
        # Add user_app via APPLICATION route
        add_resp = existing_admin_client.post(
            f"/groups/{group['id']}/users", json={"user_id": user_app["id"]}
        )
        assert add_resp.status_code == 201, add_resp.text
        try:
            response = existing_admin_client.put(
                group_url(manager_prefix, group["id"]),
                json=[{"user_id": user_managed["id"]}],
            )
            assert response.status_code == 200, response.text
            returned_ids = {r["user_id"] for r in response.json()}
            assert user_app["id"] not in returned_ids, "APPLICATION member should not appear in response"
            assert user_managed["id"] in returned_ids, "Managed member should appear in response"
        finally:
            existing_admin_client.delete(f"/users/{user_app['id']}")
            existing_admin_client.delete(f"/users/{user_managed['id']}")

