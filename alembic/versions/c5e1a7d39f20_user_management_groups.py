"""user management: groups as the single access primitive

Revision ID: c5e1a7d39f20
Revises: b2f6d8e4a9c1
Create Date: 2026-11-03 09:00:00.000000

See design/2026_11_User_Management. Projects and submit nodes become metadata on groups:
membership lives in group_members (users and groups as members), flattened into
group_effective_members, and user_projects / user_groups go away. managed_by moves from
the membership rows to the group: a group is synced by an external system or it is not.
"""
import json
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c5e1a7d39f20'
down_revision: Union[str, Sequence[str], None] = 'b2f6d8e4a9c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

entity_manager_enum = postgresql.ENUM('APPLICATION', 'MANIFEST', 'MORGRIDGE_AD', name='entity_manager_enum', create_type=False)
audit_action_enum = postgresql.ENUM(
    'member_added', 'member_removed', 'group_created', 'group_deleted', 'owner_group_changed', 'metadata_changed',
    name='audit_action_enum', create_type=False,
)

GROUP_NAME_MAX = 32

# Same statement as userapp.core.services.membership.RECOMPUTE_SQL. Migrations must not import
# application code, so it is duplicated; if the two diverge the service wins after the first write.
RECOMPUTE_DELETE_SQL = "DELETE FROM group_effective_members"
RECOMPUTE_INSERT_SQL = """
    WITH RECURSIVE r(root_id, group_id, path) AS (
        SELECT g.id, g.id, ARRAY[g.id]
        FROM groups g
        WHERE g.deleted_at IS NULL
        UNION ALL
        SELECT r.root_id, gm.member_group_id, r.path || gm.member_group_id
        FROM r
        JOIN group_members gm ON gm.group_id = r.group_id
        WHERE gm.member_group_id IS NOT NULL
          AND NOT gm.member_group_id = ANY(r.path)
    )
    INSERT INTO group_effective_members (group_id, user_id, path)
    SELECT r.root_id, gm.member_user_id, r.path
    FROM r
    JOIN group_members gm ON gm.group_id = r.group_id
    WHERE gm.member_user_id IS NOT NULL
"""


def _slugify(text: str) -> str:
    slug = re.sub(r'[^a-z0-9_-]', '_', text.lower())
    slug = re.sub(r'_+', '_', slug)
    return slug.strip('_-')


def _unique_name(taken: set, base: str, suffix: str = "") -> str:
    """Truncate base so base + suffix fits in 32 characters, then append _2, _3, ... while taken"""
    candidate = base[:GROUP_NAME_MAX - len(suffix)] + suffix
    n = 2
    while candidate in taken:
        number = f"_{n}"
        candidate = base[:GROUP_NAME_MAX - len(suffix) - len(number)] + suffix + number
        n += 1
    taken.add(candidate)
    return candidate


# --------------------------------------------------------------------------- #
#  Views                                                                       #
# --------------------------------------------------------------------------- #

# One row per distinct (group, user): group_effective_members holds one row per path.
_DISTINCT_EFFECTIVE = "(SELECT DISTINCT group_id, user_id FROM group_effective_members)"

# Group names along a path, in path order
_PATH_NAMES = """
    ARRAY(
        SELECT g.name
        FROM unnest(gem.path) WITH ORDINALITY AS t(group_id, ord)
        JOIN groups g ON g.id = t.group_id
        ORDER BY t.ord
    )
"""

