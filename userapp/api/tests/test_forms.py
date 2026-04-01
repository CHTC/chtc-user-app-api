import random

from httpx import Client


def user_form_data_f(netid: str = None) -> dict:
    rand = random.randint(100000, 999999)
    return {
        "netid": netid if netid else f"testnetid{rand}",
    }


class TestUserFormPost:

    def test_authenticated_user_can_post_user_form(self, nonadmin_client: Client):
        """Non-admin users should be able to submit a user form."""

        response = nonadmin_client.post("/forms/users", json=user_form_data_f())

        assert response.status_code == 201, (
            f"Authenticated POST /forms/users should return 201, got {response.status_code}: {response.text}"
        )

    def test_post_user_form_returns_pending_status(self, nonadmin_client: Client):
        """A newly submitted form should default to PENDING status."""

        response = nonadmin_client.post("/forms/users", json=user_form_data_f())

        assert response.status_code == 201
        assert response.json()["status"] == "PENDING", (
            f"New form status should default to PENDING, got '{response.json()['status']}'"
        )

    def test_post_user_form_returns_correct_netid(self, nonadmin_client: Client):
        """The created form should echo back the submitted netid."""

        netid = f"testnetid{random.randint(100000, 999999)}"
        response = nonadmin_client.post("/forms/users", json=user_form_data_f(netid=netid))

        assert response.status_code == 201
        assert response.json()["netid"] == netid, (
            f"Response netid should be '{netid}', got '{response.json()['netid']}'"
        )


class TestUserFormPut:

    def test_admin_update_changes_updated_by_but_not_created_by(
        self,
        nonadmin_client: Client,
        admin_client: Client,
        user: dict,
        admin_user: dict,
    ):
        """Creating as a non-admin should set both audit users, and admin updates should only change updated_by."""

        create_response = nonadmin_client.post("/forms/users", json=user_form_data_f())

        assert create_response.status_code == 201, (
            f"Non-admin POST /forms/users should return 201, got {create_response.status_code}: {create_response.text}"
        )

        created_form = create_response.json()
        form_id = created_form["id"]

        assert created_form["created_by"]["id"] == user["id"], (
            f"Created form created_by.id should be {user['id']}, got {created_form['created_by']['id']}"
        )
        assert created_form["updated_by"]["id"] == user["id"], (
            f"Created form updated_by.id should be {user['id']}, got {created_form['updated_by']['id']}"
        )

        update_response = admin_client.put(f"/forms/{form_id}", json={"status": "APPROVED"})

        assert update_response.status_code == 200, (
            f"Admin PUT /forms/{form_id} should return 200, got {update_response.status_code}: {update_response.text}"
        )

        updated_form = update_response.json()

        assert updated_form["created_by"]["id"] == user["id"], (
            f"Updated form created_by.id should remain {user['id']}, got {updated_form['created_by']['id']}"
        )
        assert updated_form["updated_by"]["id"] == admin_user["id"], (
            f"Updated form updated_by.id should be {admin_user['id']}, got {updated_form['updated_by']['id']}"
        )
        assert "netid" not in updated_form, (
            f"Generic PUT /forms/{form_id} response should not include netid, got {updated_form}"
        )

    def test_nonadmin_cannot_put_user_form(self, nonadmin_client: Client, admin_client: Client):
        """Non-admin users should not be able to update form status."""

        create_response = admin_client.post("/forms/users", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        response = nonadmin_client.put(f"/forms/{form_id}", json={"status": "APPROVED"})

        assert response.status_code == 403, (
            f"Non-admin PUT /forms/{form_id} should return 403, got {response.status_code}: {response.text}"
        )

    def test_admin_can_approve_user_form(self, admin_client: Client):
        """Admin users should be able to approve a user form."""

        create_response = admin_client.post("/forms/users", json=user_form_data_f())
        assert create_response.status_code == 201
        form_id = create_response.json()["id"]

        update_response = admin_client.put(f"/forms/{form_id}", json={"status": "APPROVED"})

        assert update_response.status_code == 200, (
            f"Admin PUT /forms/{form_id} should return 200, got {update_response.status_code}: {update_response.text}"
        )
        assert update_response.json()["status"] == "APPROVED"
        assert "netid" not in update_response.json(), (
            f"Generic PUT /forms/{form_id} response should not include netid, got {update_response.json()}"
        )

    def test_put_nonexistent_form_returns_404(self, admin_client: Client):
        """Updating a form that does not exist should return 404."""

        response = admin_client.put("/forms/999999999", json={"status": "APPROVED"})

        assert response.status_code == 404, (
            f"PUT /forms/999999999 should return 404, got {response.status_code}: {response.text}"
        )
