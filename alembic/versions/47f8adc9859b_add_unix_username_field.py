"""Add unix username field

Revision ID: 47f8adc9859b
Revises: 4aa2a7d34719
Create Date: 2026-04-20 10:27:12.467103

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47f8adc9859b'
down_revision: Union[str, Sequence[str], None] = '4aa2a7d34719'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


netid_username_map = {
    "aschneider37": "austins",
}


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('DROP VIEW IF EXISTS joined_projects')
    op.add_column('users', sa.Column('username', sa.String(length=255), nullable=True))
    users_table = sa.table(
        'users',
        sa.column('id', sa.Integer()),
        sa.column('netid', sa.String(length=255)),
        sa.column('username', sa.String(length=255)),
    )

    op.execute("""
        UPDATE users
        SET username = netid
        WHERE active IS TRUE
    """)

    for netid, username in netid_username_map.items():
        op.execute(
            users_table.update()
            .where(users_table.c.netid == netid)
            .values(username=username)
        )

    op.create_unique_constraint(op.f('users_username_key'), 'users', ['username'])
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
                u.name,
                u.username,
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
                (
                    SELECT n.ticket
                    FROM notes n
                    LEFT JOIN user_notes un ON n.id = un.note_id
                    WHERE un.user_id = up.user_id AND un.project_id = up.project_id
                    ORDER BY n.id DESC
                    LIMIT 1
                ) AS last_note_ticket
            FROM user_projects up
            JOIN users u ON up.user_id = u.id
            JOIN projects p ON up.project_id = p.id
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute('DROP VIEW IF EXISTS joined_projects')
    op.drop_constraint(op.f('users_username_key'), 'users', type_='unique')
    op.drop_column('users', 'username')
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
                (
                    SELECT n.ticket
                    FROM notes n
                    LEFT JOIN user_notes un ON n.id = un.note_id
                    WHERE un.user_id = up.user_id AND un.project_id = up.project_id
                    ORDER BY n.id DESC
                    LIMIT 1
                ) AS last_note_ticket
            FROM user_projects up
            JOIN users u ON up.user_id = u.id
            JOIN projects p ON up.project_id = p.id
    """)
