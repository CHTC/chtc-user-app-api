import random
from unittest.mock import AsyncMock

from httpx import Client
from userapp.api.routes import forms as forms_routes
from userapp.core.models.enum import FormStatusEnum, FormTypeEnum
from userapp.api.tests.fake_data import user_form_data_f, user_form_approval_data_f


def create_submit_node(admin_client: Client) -> dict:
    response = admin_client.post(
        "/submit_nodes",
        json={"name": f"form-submit-node-{random.randint(0, 10**6)}"},
    )
    assert response.status_code == 201, (
        f"POST /submit_nodes should return 201, got {response.status_code}: {response.text}"
    )
    return response.json()


class TestUserFormPost:

    def test_user_can_create_form(self, nonadmin_client: Client):
        """Non-admin users should be able to submit a user form."""

        response = nonadmin_client.post("/forms/user-applications", json=user_form_data_f())

        assert response.status_code == 201, (
            f"Authenticated POST /forms/user-applications should return 201, got {response.status_code}: {response.text}"
        )

    def test_create_returns_pending_status(self, nonadmin_client: Client):
        """A newly submitted form should default to PENDING status."""

        response = nonadmin_client.post("/forms/user-applications", json=user_form_data_f())

        assert response.status_code == 201
        assert response.json()["status"] == "PENDING", (
            f"New form status should default to PENDING, got '{response.json()['status']}'"
        )

    def test_create_accepts_named_pi(self, nonadmin_client: Client):
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

    def test_create_accepts_pi_id(self, nonadmin_client: Client, user_factory, project_factory):
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

    def test_create_rejects_missing_pi_email(self, nonadmin_client: Client):
        """A user form should fail validation when only pi_name is provided."""

        payload = user_form_data_f()
        payload["pi_email"] = None

        response = nonadmin_client.post("/forms/user-applications", json=payload)

        assert response.status_code == 422, (
            f"POST /forms/user-applications with pi_name but no pi_email should return 422, got {response.status_code}: {response.text}"
        )

    def test_create_rejects_mixed_pi_fields(self, nonadmin_client: Client, user_factory, project_factory):
        """A user form should fail validation when both pi_id and pi_name/pi_email are provided."""

        project = project_factory()
        pi_user = user_factory(2, project_id=project["id"])
        payload = user_form_data_f()
        payload["pi_id"] = pi_user["id"]

        response = nonadmin_client.post("/forms/user-applications", json=payload)

        assert response.status_code == 422, (
            f"POST /forms/user-applications with both pi_id and pi_name/pi_email should return 422, got {response.status_code}: {response.text}"
        )

    def test_create_rejects_unknown_pi_id(self, nonadmin_client: Client):
        """A user form should return 400 when pi_id does not refer to an existing user."""

        payload = user_form_data_f()
        payload["pi_id"] = 999999999
        payload["pi_name"] = None
        payload["pi_email"] = None

        response = nonadmin_client.post("/forms/user-applications", json=payload)

        assert response.status_code == 400, (
            f"POST /forms/user-applications with nonexistent pi_id should return 400, got {response.status_code}: {response.text}"
        )


    def test_create_rejects_missing_required_fields(self, nonadmin_client: Client, user_factory, project_factory):

        user_form = user_form_data_f()
        user_form['how_chtc_can_help'] = None

        response = nonadmin_client.post("/forms/user-applications", json=user_form)

        assert response.status_code != 201, (
            f"Authenticated POST /forms/user-applications shouldn't return 201, got {response.status_code}: {response.text}"
        )

