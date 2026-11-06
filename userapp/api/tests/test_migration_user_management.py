"""Shape of the schema after `alembic upgrade head` for the user management redesign.

The old tables are dropped by the migration, so the data mapping cannot be tested from here
(there is nothing to seed): this only checks that the schema the application expects is the
schema the migration leaves behind.
"""
import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from userapp.api.tests.conftest import _seed_db_url
from userapp.db import connect_engine


def _rows(sql: str, **params) -> list[dict]:
    async def run():
        engine = await connect_engine(_seed_db_url())
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(sql), params)
                return [dict(row._mapping) for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _column_set(sql: str, **params) -> set:
    return {tuple(r.values()) if len(r) > 1 else next(iter(r.values())) for r in _rows(sql, **params)}


def _tables() -> set[str]:
    return _column_set("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'")


def _views() -> set[str]:
    return _column_set("SELECT table_name FROM information_schema.views WHERE table_schema = 'public'")


def _columns(table: str) -> dict[str, dict]:
    rows = _rows(
        "SELECT column_name, data_type, udt_name, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t",
        t=table,
    )
    return {r['column_name']: r for r in rows}


def _constraints(table: str, kind: str) -> dict[str, str]:
    """name -> definition for constraints of the given pg_constraint contype"""
    rows = _rows(
        "SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint "
        "WHERE conrelid = CAST(:t AS regclass) AND contype::text = :k",
        t=table, k=kind,
    )
    return {r['conname']: r['definition'] for r in rows}


def _indexes(table: str) -> set[str]:
    return _column_set("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = :t", t=table)


class TestTables:

    def test_new_tables_exist_and_old_ones_are_gone(self):
        tables = _tables()
        assert {'groups', 'group_members', 'group_effective_members', 'audit_log'} <= tables
        assert not {'backing_stores', 'data_access'} & tables
        assert 'user_projects' not in tables
        assert 'user_groups' not in tables

    def test_role_enum_is_gone_and_audit_action_enum_exists(self):
        assert _rows("SELECT 1 FROM pg_type WHERE typname = 'role_enum'") == []
        labels = _column_set(
            "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'audit_action_enum'"
        )
        assert labels == {'member_added', 'member_removed', 'group_created', 'group_deleted', 'owner_group_changed', 'metadata_changed'}

    def test_groups_columns(self):
        columns = _columns('groups')
        assert {'id', 'name', 'unix_gid', 'owner_group_id', 'description', 'managed_by', 'deleted_at', 'created_at', 'updated_at'} <= set(columns)
        assert not {'point_of_contact', 'has_groupdir', 'expires_at'} & set(columns)
        assert columns['name']['is_nullable'] == 'NO'
        assert columns['managed_by']['udt_name'] == 'entity_manager_enum'
        assert columns['managed_by']['is_nullable'] == 'NO' and 'APPLICATION' in columns['managed_by']['column_default']
        assert columns['unix_gid']['is_nullable'] == 'YES'
        assert columns['owner_group_id']['is_nullable'] == 'YES'
        assert columns['deleted_at']['is_nullable'] == 'YES'
        assert columns['created_at']['is_nullable'] == 'NO' and 'now()' in columns['created_at']['column_default']
        assert columns['updated_at']['is_nullable'] == 'NO' and 'now()' in columns['updated_at']['column_default']

    def test_groups_constraints(self):
        assert 'ck_groups_not_self_owned' in _constraints('groups', 'c')
        assert any('owner_group_id' in d and 'REFERENCES groups(id)' in d for d in _constraints('groups', 'f').values())
        unique = " ".join(_constraints('groups', 'u').values())
        assert 'UNIQUE (name)' in unique and 'UNIQUE (unix_gid)' in unique

    def test_group_members_shape(self):
        columns = _columns('group_members')
        assert set(columns) == {'id', 'group_id', 'member_user_id', 'member_group_id', 'created_at', 'updated_at'}
        assert columns['group_id']['is_nullable'] == 'NO'
        assert columns['member_user_id']['is_nullable'] == 'YES' and columns['member_group_id']['is_nullable'] == 'YES'

        assert {'ck_group_members_one_member', 'ck_group_members_not_self'} <= set(_constraints('group_members', 'c'))
        unique = " ".join(_constraints('group_members', 'u').values())
        assert 'UNIQUE (group_id, member_user_id)' in unique and 'UNIQUE (group_id, member_group_id)' in unique
        assert {'ix_group_members_member_user_id', 'ix_group_members_member_group_id'} <= _indexes('group_members')

        # Deleting a group or a user takes their membership rows with them
        for definition in _constraints('group_members', 'f').values():
            assert 'ON DELETE CASCADE' in definition

    def test_group_effective_members_shape(self):
        columns = _columns('group_effective_members')
        assert set(columns) == {'group_id', 'user_id', 'path'}
        assert columns['path']['data_type'] == 'ARRAY' and columns['path']['udt_name'] == '_int4'
        assert all(c['is_nullable'] == 'NO' for c in columns.values())
        assert _constraints('group_effective_members', 'p') == {
            'group_effective_members_pkey': 'PRIMARY KEY (group_id, user_id, path)'
        }
        assert 'ix_group_effective_members_user_id' in _indexes('group_effective_members')

    def test_projects_and_users_columns(self):
        projects = _columns('projects')
        assert {'pi_group_id', 'project_group_id'} <= set(projects)
        assert not {'pi', 'expires_at'} & set(projects)
        assert all(projects[c]['is_nullable'] == 'YES' for c in ('pi_group_id', 'project_group_id'))
        assert {'ix_projects_pi_group_id', 'ix_projects_project_group_id'} <= _indexes('projects')

        users = _columns('users')
        assert users['primary_project_id']['is_nullable'] == 'YES'
        assert 'ix_users_primary_project_id' in _indexes('users')
        [definition] = [d for d in _constraints('users', 'f').values() if 'primary_project_id' in d]
        assert 'REFERENCES projects(id) ON DELETE SET NULL' in definition

    def test_audit_log_shape(self):
        columns = _columns('audit_log')
        assert set(columns) == {'id', 'occurred_at', 'actor_id', 'action', 'group_id', 'member_user_id', 'member_group_id', 'caused_by', 'details'}
        assert columns['id']['data_type'] == 'bigint'
        assert columns['caused_by']['data_type'] == 'bigint'
        assert columns['details']['udt_name'] == 'jsonb'
        assert columns['action']['udt_name'] == 'audit_action_enum' and columns['action']['is_nullable'] == 'NO'
        assert columns['occurred_at']['is_nullable'] == 'NO' and 'now()' in columns['occurred_at']['column_default']
        assert {'ix_audit_log_group_id', 'ix_audit_log_actor_id', 'ix_audit_log_member_user_id', 'ix_audit_log_occurred_at'} <= _indexes('audit_log')

        fks = _constraints('audit_log', 'f')
        [actor] = [d for d in fks.values() if d.startswith('FOREIGN KEY (actor_id)')]
        [member] = [d for d in fks.values() if d.startswith('FOREIGN KEY (member_user_id)')]
        assert 'ON DELETE SET NULL' in actor and 'ON DELETE SET NULL' in member
        [caused_by] = [d for d in fks.values() if d.startswith('FOREIGN KEY (caused_by)')]
        assert 'REFERENCES audit_log(id)' in caused_by

    def test_submit_nodes_unchanged(self):
        assert set(_columns('submit_nodes')) == {'id', 'name', 'group_id'}
        [definition] = _constraints('submit_nodes', 'f').values()
        assert 'REFERENCES groups(id) ON DELETE SET NULL' in definition


class TestViews:

    def test_views_exist_and_old_ones_are_gone(self):
        views = _views()
        assert {'group_members_view', 'user_groups_view', 'joined_projects', 'pi_projects', 'user_submit_nodes'} <= views
        assert 'group_users' not in views and 'user_group_memberships' not in views

    def test_group_members_view_columns(self):
        assert set(_columns('group_members_view')) == {
            'group_id', 'user_id', 'direct', 'paths', 'path_names',
            'name', 'netid', 'username', 'email1', 'is_admin', 'active', 'unix_uid', 'position',
        }

    def test_user_groups_view_columns(self):
        assert set(_columns('user_groups_view')) == {
            'user_id', 'group_id', 'direct', 'paths', 'path_names', 'is_owner',
            'name', 'unix_gid', 'owner_group_id', 'description', 'managed_by', 'deleted_at',
        }

    def test_joined_projects_columns(self):
        columns = set(_columns('joined_projects'))
        assert not {'role', 'managed_by', 'project_expires_at'} & columns
        assert {'is_primary', 'is_pi', 'direct', 'project_pi_group_id', 'project_project_group_id',
                'project_display_name', 'last_note_ticket', 'id', 'project_id'} <= columns

    def test_other_views_keep_their_columns(self):
        assert set(_columns('pi_projects')) == {'user_id', 'name', 'email1', 'netid', 'phone1', 'project_id', 'project_name', 'project_display_name'}
        assert set(_columns('user_submit_nodes')) == {'user_id', 'submit_node_id', 'submit_node_name', 'id', 'name', 'group_id'}


class TestTriggers:

    def test_unix_gid_is_no_longer_assigned_automatically(self):
        triggers = _column_set("SELECT tgname FROM pg_trigger WHERE tgrelid = 'groups'::regclass AND NOT tgisinternal")
        assert 'trg_assign_lowest_unix_gid' not in triggers
        assert 'trg_check_unix_gid_uid_unique' in triggers

    def test_note_trigger_reads_group_membership(self):
        [row] = _rows("SELECT pg_get_functiondef('check_user_in_project_for_note'::regproc) AS definition")
        assert 'group_effective_members' in row['definition']
        assert 'user_projects' not in row['definition']


class TestConstraintsAreEnforced:
    """The CHECK constraints reject the rows the design forbids, whatever the application does"""

    @staticmethod
    def _violation(statements: list[tuple[str, dict]]) -> bool:
        async def run():
            engine = await connect_engine(_seed_db_url())
            try:
                async with engine.connect() as conn:
                    try:
                        for sql, params in statements:
                            await conn.execute(text(sql), params)
                    except DBAPIError:
                        return True
                    return False
                    # no commit: the connection rolls everything back when it closes
            finally:
                await engine.dispose()

        return asyncio.run(run())

    def test_group_cannot_own_itself(self):
        assert self._violation([
            ("INSERT INTO groups (id, name) VALUES (910001, 'mig-self-owner')", {}),
            ("UPDATE groups SET owner_group_id = 910001 WHERE id = 910001", {}),
        ])

    def test_group_member_needs_exactly_one_member(self):
        setup = ("INSERT INTO groups (id, name) VALUES (910002, 'mig-one-member')", {})
        assert self._violation([setup, ("INSERT INTO group_members (group_id) VALUES (910002)", {})])
        assert self._violation([
            setup,
            ("INSERT INTO group_members (group_id, member_user_id, member_group_id) VALUES (910002, 4, 910002)", {}),
        ])

    def test_group_cannot_be_its_own_member(self):
        assert self._violation([
            ("INSERT INTO groups (id, name) VALUES (910003, 'mig-self-member')", {}),
            ("INSERT INTO group_members (group_id, member_group_id) VALUES (910003, 910003)", {}),
        ])

    def test_memberships_are_unique(self):
        assert self._violation([
            ("INSERT INTO groups (id, name) VALUES (910004, 'mig-unique')", {}),
            ("INSERT INTO group_members (group_id, member_user_id) VALUES (910004, 4)", {}),
            ("INSERT INTO group_members (group_id, member_user_id) VALUES (910004, 4)", {}),
        ])

    def test_valid_rows_are_accepted(self):
        assert not self._violation([
            ("INSERT INTO groups (id, name) VALUES (910005, 'mig-valid-a'), (910006, 'mig-valid-b')", {}),
            ("UPDATE groups SET owner_group_id = 910006 WHERE id = 910005", {}),
            ("INSERT INTO group_members (group_id, member_user_id) VALUES (910005, 4)", {}),
            ("INSERT INTO group_members (group_id, member_group_id) VALUES (910005, 910006)", {}),
        ])
