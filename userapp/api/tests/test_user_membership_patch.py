"""Tests for membership PATCH endpoints:

    PATCH /projects/{project_id}/users/{user_id}
    PATCH /users/{user_id}/projects/{project_id}
    PATCH /groups/{group_id}/users/{user_id}
    PATCH /users/{user_id}/groups/{group_id}

Each pair (project / group) consists of two URL orderings that hit the same
underlying handler, so every test is parametrized over both orderings to
guarantee identical behavior without duplicating code.
"""
import pytest

from userapp.core.models.enum import EntityManagerEnum, RoleEnum


# ---------------------------------------------------------------------------
# URL-ordering parametrize markers
# ---------------------------------------------------------------------------

PROJECT_URL_ORDERINGS = [
    pytest.param(
        lambda user_id, project_id: f"/projects/{project_id}/users/{user_id}",
        id="project-first",
    ),
    pytest.param(
        lambda user_id, project_id: f"/users/{user_id}/projects/{project_id}",
        id="user-first",
    ),
]

GROUP_URL_ORDERINGS = [
    pytest.param(
        lambda user_id, group_id: f"/groups/{group_id}/users/{user_id}",
        id="group-first",
    ),
    pytest.param(
        lambda user_id, group_id: f"/users/{user_id}/groups/{group_id}",
        id="user-first",
    ),
]