class TestFormGet:

    def test_nonadmin_cannot_get_forms(self, nonadmin_client: Client):
        """A non-admin should not be able to list all forms."""

        response = nonadmin_client.get("/forms")

        assert response.status_code == 403, (
            f"GET /forms as non-admin should return 403, got {response.status_code}: {response.text}"
        )

    def test_admin_can_list_forms(self, admin_client: Client):
        """Admins should be able to list forms."""

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

    def test_admin_can_get_user_applications(self, admin_client: Client):
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

    def test_patch_updates_only_updated_by(
        self,
        nonadmin_client: Client,
        admin_client: Client,
        project_factory,
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

        project = project_factory()
        submit_node = create_submit_node(admin_client)
        update_response = admin_client.patch(
            f"/forms/user-applications/{form_id}",
            json=user_form_approval_data_f(project["id"], [submit_node["name"]]),
        )

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

    def test_nonadmin_cannot_patch_form(self, nonadmin_client: Client, admin_client: Client):
        """Non-admins cannot patch forms."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        response = nonadmin_client.patch(f"/forms/user-applications/{form_id}", json={"status": "APPROVED"})

        assert response.status_code == 403, (
            f"Non-admin PATCH /forms/user-applications/{form_id} should return 403, got {response.status_code}: {response.text}"
        )

    def test_admin_can_approve_form(self, admin_client: Client, project_factory):
        """Admins can approve forms."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        project = project_factory()
        submit_node = create_submit_node(admin_client)
        update_response = admin_client.patch(
            f"/forms/user-applications/{form_id}",
            json=user_form_approval_data_f(project["id"], [submit_node["name"]]),
        )

        assert update_response.status_code == 200, (
            f"Admin PATCH /forms/user-applications/{form_id} should return 200, got {update_response.status_code}: {update_response.text}"
        )
        assert update_response.json()["status"] == "APPROVED"

    def test_patch_missing_form_returns_404(self, admin_client: Client):
        """Patch returns 404 for a missing form."""

        response = admin_client.patch("/forms/user-applications/999999999", json={"status": "APPROVED"})

        assert response.status_code == 404, (
            f"PATCH /forms/user-applications/999999999 should return 404, got {response.status_code}: {response.text}"
        )


class TestUserFormTriggers:

    def test_approved_form_cannot_change(self, admin_client: Client, project_factory):
        """Once a form is approved, a second update should not be allowed."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        project = project_factory()
        submit_node = create_submit_node(admin_client)
        approve_response = admin_client.patch(
            f"/forms/user-applications/{form_id}",
            json=user_form_approval_data_f(project["id"], [submit_node["name"]]),
        )
        assert approve_response.status_code == 200

        second_update_response = admin_client.patch(f"/forms/user-applications/{form_id}", json={"status": "DENIED"})

        assert second_update_response.status_code == 400, (
            f"PATCH /forms/user-applications/{form_id} after approval should return 400, got {second_update_response.status_code}: "
            f"{second_update_response.text}"
        )

    def test_approve_runs_trigger(self, admin_client: Client, monkeypatch, project_factory):
        """Approving a user form should run the approval side effect."""

        create_response = admin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        task_mock = AsyncMock()
        monkeypatch.setitem(
            forms_routes.form_triggers,
            (FormTypeEnum.USER, FormStatusEnum.PENDING, FormStatusEnum.APPROVED),
            task_mock,
        )

        project = project_factory()
        submit_node = create_submit_node(admin_client)
        update_response = admin_client.patch(
            f"/forms/user-applications/{form_id}",
            json=user_form_approval_data_f(project["id"], [submit_node["name"]]),
        )

        assert update_response.status_code == 200
        task_mock.assert_called_once()
        [_, call_form_id, call_form], _ = task_mock.call_args
        assert call_form_id == form_id
        assert call_form.status == FormStatusEnum.APPROVED

    def test_approve_activates_user_and_assigns_access(
        self,
        nonadmin_client: Client,
        admin_client: Client,
        project_factory,
        user: dict,
    ):
        """Approve activates the user and adds project and submit-node access."""

        create_response = nonadmin_client.post("/forms/user-applications", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        deactivate_response = admin_client.patch(f"/users/{user['id']}", json={"active": False})
        assert deactivate_response.status_code == 200

        project = project_factory()
        submit_node = create_submit_node(admin_client)
        update_response = admin_client.patch(
            f"/forms/user-applications/{form_id}",
            json=user_form_approval_data_f(project["id"], [submit_node["name"]]),
        )

        assert update_response.status_code == 200, (
            f"Admin PATCH /forms/user-applications/{form_id} should return 200, got {update_response.status_code}: {update_response.text}"
        )

        user_response = admin_client.get(f"/users/{user['id']}")
        assert user_response.status_code == 200
        updated_user = user_response.json()

        assert updated_user["active"] is True
        assert updated_user["position"] == "POSTDOC"
        assert any(project_membership["project_id"] == project["id"] for project_membership in updated_user["projects"])
        assert any(user_submit["submit_node_name"] == submit_node["name"] for user_submit in updated_user["submit_nodes"])
