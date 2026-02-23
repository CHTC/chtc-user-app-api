"""convert_staff_fields_to_user_ids

Converts groups.point_of_contact, notes.author, projects.staff1, and
projects.staff2 from plain text usernames to integer foreign keys
referencing users.id.

Run alembic/scripts/loss_analysis.py before applying this migration to see
which values will be lost because they do not match

Matching strategy:
  - groups.point_of_contact  -> match against users.username
  - notes.author             -> match against users.id (stringified) first,
                                then fall back to users.username
  - projects.staff1          -> match against users.username
  - projects.staff2          -> match against users.username

Revision ID: f3a9c2e81d04
Revises: a674e0eb726a
Create Date: 2026-02-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c2e81d04'
down_revision: Union[str, Sequence[str], None] = 'a674e0eb726a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Add new integer columns alongside the old string ones
    # ------------------------------------------------------------------
    op.add_column('groups',   sa.Column('point_of_contact_new', sa.Integer(), nullable=True))
    op.add_column('notes',    sa.Column('author_new',           sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('staff1_new',           sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('staff2_new',           sa.Integer(), nullable=True))

    # ------------------------------------------------------------------
    # 3. Populate new columns by resolving string values → user IDs
    # ------------------------------------------------------------------

    # groups.point_of_contact: match by username
    # temporary hack to avoid violating the chk_unix_gid_range constraint while updating the groups table
    op.execute('ALTER TABLE groups DROP CONSTRAINT IF EXISTS chk_unix_gid_range')
    bind.execute(sa.text("""
        UPDATE groups
        SET    point_of_contact_new = u.id
        FROM   users u
        WHERE  groups.point_of_contact = u.username
    """))
    op.execute('ALTER TABLE groups ADD CONSTRAINT chk_unix_gid_range CHECK (unix_gid BETWEEN 40000 AND 60000) NOT VALID')

    # notes.author: match by stringified user id first, then by username
    bind.execute(sa.text("""
        UPDATE notes
        SET    author_new = (
                   SELECT u.id
                   FROM   users u
                   WHERE  u.id::text = notes.author
                      OR  u.username    = notes.author
                   LIMIT  1
               )
        WHERE  notes.author IS NOT NULL
    """))

    # projects.staff1: match by username
    bind.execute(sa.text("""
        UPDATE projects
        SET    staff1_new = u.id
        FROM   users u
        WHERE  projects.staff1 = u.username
    """))

    # projects.staff2: match by username
    bind.execute(sa.text("""
        UPDATE projects
        SET    staff2_new = u.id
        FROM   users u
        WHERE  projects.staff2 = u.username
    """))

    # ------------------------------------------------------------------
    # 4. Drop the views that reference projects.staff1 / projects.staff2
    #    (the column types are changing so we must recreate the view)
    # ------------------------------------------------------------------
    op.execute('DROP VIEW IF EXISTS joined_projects')
    op.execute('DROP VIEW IF EXISTS pi_projects')

    # ------------------------------------------------------------------
    # 5. Drop old string columns
    # ------------------------------------------------------------------
    op.drop_column('groups',   'point_of_contact')
    op.drop_column('notes',    'author')
    op.drop_column('projects', 'staff1')
    op.drop_column('projects', 'staff2')

    # ------------------------------------------------------------------
    # 6. Rename new columns to the canonical names
    # ------------------------------------------------------------------
    op.alter_column('groups',   'point_of_contact_new', new_column_name='point_of_contact')
    op.alter_column('notes',    'author_new',           new_column_name='author')
    op.alter_column('projects', 'staff1_new',           new_column_name='staff1')
    op.alter_column('projects', 'staff2_new',           new_column_name='staff2')

    # ------------------------------------------------------------------
    # 7. Add foreign-key constraints (SET NULL on delete so removing a
    #    user does not cascade-delete groups / notes / projects)
    # ------------------------------------------------------------------
    op.create_foreign_key(
        'fk_groups_point_of_contact', 'groups',   'users',
        ['point_of_contact'], ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_notes_author',            'notes',    'users',
        ['author'],           ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_projects_staff1',         'projects', 'users',
        ['staff1'],           ['id'], ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_projects_staff2',         'projects', 'users',
        ['staff2'],           ['id'], ondelete='SET NULL'
    )

    # ------------------------------------------------------------------
    # 8. Recreate views (staff1/staff2 are now integers)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE VIEW joined_projects AS
            SELECT
                u.id,
                p.id                    AS project_id,
                p.name                  AS project_name,
                p.staff1                AS project_staff1,
                p.staff2                AS project_staff2,
                p.status                AS project_status,
                p.last_contact          AS project_last_contact,
                p.accounting_group      AS project_accounting_group,
                up.is_primary           AS is_primary,
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
                    FROM   notes n
                    LEFT JOIN user_notes un ON n.id = un.note_id
                    WHERE  un.user_id    = up.user_id
                      AND  un.project_id = up.project_id
                    ORDER  BY n.id DESC
                    LIMIT  1
                ) AS last_note_ticket
            FROM  user_projects up
            JOIN  users    u ON up.user_id    = u.id
            JOIN  projects p ON up.project_id = p.id
    """)

    op.execute("""
        CREATE VIEW pi_projects AS
        SELECT
            u.id          AS user_id,
            u.name,
            u.email1,
            u.netid,
            u.phone1,
            p.id          AS project_id,
            p.name        AS project_name
        FROM  users u
        JOIN  user_projects up ON up.user_id = u.id
        JOIN  projects      p  ON p.id       = up.project_id
        WHERE up.role = 'PI'
    """)


