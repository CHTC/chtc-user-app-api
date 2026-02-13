"""Collapse auth_netid and auth_username into active field

Revision ID: a674e0eb726a
Revises: 1d68d572169d
Create Date: 2026-02-02 11:24:03.500632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a674e0eb726a'
down_revision: Union[str, Sequence[str], None] = 'cd61b41c6c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # temporarily drop all check constraints on users table to avoid constraint violations during migration
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_username_or_netid_not_null')
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_password_if_username_not_null')
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_name_no_colon_semicolon')

    # drop the view first since it depends on the columns we're about to drop
    op.execute('DROP VIEW IF EXISTS joined_projects')

    # create active field
    op.add_column('users', sa.Column('active', sa.Boolean(), nullable=True))
    # set active field to prev auth_netid value
    op.execute('UPDATE users SET active = auth_netid')
    # set active field to non-nullable with default false
    op.alter_column('users', 'active', nullable=False, server_default='false')

    # drop auth_username and auth_netid
    op.drop_column('users', 'auth_username')
    op.drop_column('users', 'auth_netid')

    # recreate joined_projects view with new schema
    op.execute("""
        CREATE VIEW joined_projects AS
            SELECT
                u.id,
                p.id AS project_id,
                p.name AS project_name,
                p.staff1 AS project_staff1,
                p.staff2 AS project_staff2,
                p.status AS project_status,
                p.last_contact AS project_last_contact,
                p.accounting_group AS project_accounting_group,
                up.is_primary AS is_primary,
                u.username,
                u.name,
                u.email1,
                u.email2,
                u.netid,
                u.netid_exp_datetime,
                u.phone1,
                u.phone2,
                u.is_admin,
                u.active,
                u.date,
                u.unix_uid,
                u.position,
                up.role,
                ( SELECT n.ticket FROM notes n LEFT JOIN user_notes un ON n.id = un.note_id WHERE un.user_id = up.user_id AND un.project_id = up.project_id ORDER BY n.id DESC LIMIT 1 ) AS last_note_ticket
            FROM user_projects up
            JOIN users u ON up.user_id = u.id
            JOIN projects p ON up.project_id = p.id
    """)

    # re-add the constraints
    op.execute('ALTER TABLE users ADD CONSTRAINT chk_username_or_netid_not_null CHECK (username IS NOT NULL OR netid IS NOT NULL) NOT VALID')
    op.execute('ALTER TABLE users ADD CONSTRAINT chk_password_if_username_not_null CHECK (username IS NULL OR password IS NOT NULL) NOT VALID')
    op.execute('ALTER TABLE users ADD CONSTRAINT chk_name_no_colon_semicolon CHECK (name !~ \':\'  AND name !~ \';\') NOT VALID')


def downgrade() -> None:
    """Downgrade schema."""
    # temporarily drop all check constraints on users table to avoid constraint violations during migration
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_username_or_netid_not_null')
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_password_if_username_not_null')
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_name_no_colon_semicolon')

    # drop the view first since it depends on the columns we're modifying
    op.execute('DROP VIEW IF EXISTS joined_projects')

    # re-add auth_netid and auth_username columns
    op.add_column('users', sa.Column('auth_netid', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('auth_username', sa.BOOLEAN(), autoincrement=False, nullable=True))

    # migrate data back: set auth_netid = active, auth_username = False
    # (technically this is lossy since we don't know previous auth_username values)
    op.execute('UPDATE users SET auth_netid = active, auth_username = false')

    # set auth_netid and auth_username to non-nullable with defaults
    op.alter_column('users', 'auth_netid', nullable=False, server_default='false')
    op.alter_column('users', 'auth_username', nullable=False, server_default='false')

    # drop active column
    op.drop_column('users', 'active')

    # recreate view with original schema
    op.execute("""
        CREATE VIEW joined_projects AS
            SELECT
                u.id,
                p.id AS project_id,
                p.name AS project_name,
                p.staff1 AS project_staff1,
                p.staff2 AS project_staff2,
                p.status AS project_status,
                p.last_contact AS project_last_contact,
                p.accounting_group AS project_accounting_group,
                up.is_primary AS is_primary,
                u.username,
                u.name,
                u.email1,
                u.email2,
                u.netid,
                u.netid_exp_datetime,
                u.phone1,
                u.phone2,
                u.is_admin,
                u.auth_netid,
                u.auth_username,
                u.date,
                u.unix_uid,
                u.position,
                up.role,
                ( SELECT n.ticket FROM notes n LEFT JOIN user_notes un ON n.id = un.note_id WHERE un.user_id = up.user_id AND un.project_id = up.project_id ORDER BY n.id DESC LIMIT 1 ) AS last_note_ticket
            FROM user_projects up
            JOIN users u ON up.user_id = u.id
            JOIN projects p ON up.project_id = p.id
    """)

    # re-add the constraints
    op.execute('ALTER TABLE users ADD CONSTRAINT chk_username_or_netid_not_null CHECK (username IS NOT NULL OR netid IS NOT NULL) NOT VALID')
    op.execute('ALTER TABLE users ADD CONSTRAINT chk_password_if_username_not_null CHECK (username IS NULL OR password IS NOT NULL) NOT VALID')
    op.execute('ALTER TABLE users ADD CONSTRAINT chk_name_no_colon_semicolon CHECK (name !~ \':\'  AND name !~ \';\') NOT VALID')
