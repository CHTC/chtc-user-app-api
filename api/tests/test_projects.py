import random
import base64
import os
from datetime import datetime
from typing import Optional

import pytest
from httpx import Client

from api.models import RoleEnum
from api.tests.main import basic_auth_client as client, filled_out_project, admin_user, project, user, user_factory, project_factory

class TestProjects:

    def test_get_projects(self, client):
        """Test getting projects from the database"""

        response = client.get("/projects")

        assert response.status_code == 200, "Getting projects should return a 200 status code"

        data = response.json()

        assert isinstance(data, list), "The returned data should be a list of projects"

    def test_add_note(self, client, filled_out_project):
        """Test adding a note to the database"""

        note_data = {
            "ticket": "TICKET13",
            "note": "This is a test note.",
            "author": "test-author",
            "users": [*map(lambda u: u['id'], filled_out_project['users'])]
        }

        response = client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )

        assert response.status_code == 201, "Adding a note should return a 201 status code"

        data = response.json()

        assert data['ticket'] == note_data['ticket'], "The returned ticket does not match the input"
        assert data['note'] == note_data['note'], "The returned note does not match the input"
        assert data['author'] == note_data['author'], "The returned author does not match the input"
        assert set(map(lambda x: x['id'], data['users'])) == set(note_data['users']), "The returned users do not match the input"

    def test_get_notes(self, client, filled_out_project):
        """Test getting notes from the database"""

        # Create the note
        note_data = {
            "ticket": "TICKET13",
            "note": "This is a test note.",
            "author": "test-author",
            "users": [*map(lambda u: u['id'], filled_out_project['users'])]
        }
        response = client.post(
            f"/projects/{filled_out_project['id']}/notes",
            json=note_data,
        )
        assert response.status_code == 201, "Adding a note should return a 201 status code"

        # Get the note
        note_response = client.get(
            f"/projects/{filled_out_project['id']}/notes",
        )
        assert note_response.status_code == 200, f"Getting notes should return a 200 status code instead got {note_response.text}"

        notes = note_response.json()
        assert len(notes) > 0, "There should be at least one note returned"

        # Check the notes data
        note = notes[0]
        assert note['ticket'] == note_data['ticket'], "The returned ticket does not match"
        assert note['note'] == note_data['note'], "The returned note does not match"
        assert note['author'] == note_data['author'], "The returned author does not match"
        assert set(map(lambda x: x['id'], note['users'])) == set(note_data['users']), "The returned users do not match"


    def test_list_project_users(self, client, filled_out_project):
        """Test listing users in a project"""

        response = client.get(
            f"/projects/{filled_out_project['id']}/users"
        )
        assert response.status_code == 200, f"Getting the project should return a 200 status code, instead got {response.text}"
        project_users = response.json()

        assert len(project_users) >= 1, "There should be at least one user in the project"


    def test_add_user_to_project(self, client, project, user):
        """Test adding a user to a project"""

        # Add the user to the project
        response = client.post(
            f"/projects/{project['id']}/users",
            json={
                "user_id": user['id'],
                "is_primary": False,
                "role": RoleEnum.MEMBER.value,
            }
        )
        assert response.status_code == 201, f"Adding a user to a project should return a 201 status code, instead got {response.text}"

        # Verify the user is in the project
        project_users_response = client.get(
            f"/projects/{project['id']}/users"
        )
        assert project_users_response.status_code == 200, f"Getting the project should return a 200 status code, instead got {project_users_response.text}"
        project_users = project_users_response.json()

        user_ids_in_project = [user['user_id'] for user in project_users]
        assert user['id'] in user_ids_in_project, "The created user should be in the project's users list"