def downgrade() -> None:
    """Downgrade schema — converts integer FK columns back to text."""

    bind = op.get_bind()

    # Drop views first
    op.execute('DROP VIEW IF EXISTS joined_projects')
    op.execute('DROP VIEW IF EXISTS pi_projects')

    # Drop FK constraints
    op.drop_constraint('fk_groups_point_of_contact', 'groups',   type_='foreignkey')
    op.drop_constraint('fk_notes_author',            'notes',    type_='foreignkey')
    op.drop_constraint('fk_projects_staff1',         'projects', type_='foreignkey')
    op.drop_constraint('fk_projects_staff2',         'projects', type_='foreignkey')

    # Add temporary text columns
    op.add_column('groups',   sa.Column('point_of_contact_old', sa.String(50),  nullable=True))
    op.add_column('notes',    sa.Column('author_old',           sa.String(255), nullable=True))
    op.add_column('projects', sa.Column('staff1_old',           sa.String(255), nullable=True))
    op.add_column('projects', sa.Column('staff2_old',           sa.String(255), nullable=True))

    # Restore values as username strings where possible
    op.execute('ALTER TABLE groups DROP CONSTRAINT IF EXISTS chk_unix_gid_range')
    bind.execute(sa.text("""
        UPDATE groups
        SET    point_of_contact_old = u.username
        FROM   users u
        WHERE  groups.point_of_contact = u.id
    """))
    op.execute('ALTER TABLE groups ADD CONSTRAINT chk_unix_gid_range CHECK (unix_gid BETWEEN 40000 AND 60000) NOT VALID')

    bind.execute(sa.text("""
        UPDATE notes
        SET    author_old = u.username
        FROM   users u
        WHERE  notes.author = u.id
    """))

    bind.execute(sa.text("""
        UPDATE projects
        SET    staff1_old = u.username
        FROM   users u
        WHERE  projects.staff1 = u.id
    """))

    bind.execute(sa.text("""
        UPDATE projects
        SET    staff2_old = u.username
        FROM   users u
        WHERE  projects.staff2 = u.id
    """))

    # Drop integer columns
    op.drop_column('groups',   'point_of_contact')
    op.drop_column('notes',    'author')
    op.drop_column('projects', 'staff1')
    op.drop_column('projects', 'staff2')

    # Rename text columns back
    op.alter_column('groups',   'point_of_contact_old', new_column_name='point_of_contact')
    op.alter_column('notes',    'author_old',           new_column_name='author')
    op.alter_column('projects', 'staff1_old',           new_column_name='staff1')
    op.alter_column('projects', 'staff2_old',           new_column_name='staff2')

    # Recreate views with text columns
    op.execute("""
        CREATE VIEW joined_projects AS
            SELECT
                u.id,
                p.id                    AS project_id,
                p.name                  AS project_name,
                p.staff1                AS project_staff1,
                p.staff2                AS project_staff2,
                p.status                AS project_status,
                p.last_contact          AS project_last_contact,
                p.accounting_group      AS project_accounting_group,
                up.is_primary           AS is_primary,
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
                (
                    SELECT n.ticket
                    FROM   notes n
                    LEFT JOIN user_notes un ON n.id = un.note_id
                    WHERE  un.user_id    = up.user_id
                      AND  un.project_id = up.project_id
                    ORDER  BY n.id DESC
                    LIMIT  1
                ) AS last_note_ticket
            FROM  user_projects up
            JOIN  users    u ON up.user_id    = u.id
            JOIN  projects p ON up.project_id = p.id
    """)

    op.execute("""
        CREATE VIEW pi_projects AS
        SELECT
            u.id          AS user_id,
            u.name,
            u.email1,
            u.netid,
            u.phone1,
            p.id          AS project_id,
            p.name        AS project_name
        FROM  users u
        JOIN  user_projects up ON up.user_id = u.id
        JOIN  projects      p  ON p.id       = up.project_id
        WHERE up.role = 'PI'
    """)