NEW_VIEWS = {
    'group_members_view': f"""
        CREATE VIEW group_members_view AS
        SELECT
            gem.group_id,
            gem.user_id,
            bool_or(cardinality(gem.path) = 1) AS direct,
            jsonb_agg(to_jsonb(gem.path) ORDER BY cardinality(gem.path), gem.path) AS paths,
            jsonb_agg(to_jsonb({_PATH_NAMES}) ORDER BY cardinality(gem.path), gem.path) AS path_names,
            u.name,
            u.netid,
            u.username,
            u.email1,
            u.is_admin,
            u.active,
            u.unix_uid,
            u.position
        FROM group_effective_members gem
        JOIN users u ON u.id = gem.user_id
        GROUP BY gem.group_id, gem.user_id, u.id
    """,
    'user_groups_view': f"""
        CREATE VIEW user_groups_view AS
        SELECT
            gem.user_id,
            gem.group_id,
            bool_or(cardinality(gem.path) = 1) AS direct,
            jsonb_agg(to_jsonb(gem.path) ORDER BY cardinality(gem.path), gem.path) AS paths,
            jsonb_agg(to_jsonb({_PATH_NAMES}) ORDER BY cardinality(gem.path), gem.path) AS path_names,
            g.name,
            g.unix_gid,
            g.owner_group_id,
            g.description,
            g.managed_by,
            g.deleted_at
        FROM group_effective_members gem
        JOIN groups g ON g.id = gem.group_id
        GROUP BY gem.user_id, gem.group_id, g.id
    """,
    'joined_projects': f"""
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
                (u.primary_project_id = p.id) AS is_primary,
                (gm.id IS NOT NULL) AS direct,
                gm.created_at,
                gm.updated_at,
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
                (
                    SELECT n.ticket
                    FROM notes n
                    LEFT JOIN user_notes un ON n.id = un.note_id
                    WHERE un.user_id = u.id AND un.project_id = p.id
                    ORDER BY n.id DESC
                    LIMIT 1
                ) AS last_note_ticket,
                p.display_name AS project_display_name,
                EXISTS (
                    SELECT 1 FROM group_effective_members pig
                    WHERE pig.group_id = p.pi_group_id AND pig.user_id = u.id
                ) AS is_pi,
                p.pi_group_id AS project_pi_group_id,
                p.project_group_id AS project_project_group_id
            FROM projects p
            JOIN {_DISTINCT_EFFECTIVE} gem ON gem.group_id = p.project_group_id
            JOIN users u ON u.id = gem.user_id
            LEFT JOIN group_members gm ON gm.group_id = p.project_group_id AND gm.member_user_id = u.id
    """,
    'pi_projects': f"""
        CREATE VIEW pi_projects AS
        SELECT
            u.id AS user_id,
            u.name,
            u.email1,
            u.netid,
            u.phone1,
            p.id AS project_id,
            p.name AS project_name,
            p.display_name AS project_display_name
        FROM projects p
        JOIN {_DISTINCT_EFFECTIVE} gem ON gem.group_id = p.pi_group_id
        JOIN users u ON u.id = gem.user_id
    """,
    'user_submit_nodes': f"""
        CREATE VIEW user_submit_nodes AS
        SELECT gem.user_id, sn.id AS submit_node_id, sn.name AS submit_node_name,
               sn.id, sn.name, sn.group_id
        FROM submit_nodes sn
        JOIN {_DISTINCT_EFFECTIVE} gem ON gem.group_id = sn.group_id
    """,
}

NEW_VIEW_ORDER = ['group_members_view', 'user_groups_view', 'joined_projects', 'pi_projects', 'user_submit_nodes']

