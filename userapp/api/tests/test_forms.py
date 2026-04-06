from unittest.mock import AsyncMock

from httpx import Client
from userapp.api.routes import forms as forms_routes
from userapp.core.models.enum import FormStatusEnum, FormTypeEnum


def user_form_data_f() -> dict:
    return {
        "pi_id": None,
        "pi_name": "John Doe",
        "pi_email": "johndoe@wisc.edu",
        "position": "POSTDOC"
    }


class TestUserFormPost:

    def test_authenticated_user_can_post_user_form(self, nonadmin_client: Client):
        """Non-admin users should be able to submit a user form."""

        response = nonadmin_client.post("/forms/user-applications", json=user_form_data_f())

        assert response.status_code == 201, (
            f"Authenticated POST /forms/user-applications should return 201, got {response.status_code}: {response.text}"
        )

    def test_post_user_form_returns_pending_status(self, nonadmin_client: Client):
        """A newly submitted form should default to PENDING status."""

        response = nonadmin_client.post("/forms/user-applications", json=user_form_data_f())

        assert response.status_code == 201
        assert response.json()["status"] == "PENDING", (
            f"New form status should default to PENDING, got '{response.json()['status']}'"
        )

    def test_post_user_form_accepts_named_pi_fields(self, nonadmin_client: Client):
        """A user form can be submitted with PI name/email instead of a PI id."""

        payload = user_form_data_f()
        response = nonadmin_client.post("/forms/user-applications", json=payload)

        assert response.status_code == 201, (
            f"POST /forms/user-applications with pi_name/pi_email should return 201, got {response.status_code}: {response.text}"
        )
        response_json = response.json()
        assert response_json["pi_id"] is None
        assert response_json["pi_name"] == payload["pi_name"]
        assert response_json["pi_email"] == payload["pi_email"]

    def test_post_user_form_accepts_pi_id(self, nonadmin_client: Client, user_factory, project_factory):
        """A user form can be submitted with an existing PI id and no PI name/email."""

        project = project_factory()
        pi_user = user_factory(1, project_id=project["id"])
        payload = user_form_data_f()
        payload["pi_id"] = pi_user["id"]
        payload["pi_name"] = None
        payload["pi_email"] = None

        response = nonadmin_client.post("/forms/user-applications", json=payload)

        assert response.status_code == 201, (
            f"POST /forms/user-applications with pi_id should return 201, got {response.status_code}: {response.text}"
        )
        response_json = response.json()
        assert response_json["pi_id"] == pi_user["id"]
        assert response_json["pi_name"] is None
        assert response_json["pi_email"] is None

    def test_post_user_form_rejects_missing_pi_email(self, nonadmin_client: Client):
        """A user form should fail validation when only pi_name is provided."""

        payload = user_form_data_f()
        payload["pi_email"] = None

        response = nonadmin_client.post("/forms/user-applications", json=payload)

        assert response.status_code == 422, (
            f"POST /forms/user-applications with pi_name but no pi_email should return 422, got {response.status_code}: {response.text}"
        )

    def test_post_user_form_rejects_mixed_pi_id_and_name_email(self, nonadmin_client: Client, user_factory, project_factory):
        """A user form should fail validation when both pi_id and pi_name/pi_email are provided."""

        project = project_factory()
        pi_user = user_factory(2, project_id=project["id"])
        payload = user_form_data_f()
        payload["pi_id"] = pi_user["id"]

        response = nonadmin_client.post("/forms/user-applications", json=payload)

        assert response.status_code == 422, (
            f"POST /forms/user-applications with both pi_id and pi_name/pi_email should return 422, got {response.status_code}: {response.text}"
        )

    def test_post_user_form_rejects_nonexistent_pi_id(self, nonadmin_client: Client):
        """A user form should return 400 when pi_id does not refer to an existing user."""

        payload = user_form_data_f()
        payload["pi_id"] = 999999999
        payload["pi_name"] = None
        payload["pi_email"] = None

        response = nonadmin_client.post("/forms/user-applications", json=payload)

        assert response.status_code == 400, (
            f"POST /forms/user-applications with nonexistent pi_id should return 400, got {response.status_code}: {response.text}"
        )


class TestFormGet:

    def test_admin_can_list_forms(self, admin_client: Client):
        """Admins should be able to list forms generically."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        created_form = create_response.json()

        response = admin_client.get("/forms")

        assert response.status_code == 200, (
            f"GET /forms should return 200, got {response.status_code}: {response.text}"
        )
        response_json = response.json()
        assert len(response_json) >= 1
        assert any(form["id"] == created_form["id"] and form["status"] == "PENDING" for form in response_json), (
            f"GET /forms should include the created form {created_form['id']}, got {response_json}"
        )

    def test_admin_can_list_user_applications(self, admin_client: Client):
        """Admins should be able to list user applications with user info."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        created_form = create_response.json()

        response = admin_client.get("/forms/user-applications")

        assert response.status_code == 200, (
            f"GET /forms/user-applications should return 200, got {response.status_code}: {response.text}"
        )
        response_json = response.json()
        assert len(response_json) >= 1
        matching_form = next((form for form in response_json if form["id"] == created_form["id"]), None)
        assert matching_form is not None, (
            f"GET /forms/user-applications should include the created form {created_form['id']}, got {response_json}"
        )
        assert matching_form["created_by"]["id"] is not None
        assert matching_form["pi_name"] == "John Doe"