# ---------------------------------------------------------------------------
# Project-membership PATCH
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url_for", PROJECT_URL_ORDERINGS)
class TestPatchUserProject:
    """Tests for both PATCH URL orderings for project membership."""

    def test_requires_admin(self, nonadmin_client, user, url_for):
        """Non-admin requests are rejected with 403."""
        project_id = user["projects"][0]["project_id"]
        response = nonadmin_client.patch(url_for(user["id"], project_id), json={})
        assert response.status_code == 403

    def test_nonexistent_project_returns_404(self, existing_admin_client, user, url_for):
        """Returns 404 when no such project exists."""
        response = existing_admin_client.patch(
            url_for(user["id"], 999_999_999),
            json={"is_primary": False},
        )
        assert response.status_code == 404

    def test_nonexistent_user_returns_404(self, existing_admin_client, project, url_for):
        """Returns 404 when no such user exists."""
        response = existing_admin_client.patch(
            url_for(999_999_999, project["id"]),
            json={"is_primary": False},
        )
        assert response.status_code == 404

    def test_user_not_in_project_returns_404(
        self, existing_admin_client, user, project_factory, url_for
    ):
        """Returns 404 when both ids exist but user isn't a member of that project."""
        side_project = project_factory()
        try:
            response = existing_admin_client.patch(
                url_for(user["id"], side_project["id"]),
                json={"is_primary": False},
            )
            assert response.status_code == 404
        finally:
            existing_admin_client.delete(f"/projects/{side_project['id']}")

    def test_patch_role(self, existing_admin_client, user, url_for):
        """Updating role persists and is reflected in the response and a subsequent GET."""
        project_id = user["projects"][0]["project_id"]
        response = existing_admin_client.patch(
            url_for(user["id"], project_id),
            json={"role": RoleEnum.MEMBER.value},
        )
        assert response.status_code == 200, response.text
        assert response.json()["role"] == RoleEnum.MEMBER.value
        assert response.json()["project_id"] == project_id
        assert response.json()["id"] == user["id"]

        # Verify it actually persisted
        get_resp = existing_admin_client.get(f"/projects/{project_id}/users")
        membership = next(m for m in get_resp.json() if m["id"] == user["id"])
        assert membership["role"] == RoleEnum.MEMBER.value

    def test_patch_is_primary(self, existing_admin_client, user, url_for):
        """Updating is_primary persists."""
        project_id = user["projects"][0]["project_id"]
        # User was created with their primary project = this project, so they're
        # already is_primary=True. Flip it off.
        response = existing_admin_client.patch(
            url_for(user["id"], project_id),
            json={"is_primary": False},
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_primary"] is False

    def test_patch_managed_by(self, existing_admin_client, user, url_for):
        """Updating managed_by persists and is returned with the enum value."""
        project_id = user["projects"][0]["project_id"]
        response = existing_admin_client.patch(
            url_for(user["id"], project_id),
            json={"managed_by": EntityManagerEnum.MANIFEST.value},
        )
        assert response.status_code == 200, response.text
        assert response.json()["managed_by"] == EntityManagerEnum.MANIFEST.value

    @pytest.mark.parametrize(
        "manager",
        [
            pytest.param(EntityManagerEnum.MANIFEST, id="MANIFEST"),
            pytest.param(EntityManagerEnum.MORGRIDGE_AD, id="MORGRIDGE_AD"),
            pytest.param(EntityManagerEnum.APPLICATION, id="APPLICATION"),
        ],
    )
    def test_patch_managed_by_round_trips_every_enum_member(
        self, existing_admin_client, user, url_for, manager
    ):
        """Regression: every ``EntityManagerEnum`` member must round-trip
        cleanly through PATCH and a subsequent GET.

        ``MORGRIDGE_AD`` is the critical case — its ``.name`` (``MORGRIDGE_AD``)
        differs from its ``.value`` (``MORGRIDGE_ACTIVE_DIRECTORY``). A prior
        bug caused the helper to assign the serialized ``.value`` string to
        the ORM column, which Postgres rejected with
        ``InvalidTextRepresentationError``. SQLite silently accepts it but the
        round-tripped GET still has to match the requested value, so this test
        catches the bug on both backends.
        """
        project_id = user["projects"][0]["project_id"]

        response = existing_admin_client.patch(
            url_for(user["id"], project_id),
            json={"managed_by": manager.value},
        )
        assert response.status_code == 200, response.text
        assert response.json()["managed_by"] == manager.value, (
            f"PATCH response managed_by mismatch: requested {manager.value!r}, "
            f"got {response.json()['managed_by']!r}"
        )

        # Persisted value must match what we sent (round-trip via the view).
        get_resp = existing_admin_client.get(f"/projects/{project_id}/users")
        assert get_resp.status_code == 200, get_resp.text
        membership = next(m for m in get_resp.json() if m["id"] == user["id"])
        assert membership["managed_by"] == manager.value, (
            f"Persisted managed_by mismatch for {manager.name}: "
            f"expected {manager.value!r}, got {membership['managed_by']!r}"
        )

    def test_empty_patch_returns_existing_row_unchanged(
        self, existing_admin_client, user, url_for
    ):
        """An empty PATCH body is a no-op and returns the current membership."""
        project_id = user["projects"][0]["project_id"]
        before = next(p for p in user["projects"] if p["project_id"] == project_id)

        response = existing_admin_client.patch(
            url_for(user["id"], project_id), json={}
        )
        assert response.status_code == 200, response.text
        after = response.json()
        assert after["id"] == user["id"]
        assert after["project_id"] == project_id
        assert after["role"] == before["role"]
        assert after["is_primary"] == before["is_primary"]
        assert after["managed_by"] == before["managed_by"]


# ---------------------------------------------------------------------------
# Group-membership PATCH
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url_for", GROUP_URL_ORDERINGS)
class TestPatchUserGroup:
    """Tests for both PATCH URL orderings for group membership."""

    def test_requires_admin(self, nonadmin_client, user, url_for):
        """Non-admin requests are rejected with 403."""
        group_id = user["groups"][0]["group_id"]
        response = nonadmin_client.patch(url_for(user["id"], group_id), json={})
        assert response.status_code == 403

    def test_nonexistent_group_returns_404(self, existing_admin_client, user, url_for):
        """Returns 404 when no such group exists."""
        response = existing_admin_client.patch(
            url_for(user["id"], 999_999_999),
            json={"managed_by": EntityManagerEnum.MANIFEST.value},
        )
        assert response.status_code == 404

    def test_nonexistent_user_returns_404(self, existing_admin_client, group, url_for):
        """Returns 404 when no such user exists."""
        response = existing_admin_client.patch(
            url_for(999_999_999, group["id"]),
            json={"managed_by": EntityManagerEnum.MANIFEST.value},
        )
        assert response.status_code == 404

    def test_user_not_in_group_returns_404(
        self, existing_admin_client, user, group_factory, url_for
    ):
        """Returns 404 when both ids exist but user isn't a member of that group."""
        side_group = group_factory()
        try:
            response = existing_admin_client.patch(
                url_for(user["id"], side_group["id"]),
                json={"managed_by": EntityManagerEnum.MANIFEST.value},
            )
            assert response.status_code == 404
        finally:
            existing_admin_client.delete(f"/groups/{side_group['id']}")

    def test_patch_managed_by(self, existing_admin_client, user, url_for):
        """Updating managed_by persists and is reflected in the response and a subsequent GET."""
        group_id = user["groups"][0]["group_id"]
        response = existing_admin_client.patch(
            url_for(user["id"], group_id),
            json={"managed_by": EntityManagerEnum.MORGRIDGE_AD.value},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["managed_by"] == EntityManagerEnum.MORGRIDGE_AD.value
        assert body["group_id"] == group_id
        assert body["user_id"] == user["id"]

        # Verify it actually persisted
        get_resp = existing_admin_client.get(f"/groups/{group_id}/users")
        membership = next(m for m in get_resp.json() if m["user_id"] == user["id"])
        assert membership["managed_by"] == EntityManagerEnum.MORGRIDGE_AD.value

    @pytest.mark.parametrize(
        "manager",
        [
            pytest.param(EntityManagerEnum.MANIFEST, id="MANIFEST"),
            pytest.param(EntityManagerEnum.MORGRIDGE_AD, id="MORGRIDGE_AD"),
            pytest.param(EntityManagerEnum.APPLICATION, id="APPLICATION"),
        ],
    )
    def test_patch_managed_by_round_trips_every_enum_member(
        self, existing_admin_client, user, url_for, manager
    ):
        """Regression: every ``EntityManagerEnum`` member must round-trip
        cleanly through PATCH and a subsequent GET. See the equivalent test on
        the project side for full background on the ``MORGRIDGE_AD`` bug.
        """
        group_id = user["groups"][0]["group_id"]

        response = existing_admin_client.patch(
            url_for(user["id"], group_id),
            json={"managed_by": manager.value},
        )
        assert response.status_code == 200, response.text
        assert response.json()["managed_by"] == manager.value, (
            f"PATCH response managed_by mismatch: requested {manager.value!r}, "
            f"got {response.json()['managed_by']!r}"
        )

        # Persisted value must match what we sent (round-trip via the view).
        get_resp = existing_admin_client.get(f"/groups/{group_id}/users")
        assert get_resp.status_code == 200, get_resp.text
        membership = next(m for m in get_resp.json() if m["user_id"] == user["id"])
        assert membership["managed_by"] == manager.value, (
            f"Persisted managed_by mismatch for {manager.name}: "
            f"expected {manager.value!r}, got {membership['managed_by']!r}"
        )

    def test_patch_managed_by_sequential_changes_persist(
        self, existing_admin_client, user, url_for
    ):
        """Sequential PATCHes across enum members must each persist correctly.

        This catches a bug where a "sticky" serialized string from an earlier
        PATCH could be re-read and re-bound on a later UPDATE, producing
        ``invalid input value for enum`` against Postgres' native enum type.
        """
        group_id = user["groups"][0]["group_id"]
        sequence = [
            EntityManagerEnum.MANIFEST,
            EntityManagerEnum.MORGRIDGE_AD,
            EntityManagerEnum.APPLICATION,
            EntityManagerEnum.MORGRIDGE_AD,
        ]
        for manager in sequence:
            resp = existing_admin_client.patch(
                url_for(user["id"], group_id),
                json={"managed_by": manager.value},
            )
            assert resp.status_code == 200, (
                f"PATCH to {manager.name} failed: {resp.status_code} {resp.text}"
            )
            assert resp.json()["managed_by"] == manager.value

    def test_empty_patch_returns_existing_row_unchanged(
        self, existing_admin_client, user, url_for
    ):
        """An empty PATCH body is a no-op and returns the current membership."""
        group_id = user["groups"][0]["group_id"]
        before = next(g for g in user["groups"] if g["group_id"] == group_id)

        response = existing_admin_client.patch(
            url_for(user["id"], group_id), json={}
        )
        assert response.status_code == 200, response.text
        after = response.json()
        assert after["user_id"] == user["id"]
        assert after["group_id"] == group_id
        assert after["managed_by"] == before["managed_by"]