# Definitions the previous revisions left behind: joined_projects and pi_projects from
# 9b4e17c2d0a3, group_users and user_group_memberships from f2ec55925c4c, user_submit_nodes
# from 5a9269d00368.
OLD_VIEWS = {
    'joined_projects': """
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
                up.managed_by,
                up.created_at,
                up.updated_at,
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
                ) AS last_note_ticket,
                p.display_name AS project_display_name
            FROM user_projects up
            JOIN users u ON up.user_id = u.id
            JOIN projects p ON up.project_id = p.id
    """,
    'pi_projects': """
        CREATE VIEW pi_projects AS
        SELECT
            u.id AS user_id,
            u.name,
            u.email1,
            u.netid,
            u.phone1,
            p.id AS project_id,
            p.name AS project_name,
            p.display_name AS project_display_name
        FROM users u
        JOIN user_projects up ON up.user_id = u.id
        JOIN projects p ON p.id = up.project_id
        WHERE up.role = 'PI'
    """,
    'group_users': """
        CREATE OR REPLACE VIEW group_users AS
        SELECT
            ug.group_id,
            ug.user_id,
            ug.managed_by,
            ug.created_at,
            ug.updated_at,
            u.name,
            u.netid,
            u.username,
            u.is_admin,
            u.active,
            u.unix_uid
        FROM user_groups ug
        JOIN users u ON ug.user_id = u.id
    """,
    'user_group_memberships': """
        CREATE VIEW user_group_memberships AS
        SELECT
            ug.group_id,
            ug.user_id,
            ug.managed_by,
            ug.created_at,
            ug.updated_at,
            g.name,
            g.point_of_contact,
            g.unix_gid,
            g.has_groupdir
        FROM user_groups ug
        JOIN groups g ON ug.group_id = g.id
    """,
    'user_submit_nodes': """
        CREATE VIEW user_submit_nodes AS
        SELECT ug.user_id, sn.id AS submit_node_id, sn.name AS submit_node_name,
               sn.id, sn.name, sn.group_id
        FROM user_groups ug
        JOIN submit_nodes sn ON sn.group_id = ug.group_id
    """,
}

OLD_VIEW_ORDER = ['joined_projects', 'pi_projects', 'group_users', 'user_group_memberships', 'user_submit_nodes']


def _drop_views(names) -> None:
    for name in names:
        op.execute(f'DROP VIEW IF EXISTS {name}')


# --------------------------------------------------------------------------- #
#  Upgrade                                                                     #
# --------------------------------------------------------------------------- #