class TestUserFormPatch:

    def test_admin_update_changes_updated_by_but_not_created_by(
        self,
        nonadmin_client: Client,
        admin_client: Client,
        user: dict,
        admin_user: dict,
    ):
        """Creating as a non-admin should set both audit users, and admin updates should only change updated_by."""

        create_response = nonadmin_client.post("/forms/user-applications", json=user_form_data_f())

        assert create_response.status_code == 201, (
            f"Non-admin POST /forms/user-applications should return 201, got {create_response.status_code}: {create_response.text}"
        )

        created_form = create_response.json()
        form_id = created_form["id"]

        assert created_form["created_by"]["id"] == user["id"], (
            f"Created form created_by.id should be {user['id']}, got {created_form['created_by']['id']}"
        )
        assert created_form["updated_by"]["id"] == user["id"], (
            f"Created form updated_by.id should be {user['id']}, got {created_form['updated_by']['id']}"
        )

        update_response = admin_client.patch(f"/forms/user-applications/{form_id}", json={"status": "APPROVED"})

        assert update_response.status_code == 200, (
            f"Admin PATCH /forms/user-applications/{form_id} should return 200, got {update_response.status_code}: {update_response.text}"
        )

        updated_form = update_response.json()

        assert updated_form["created_by"]["id"] == user["id"], (
            f"Updated form created_by.id should remain {user['id']}, got {updated_form['created_by']['id']}"
        )
        assert updated_form["updated_by"]["id"] == admin_user["id"], (
            f"Updated form updated_by.id should be {admin_user['id']}, got {updated_form['updated_by']['id']}"
        )

    def test_nonadmin_cannot_patch_user_form(self, nonadmin_client: Client, admin_client: Client):
        """Non-admin users should not be able to update form status."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        response = nonadmin_client.patch(f"/forms/user-applications/{form_id}", json={"status": "APPROVED"})

        assert response.status_code == 403, (
            f"Non-admin PATCH /forms/user-applications/{form_id} should return 403, got {response.status_code}: {response.text}"
        )

    def test_admin_can_approve_user_form(self, admin_client: Client):
        """Admin users should be able to approve a user form."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        update_response = admin_client.patch(f"/forms/user-applications/{form_id}", json={"status": "APPROVED"})

        assert update_response.status_code == 200, (
            f"Admin PATCH /forms/user-applications/{form_id} should return 200, got {update_response.status_code}: {update_response.text}"
        )
        assert update_response.json()["status"] == "APPROVED"

    def test_patch_nonexistent_form_returns_404(self, admin_client: Client):
        """Updating a form that does not exist should return 404."""

        response = admin_client.patch("/forms/user-applications/999999999", json={"status": "APPROVED"})

        assert response.status_code == 404, (
            f"PATCH /forms/user-applications/999999999 should return 404, got {response.status_code}: {response.text}"
        )


class TestUserFormTriggers:

    def test_approved_form_cannot_change_state(self, admin_client: Client):
        """Once a form is approved, later status updates should fail."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        approve_response = admin_client.patch(f"/forms/user-applications/{form_id}", json={"status": "APPROVED"})
        assert approve_response.status_code == 200

        second_update_response = admin_client.patch(f"/forms/user-applications/{form_id}", json={"status": "DENIED"})

        assert second_update_response.status_code == 400, (
            f"PATCH /forms/user-applications/{form_id} after approval should return 400, got {second_update_response.status_code}: "
            f"{second_update_response.text}"
        )

    def test_approving_user_form_runs_trigger_in_request_session(self, admin_client: Client, monkeypatch):
        """Approving a user form should run the approval side effect in the current session."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        task_mock = AsyncMock()
        monkeypatch.setitem(
            forms_routes.form_triggers,
            (FormTypeEnum.USER, FormStatusEnum.PENDING, FormStatusEnum.APPROVED),
            task_mock,
        )

        update_response = admin_client.patch(f"/forms/user-applications/{form_id}", json={"status": "APPROVED"})

        assert update_response.status_code == 200
        task_mock.assert_called_once()
        [_, call_form_id, call_form], _ = task_mock.call_args
        assert call_form_id == form_id
        assert call_form.status == FormStatusEnum.APPROVED
