"""Tests for the app-level exception handlers registered in create_app."""
import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.testclient import TestClient

from userapp.api.util import USER_VISIBLE_PREFIX
from userapp.main import create_app


class _Strict(BaseModel):
    count: int


def _validation_error() -> ValidationError:
    try:
        _Strict(count="not a number")
    except ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


def _raise(error: Exception):
    async def route():
        raise error
    return route


@pytest.fixture
def error_client():
    app = create_app()
    routes = {
        "/trigger": DBAPIError("stmt", {}, Exception(f"CheckViolationError: {USER_VISIBLE_PREFIX}A user must have a primary project")),
        "/db": DBAPIError("stmt", {}, Exception("something internal about a table")),
        "/integrity": IntegrityError("stmt", {}, Exception("duplicate key value")),
        "/validation": _validation_error(),
        "/unexpected": RuntimeError("boom"),
    }
    for path, error in routes.items():
        app.add_api_route(f"/_errors{path}", _raise(error), methods=["GET"])

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestErrorHandlers:

    def test_trigger_rule_violation_returns_its_message(self, error_client):
        response = error_client.get("/_errors/trigger")
        assert response.status_code == 400
        assert response.json() == {"detail": "A user must have a primary project"}

    def test_other_database_error_is_generic_and_hides_internals(self, error_client):
        response = error_client.get("/_errors/db")
        assert response.status_code == 400
        assert response.json() == {"detail": "Database error occurred, likely due to violation of constraints."}

    def test_integrity_error_is_handled_as_a_database_error(self, error_client):
        response = error_client.get("/_errors/integrity")
        assert response.status_code == 400
        assert "duplicate key" not in response.text

    def test_validation_error_is_a_500_with_details(self, error_client):
        response = error_client.get("/_errors/validation")
        assert response.status_code == 500
        assert response.json()["detail"].startswith("Data validation error:")

    def test_unexpected_error_is_a_500(self, error_client):
        response = error_client.get("/_errors/unexpected")
        assert response.status_code == 500
        assert response.json() == {"detail": "An unexpected error occurred: boom"}
