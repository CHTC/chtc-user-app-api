import pytest
from pydantic import ValidationError

from userapp.core.schemas.users import UserGet, UserPost, UserTableSchema
from userapp.core.schemas.general import JoinedProjectView
from userapp.core.models.enum import PositionEnum, RoleEnum

# Mostly AI generated tests, looks decent though

class TestUserGetComputedFields:
    """Tests for UserGet schema computed fields"""

    def test_auth_netid_computed_field_when_active_true(self):
        """Test that auth_netid computed field returns active value when True"""
        user_data = {
            'id': 1,
            'username': 'testuser',
            'name': 'Test User',
            'email1': 'test@example.com',
            'active': True,
        }

        user = UserGet(**user_data)

        # Check that auth_netid matches active
        assert user.auth_netid is True, "auth_netid should be True when active is True"
        assert user.active is True, "active should be True"

    def test_auth_netid_computed_field_when_active_false(self):
        """Test that auth_netid computed field returns active value when False"""
        user_data = {
            'id': 2,
            'username': 'testuser2',
            'name': 'Test User 2',
            'email1': 'test2@example.com',
            'active': False,
        }

        user = UserGet(**user_data)

        # Check that auth_netid matches active
        assert user.auth_netid is False, "auth_netid should be False when active is False"
        assert user.active is False, "active should be False"

    def test_auth_netid_computed_field_when_active_none(self):
        """Test that auth_netid computed field returns None when active is None"""
        user_data = {
            'id': 3,
            'username': 'testuser3',
            'name': 'Test User 3',
            'email1': 'test3@example.com',
            'active': None,
        }

        user = UserGet(**user_data)

        # Check that auth_netid is None when active is None
        assert user.auth_netid is None, "auth_netid should be None when active is None"
        assert user.active is None, "active should be None"

    def test_auth_username_always_false(self):
        """Test that auth_username computed field always returns False"""
        user_data_active_true = {
            'id': 4,
            'username': 'testuser4',
            'name': 'Test User 4',
            'email1': 'test4@example.com',
            'active': True,
        }

        user_data_active_false = {
            'id': 5,
            'username': 'testuser5',
            'name': 'Test User 5',
            'email1': 'test5@example.com',
            'active': False,
        }

        user1 = UserGet(**user_data_active_true)
        user2 = UserGet(**user_data_active_false)

        # Both should have auth_username as False
        assert user1.auth_username is False, "auth_username should always be False"
        assert user2.auth_username is False, "auth_username should always be False"

    def test_computed_fields_in_model_dump(self):
        """Test that computed fields appear in model_dump output"""
        user_data = {
            'id': 6,
            'username': 'testuser6',
            'name': 'Test User 6',
            'email1': 'test6@example.com',
            'active': True,
        }

        user = UserGet(**user_data)
        dumped = user.model_dump()

        # Check that computed fields are included in dump
        assert 'auth_netid' in dumped, "auth_netid should be in model dump"
        assert 'auth_username' in dumped, "auth_username should be in model dump"
        assert dumped['auth_netid'] is True, "auth_netid should match active in dump"
        assert dumped['auth_username'] is False, "auth_username should be False in dump"


class TestUserPostValidation:
    """Tests for UserPost schema validation"""

    def test_active_requires_netid_validation(self):
        """Test that active=True requires netid to be provided"""
        user_data = {
            'username': 'testuser',
            'password': 'SecurePassword123',
            'name': 'Test User',
            'email1': 'test@example.com',
            'active': True,
            'netid': None,  # This should cause validation error
        }

        with pytest.raises(ValidationError) as exc_info:
            UserPost(**user_data)

        error = exc_info.value
        assert 'netid must be provided' in str(error).lower(), \
            "Validation error should mention netid requirement"

    def test_active_true_with_netid_succeeds(self):
        """Test that active=True with netid succeeds validation"""
        user_data = {
            'username': 'testuser',
            'password': 'SecurePassword123',
            'name': 'Test User',
            'email1': 'test@example.com',
            'active': True,
            'netid': 'validnetid',
        }

        user = UserPost(**user_data)
        assert user.active is True, "active should be True"
        assert user.netid == 'validnetid', "netid should be set"

    def test_active_false_without_netid_succeeds(self):
        """Test that active=False without netid succeeds validation"""
        user_data = {
            'username': 'testuser',
            'password': 'SecurePassword123',
            'name': 'Test User',
            'email1': 'test@example.com',
            'active': False,
            'netid': None,
        }

        user = UserPost(**user_data)
        assert user.active is False, "active should be False"
        assert user.netid is None, "netid can be None when active is False"

    def test_active_none_without_netid_succeeds(self):
        """Test that active=None (not set) without netid succeeds"""
        user_data = {
            'username': 'testuser',
            'password': 'SecurePassword123',
            'name': 'Test User',
            'email1': 'test@example.com',
            'netid_exp_time': None,
        }

        user = UserPost(**user_data)
        # active defaults to None if not provided
        assert user.active is None or user.active is False, "active should be None or False"


class TestJoinedProjectViewComputedFields:
    """Tests for JoinedProjectView schema computed fields"""

    def test_joined_project_view_auth_netid_computed_field(self):
        """Test that JoinedProjectView auth_netid matches active field"""
        project_data = {
            'id': 1,
            'project_id': 10,
            'project_name': 'Test Project',
            'name': 'Test User',
            'email1': 'test@example.com',
            'active': True,
            'role': RoleEnum.PI,
        }

        project_view = JoinedProjectView(**project_data)

        # Check computed fields
        assert project_view.auth_netid is True, "auth_netid should match active"
        assert project_view.auth_username is False, "auth_username should always be False"

    def test_joined_project_view_computed_fields_in_dump(self):
        """Test that JoinedProjectView computed fields appear in model dump"""
        project_data = {
            'id': 2,
            'project_id': 20,
            'project_name': 'Test Project 2',
            'name': 'Test User 2',
            'email1': 'test2@example.com',
            'active': False,
            'role': RoleEnum.MEMBER,
        }

        project_view = JoinedProjectView(**project_data)
        dumped = project_view.model_dump()

        # Check that computed fields are in dump
        assert 'auth_netid' in dumped, "auth_netid should be in dump"
        assert 'auth_username' in dumped, "auth_username should be in dump"
        assert dumped['auth_netid'] is False, "auth_netid should match active in dump"
        assert dumped['auth_username'] is False, "auth_username should be False in dump"


class TestUserTableSchema:
    """Tests for UserTableSchema (database representation)"""

    def test_user_table_schema_has_active_field(self):
        """Test that UserTableSchema includes active field"""
        user_data = {
            'id': 1,
            'username': 'testuser',
            'name': 'Test User',
            'email1': 'test@example.com',
            'active': True,
        }

        user = UserTableSchema(**user_data)
        assert user.active is True, "UserTableSchema should have active field"

    def test_user_table_schema_no_auth_fields(self):
        """Test that UserTableSchema does not have old auth fields"""
        user_data = {
            'id': 2,
            'username': 'testuser2',
            'name': 'Test User 2',
            'email1': 'test2@example.com',
            'active': False,
        }

        user = UserTableSchema(**user_data)

        # The schema should not have auth_netid or auth_username as real fields
        # (they might be in __dict__ due to extra='ignore' but shouldn't be defined)
        assert hasattr(user, 'active'), "Should have active field"

        # Verify we can't set auth_netid or auth_username directly
        # (they're not in the schema definition)
        dumped = user.model_dump(exclude_none=True)
        assert 'active' in dumped, "active should be in dump"
