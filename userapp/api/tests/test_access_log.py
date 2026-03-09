import random
from datetime import datetime, timezone

from httpx import Client

from userapp.api.tests.fake_data import user_data_f


def get_access_logs(client: Client, created_at_after: datetime) -> list[dict]:
    params = { "created_at": f"gt.{created_at_after.timestamp()}" }
    response = client.get("/access_logs", params=params)
    assert response.status_code == 200
    logs = response.json()
    logs.sort(key=lambda log: log["created_at"], reverse=True)
    return logs


class TestAccessLog:

    def test_get_does_not_log(self, existing_admin_client):
        """GET requests should not produce access logs"""

        start_time = datetime.now(timezone.utc)
        existing_admin_client.get("/groups")

        logs = get_access_logs(existing_admin_client, created_at_after=start_time)
        assert not any(log["method"] == "GET" for log in logs), "GET requests should not create access logs"

    def test_non_admin_cannot_access(self, nonadmin_client):
        """Non-admin users should not be able to access access logs"""

        response = nonadmin_client.get("/access_logs")
        assert response.status_code == 403

    def test_user_id_recorded(self, existing_admin_client, existing_admin_user):
        """Access logs should record the correct user_id"""

        start_time = datetime.now(timezone.utc)
        group_name = f"access-log-test-{random.randint(100000, 999999)}"
        existing_admin_client.post("/groups", json={
            "name": group_name,
            "unix_gid": random.randint(55000, 60000),
            "has_groupdir": True,
        })

        logs = get_access_logs(existing_admin_client, created_at_after=start_time)
        assert len(logs) >= 1, "Should have at least one access log for POST /groups"
        assert logs[0]["user_id"] == existing_admin_user["id"], "Access log should record the correct user_id"

    def test_query_string_stored(self, existing_admin_client, project):
        """Access logs should store query strings"""

        start_time = datetime.now(timezone.utc)
        user_payload = user_data_f(0, project["id"])
        existing_admin_client.post("/users?a=b&c=d", json=user_payload)

        logs = get_access_logs(existing_admin_client, created_at_after=start_time)
        assert len(logs) >= 1, "Should have at least one access log"
        assert logs[0]["query_string"] is not None, "Query string should not be None"
        assert "a=b&c=d" == logs[0]["query_string"], "Query string should contain the parameters"

    def test_payload_stored(self, existing_admin_client):
        """Access logs should store the request payload"""

        start_time = datetime.now(timezone.utc)
        group_payload = {
            "name": f"payload-test-{random.randint(100000, 999999)}",
            "unix_gid": random.randint(55000, 60000),
            "has_groupdir": True,
        }
        existing_admin_client.post("/groups", json=group_payload)

        logs = get_access_logs(existing_admin_client, created_at_after=start_time)
        assert len(logs) >= 1, "Should have at least one access log"
        assert logs[0]["payload"]["name"] == group_payload["name"], "Payload should contain the group name"

    def test_status_stored(self, existing_admin_client):
        """Access logs should store the response status code"""

        start_time = datetime.now(timezone.utc)
        group_payload = {
            "name": f"status-test-{random.randint(100000, 999999)}",
            "unix_gid": random.randint(55000, 60000),
            "has_groupdir": True,
        }
        existing_admin_client.post("/groups", json=group_payload)

        logs = get_access_logs(existing_admin_client, created_at_after=start_time)
        assert len(logs) >= 1, "Should have at least one access log"
        assert logs[0]["status"] == 201, f"Status should be 201 for successful creation, got {logs[0]['status']}"
    
    def test_raw_body_stored_for_non_json(self, existing_admin_client):
        """If a non-JSON body is sent, the raw body should be stored in the payload"""

        start_time = datetime.now(timezone.utc)
        raw_body = "This is not JSON"
        existing_admin_client.post("/groups", content=raw_body, headers={"Content-Type": "text/plain"})

        logs = get_access_logs(existing_admin_client, created_at_after=start_time)
        assert len(logs) >= 1, "Should have at least one access log"
        assert logs[0]["payload"]["raw_body"] == raw_body, "Raw body should be stored in payload for non-JSON requests"