def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # The baseline trigger gives every group without a unix_gid the lowest free one. The design
    # says a null unix_gid means "no unix group", and the groups created below (pi, managers,
    # project) are not unix groups, so the trigger has to go before any of them are inserted.
    # trg_check_unix_gid_uid_unique stays.
    op.execute('DROP TRIGGER IF EXISTS trg_assign_lowest_unix_gid ON groups')

    audit_action_enum.create(bind, checkfirst=True)

    # ---- groups: altered in place so ids, names and unix_gids survive ----
    op.add_column('groups', sa.Column('owner_group_id', sa.Integer(), nullable=True))
    op.add_column('groups', sa.Column('description', sa.Text(), nullable=True))
    # Which system owns the group's user membership; a managed sync replaces it wholesale
    op.add_column('groups', sa.Column('managed_by', entity_manager_enum, server_default='APPLICATION', nullable=False))
    op.add_column('groups', sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('groups', sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False))
    op.add_column('groups', sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False))
    op.create_foreign_key('groups_owner_group_id_fkey', 'groups', 'groups', ['owner_group_id'], ['id'])
    op.create_index('ix_groups_owner_group_id', 'groups', ['owner_group_id'], unique=False)
    op.create_check_constraint('ck_groups_not_self_owned', 'groups', 'owner_group_id IS NULL OR owner_group_id <> id')

    # ---- group_members ----
    op.create_table(
        'group_members',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('member_user_id', sa.Integer(), nullable=True),
        sa.Column('member_group_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('(member_user_id IS NULL) <> (member_group_id IS NULL)', name='ck_group_members_one_member'),
        sa.CheckConstraint('member_group_id IS NULL OR member_group_id <> group_id', name='ck_group_members_not_self'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'member_user_id', name='group_members_user_distinct'),
        sa.UniqueConstraint('group_id', 'member_group_id', name='group_members_group_distinct'),
    )
    op.create_index('ix_group_members_id', 'group_members', ['id'], unique=False)
    op.create_index('ix_group_members_member_user_id', 'group_members', ['member_user_id'], unique=False)
    op.create_index('ix_group_members_member_group_id', 'group_members', ['member_group_id'], unique=False)

    # ---- group_effective_members: materialized, rewritten by the membership service ----
    op.create_table(
        'group_effective_members',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('path', postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'user_id', 'path'),
    )
    op.create_index('ix_group_effective_members_user_id', 'group_effective_members', ['user_id'], unique=False)

    # ---- projects / users ----
    op.add_column('projects', sa.Column('pi_group_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('project_group_id', sa.Integer(), nullable=True))
    op.create_foreign_key('projects_pi_group_id_fkey', 'projects', 'groups', ['pi_group_id'], ['id'])
    op.create_foreign_key('projects_project_group_id_fkey', 'projects', 'groups', ['project_group_id'], ['id'])
    op.create_index('ix_projects_pi_group_id', 'projects', ['pi_group_id'], unique=False)
    op.create_index('ix_projects_project_group_id', 'projects', ['project_group_id'], unique=False)

    op.add_column('users', sa.Column('primary_project_id', sa.Integer(), nullable=True))
    op.create_foreign_key('users_primary_project_id_fkey', 'users', 'projects', ['primary_project_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_users_primary_project_id', 'users', ['primary_project_id'], unique=False)

    # ---- audit_log ----
    op.create_table(
        'audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('occurred_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('action', audit_action_enum, nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('member_user_id', sa.Integer(), nullable=True),
        sa.Column('member_group_id', sa.Integer(), nullable=True),
        sa.Column('caused_by', sa.BigInteger(), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['member_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['member_group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['caused_by'], ['audit_log.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_log_group_id', 'audit_log', ['group_id'], unique=False)
    op.create_index('ix_audit_log_actor_id', 'audit_log', ['actor_id'], unique=False)
    op.create_index('ix_audit_log_member_user_id', 'audit_log', ['member_user_id'], unique=False)
    op.create_index('ix_audit_log_occurred_at', 'audit_log', ['occurred_at'], unique=False)

    # The old views read the tables dropped below
    _drop_views(OLD_VIEW_ORDER)

    # ---- Data migration (plain SQL: the ORM models describe the new schema, not this one) ----

    # Existing group memberships become direct user members. managed_by was per membership and
    # is now per group: a group whose memberships any external system managed is handed to that
    # system (the most common one when several did), everything else stays with the application.
    bind.execute(sa.text("""
        INSERT INTO group_members (group_id, member_user_id, created_at, updated_at)
        SELECT group_id, user_id, created_at, updated_at
        FROM user_groups
    """))
    bind.execute(sa.text("""
        UPDATE groups g
        SET managed_by = x.managed_by
        FROM (
            SELECT DISTINCT ON (group_id) group_id, managed_by
            FROM user_groups
            WHERE managed_by <> 'APPLICATION'
            GROUP BY group_id, managed_by
            ORDER BY group_id, count(*) DESC, managed_by
        ) x
        WHERE g.id = x.group_id
    """))

    taken = set(bind.execute(sa.text("SELECT name FROM groups")).scalars())

    def create_group(name: str, owner_group_id, project_id: int, role: str) -> int:
        group_id = bind.execute(
            # has_groupdir is still NOT NULL here and is dropped below
            sa.text("INSERT INTO groups (name, owner_group_id, has_groupdir) VALUES (:name, :owner, false) RETURNING id"),
            {"name": name, "owner": owner_group_id},
        ).scalar_one()
        # One group_created audit row per generated group, written by the system (actor NULL)
        details = {
            "name": name,
            "owner_group_id": owner_group_id,
            "created_for": {"entity": "project", "entity_id": project_id, "role": role},
            "migration": revision,
        }
        bind.execute(
            sa.text("""
                INSERT INTO audit_log (actor_id, action, group_id, details)
                VALUES (NULL, 'group_created', :group_id, CAST(:details AS jsonb))
            """),
            {"group_id": group_id, "details": json.dumps(details)},
        )
        return group_id

    def add_group_member(group_id: int, member_group_id: int) -> None:
        bind.execute(
            sa.text("INSERT INTO group_members (group_id, member_group_id) VALUES (:g, :m)"),
            {"g": group_id, "m": member_group_id},
        )

    projects = bind.execute(sa.text("SELECT id, name, pi FROM projects ORDER BY id")).all()
    for project_id, project_name, pi_user_id in projects:
        slug = _slugify(project_name) or "project"

        # pi_group has no owner, managers is owned by pi, project is owned by managers; the pi
        # group is a member of both managers and project (the design's Project section).
        pi_id = create_group(_unique_name(taken, slug, "_pi"), None, project_id, "pi")
        managers_id = create_group(_unique_name(taken, slug, "_managers"), pi_id, project_id, "managers")
        project_group_id = create_group(_unique_name(taken, slug), managers_id, project_id, "project")
        add_group_member(managers_id, pi_id)
        add_group_member(project_group_id, pi_id)

        bind.execute(
            sa.text("UPDATE projects SET pi_group_id = :pi, project_group_id = :project WHERE id = :id"),
            {"pi": pi_id, "project": project_group_id, "id": project_id},
        )

        # PIs: user_projects rows with role PI, plus projects.pi when it names a user
        bind.execute(
            sa.text("""
                INSERT INTO group_members (group_id, member_user_id, created_at, updated_at)
                SELECT :pi, user_id, created_at, updated_at
                FROM user_projects
                WHERE project_id = :project AND role = 'PI'
            """),
            {"pi": pi_id, "project": project_id},
        )
        if pi_user_id is not None:
            bind.execute(
                sa.text("""
                    INSERT INTO group_members (group_id, member_user_id)
                    SELECT :pi, u.id FROM users u WHERE u.id = :user_id
                    ON CONFLICT DO NOTHING
                """),
                {"pi": pi_id, "user_id": pi_user_id},
            )

        # Every existing project member (PIs included) stays a direct member of the project
        # group so created_at survives and the /managed syncs keep working. A project whose
        # memberships an external system managed hands its project group to that system.
        bind.execute(
            sa.text("""
                INSERT INTO group_members (group_id, member_user_id, created_at, updated_at)
                SELECT :project_group, user_id, created_at, updated_at
                FROM user_projects
                WHERE project_id = :project
            """),
            {"project_group": project_group_id, "project": project_id},
        )
        bind.execute(
            sa.text("""
                UPDATE groups
                SET managed_by = (
                    SELECT managed_by FROM user_projects
                    WHERE project_id = :project AND managed_by <> 'APPLICATION'
                    GROUP BY managed_by ORDER BY count(*) DESC, managed_by LIMIT 1
                )
                WHERE id = :project_group
                  AND EXISTS (SELECT 1 FROM user_projects WHERE project_id = :project AND managed_by <> 'APPLICATION')
            """),
            {"project_group": project_group_id, "project": project_id},
        )

    # is_primary becomes users.primary_project_id; the most recently updated row wins
    bind.execute(sa.text("""
        UPDATE users
        SET primary_project_id = x.project_id
        FROM (
            SELECT DISTINCT ON (user_id) user_id, project_id
            FROM user_projects
            WHERE is_primary
            ORDER BY user_id, updated_at DESC, id DESC
        ) x
        WHERE users.id = x.user_id
    """))

    bind.execute(sa.text(RECOMPUTE_DELETE_SQL))
    bind.execute(sa.text(RECOMPUTE_INSERT_SQL))

    # ---- Only now drop what the data came from ----
    op.drop_table('user_projects')
    op.drop_table('user_groups')
    op.execute('DROP FUNCTION IF EXISTS demote_other_primary_projects()')
    op.execute('DROP TYPE IF EXISTS role_enum')

    op.drop_index('ix_projects_pi', table_name='projects')
    op.drop_column('projects', 'pi')
    op.drop_constraint('fk_groups_point_of_contact', 'groups', type_='foreignkey')
    op.drop_column('groups', 'point_of_contact')
    op.drop_column('groups', 'has_groupdir')

    # A note may only be tied to a user who has access to the project, which is now membership
    # of the project group instead of a user_projects row.
    op.execute("""
        CREATE OR REPLACE FUNCTION check_user_in_project_for_note() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.user_id IS NULL THEN
                RETURN NEW;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM projects p
                JOIN group_effective_members gem ON gem.group_id = p.project_group_id
                WHERE p.id = NEW.project_id AND gem.user_id = NEW.user_id
            ) THEN
                RAISE EXCEPTION 'User % is not associated with project % for this note', NEW.user_id, NEW.project_id;
            END IF;
            RETURN NEW;
        END;
        $$
    """)

    for name in NEW_VIEW_ORDER:
        op.execute(NEW_VIEWS[name])


# --------------------------------------------------------------------------- #
#  Downgrade                                                                   #
# --------------------------------------------------------------------------- #

def downgrade() -> None:
    """Downgrade schema (best effort).

    Groups generated for projects by upgrade() (and any groups created since) are left in
    place: they are ordinary rows in groups, and removing them could orphan submit nodes and
    other references. Only the data the old tables could hold is carried back.
    """
    bind = op.get_bind()

    _drop_views(reversed(NEW_VIEW_ORDER))

    # ---- Old columns and tables ----
    op.execute("CREATE TYPE role_enum AS ENUM ('MEMBER', 'PI')")
    role_enum = postgresql.ENUM('MEMBER', 'PI', name='role_enum', create_type=False)

    op.add_column('projects', sa.Column('pi', sa.Integer(), nullable=True))
    op.create_index('ix_projects_pi', 'projects', ['pi'], unique=False)
    op.add_column('groups', sa.Column('point_of_contact', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_groups_point_of_contact', 'groups', 'users', ['point_of_contact'], ['id'], ondelete='SET NULL')
    op.add_column('groups', sa.Column('has_groupdir', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.alter_column('groups', 'has_groupdir', server_default=None)

    op.create_table(
        'user_groups',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('managed_by', entity_manager_enum, server_default='APPLICATION', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'group_id', name='user_groups_distinct'),
    )
    op.create_index('ix_user_groups_id', 'user_groups', ['id'], unique=False)
    op.create_index('ix_user_groups_group_id', 'user_groups', ['group_id'], unique=False)
    op.create_index('idx_user_group_managed_by', 'user_groups', ['group_id', 'managed_by', 'user_id'], unique=False)

    op.create_table(
        'user_projects',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', role_enum, nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False),
        sa.Column('managed_by', entity_manager_enum, server_default='APPLICATION', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'project_id', name='user_projects_distinct'),
    )
    op.create_index('ix_user_projects_id', 'user_projects', ['id'], unique=False)
    op.create_index('ix_user_projects_project_id', 'user_projects', ['project_id'], unique=False)
    op.create_index('idx_user_project_managed_by', 'user_projects', ['project_id', 'managed_by', 'user_id'], unique=False)

    # ---- Data back ----

    # Direct members of a project group, plus direct members of its pi group who are not in it
    bind.execute(sa.text("""
        INSERT INTO user_projects (project_id, user_id, role, is_primary, managed_by, created_at, updated_at)
        SELECT
            p.id,
            gm.member_user_id,
            CASE WHEN EXISTS (
                SELECT 1 FROM group_members pgm
                WHERE pgm.group_id = p.pi_group_id AND pgm.member_user_id = gm.member_user_id
            ) THEN 'PI'::role_enum ELSE 'MEMBER'::role_enum END,
            COALESCE(u.primary_project_id = p.id, false),
            pg.managed_by,
            gm.created_at,
            gm.updated_at
        FROM projects p
        JOIN groups pg ON pg.id = p.project_group_id
        JOIN group_members gm ON gm.group_id = p.project_group_id AND gm.member_user_id IS NOT NULL
        JOIN users u ON u.id = gm.member_user_id
    """))
    bind.execute(sa.text("""
        INSERT INTO user_projects (project_id, user_id, role, is_primary, managed_by, created_at, updated_at)
        SELECT
            p.id,
            gm.member_user_id,
            'PI'::role_enum,
            COALESCE(u.primary_project_id = p.id, false),
            pg.managed_by,
            gm.created_at,
            gm.updated_at
        FROM projects p
        JOIN groups pg ON pg.id = p.pi_group_id
        JOIN group_members gm ON gm.group_id = p.pi_group_id AND gm.member_user_id IS NOT NULL
        JOIN users u ON u.id = gm.member_user_id
        ON CONFLICT ON CONSTRAINT user_projects_distinct DO NOTHING
    """))
    bind.execute(sa.text("""
        UPDATE projects p
        SET pi = (
            SELECT min(gm.member_user_id)
            FROM group_members gm
            WHERE gm.group_id = p.pi_group_id AND gm.member_user_id IS NOT NULL
        )
    """))

    # Direct user memberships of every group that is not a project's pi or project group
    # (those are already represented in user_projects)
    bind.execute(sa.text("""
        INSERT INTO user_groups (group_id, user_id, managed_by, created_at, updated_at)
        SELECT gm.group_id, gm.member_user_id, g.managed_by, gm.created_at, gm.updated_at
        FROM group_members gm
        JOIN groups g ON g.id = gm.group_id
        WHERE gm.member_user_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM projects p
              WHERE p.pi_group_id = gm.group_id OR p.project_group_id = gm.group_id
          )
    """))

    # ---- Drop what the new schema added ----
    op.drop_table('audit_log')
    op.drop_table('group_effective_members')
    op.drop_table('group_members')

    op.drop_index('ix_users_primary_project_id', table_name='users')
    op.drop_constraint('users_primary_project_id_fkey', 'users', type_='foreignkey')
    op.drop_column('users', 'primary_project_id')

    op.drop_index('ix_projects_project_group_id', table_name='projects')
    op.drop_index('ix_projects_pi_group_id', table_name='projects')
    op.drop_constraint('projects_project_group_id_fkey', 'projects', type_='foreignkey')
    op.drop_constraint('projects_pi_group_id_fkey', 'projects', type_='foreignkey')
    op.drop_column('projects', 'project_group_id')
    op.drop_column('projects', 'pi_group_id')

    op.drop_constraint('ck_groups_not_self_owned', 'groups', type_='check')
    op.drop_index('ix_groups_owner_group_id', table_name='groups')
    op.drop_constraint('groups_owner_group_id_fkey', 'groups', type_='foreignkey')
    for column in ('updated_at', 'created_at', 'deleted_at', 'managed_by', 'description', 'owner_group_id'):
        op.drop_column('groups', column)

    audit_action_enum.drop(bind, checkfirst=True)

    # ---- Old triggers and functions ----
    op.execute("""
        CREATE OR REPLACE FUNCTION check_user_in_project_for_note() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.user_id IS NULL THEN
                RETURN NEW;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM user_projects
                WHERE user_id = NEW.user_id AND project_id = NEW.project_id
            ) THEN
                RAISE EXCEPTION 'User % is not associated with project % for this note', NEW.user_id, NEW.project_id;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    # As e4b9a2c6d1f7 defined them; b2f6d8e4a9c1 removed the other triggers but not this one.
    op.execute("""
        CREATE OR REPLACE FUNCTION demote_other_primary_projects() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            UPDATE user_projects
            SET is_primary = false
            WHERE user_id = NEW.user_id
              AND id <> NEW.id
              AND is_primary;
            RETURN NULL;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_demote_other_primary_projects
        AFTER INSERT OR UPDATE OF is_primary ON user_projects
        FOR EACH ROW WHEN (NEW.is_primary)
        EXECUTE FUNCTION demote_other_primary_projects()
    """)
    op.execute("""
        CREATE TRIGGER trg_assign_lowest_unix_gid
        BEFORE INSERT ON groups
        FOR EACH ROW EXECUTE FUNCTION assign_lowest_unix_gid()
    """)

    for name in OLD_VIEW_ORDER:
        op.execute(OLD_VIEWS[name])
