import random
import base64
import os
from datetime import datetime
from typing import Optional

import pytest
from httpx import Client

from api.tests.main import basic_auth_client as client, admin_user

def project_data_f(
    name: Optional[str] = None,
    pi: Optional[int] = None,
    staff1: Optional[str] = None,
    staff2: Optional[str] = None,
    status: Optional[str] = None,
    access: Optional[str] = None,
    accounting_group: Optional[str] = None,
    url: Optional[str] = None,
    date: Optional[datetime] = None,
    ticket: Optional[int] = None,
    last_contact: Optional[datetime] = None
):
    return {
        "name": name if name else f"test-project-{random.randint(0, 10000000)}",
        "pi": pi,
        "staff1": staff1,
        "staff2": staff2,
        "status": status,
        "access": access,
        "accounting_group": accounting_group,
        "url": url,
        "date": date.isoformat() if date else None,
        "ticket": ticket,
        "last_contact": last_contact.isoformat() if last_contact else None
    }

@pytest.fixture
def project(client: Client):
    project_response = client.post(
        "/projects",
        json=project_data_f()
    )
    assert project_response.status_code == 201, "Creating a project should return a 201 status code"
    project = project_response.json()
    yield project
    client.delete(f"/projects/{project['id']}")

class TestProjects:

    def test_add_note(self, client, project):
        """Test adding a note to the database"""



        note_data = {
            "ticket": "TICKET-12",
            "note": "This is a test note.",
            "author": "test-author",
            ""
        }

        response = client.post(
            f"/projects/{project['id']}/notes",
            json=note_data,
        )

        assert response.status_code == 201, "Adding a note should return a 201 status code"

        data = response.json()

        assert data['ticket'] == note_data['ticket'], "The returned ticket does not match the input"
        assert data['note'] == note_data['note'], "The returned note does not match the input"
        assert data['author'] == note_data['author'], "The returned author does not match the input"