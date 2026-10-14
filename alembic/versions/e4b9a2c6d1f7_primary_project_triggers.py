"""keep one primary project per user, and active users with one

Revision ID: e4b9a2c6d1f7
Revises: c7d2e4f8a1b6
Create Date: 2026-10-14 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e4b9a2c6d1f7'
down_revision: Union[str, Sequence[str], None] = 'c7d2e4f8a1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The API turns exceptions that start with this marker into a 400 whose detail is
# the rest of the message (see userapp.api.util.trigger_error_detail).
MARKER = 'primary_project_rule: '


def upgrade() -> None:
    # These triggers only look at the rows being written, so users who already
    # break a rule are left alone until one of these writes touches them.

    # 1. A user has one primary project. Whenever a membership row is inserted as
    # primary or updated to primary, clear is_primary on that user's other rows.
    # This runs for every writer (API routes, the managed syncs, scripts), so when
    # several writes make different projects primary the last one wins.
    # The WHEN clause keeps the trigger from re-firing on its own demotions.
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

    # An active user needs a primary project; an inactive user may have none.

    # 2. A user can't be made active (inactive -> active) without a primary project.
    op.execute(f"""
        CREATE OR REPLACE FUNCTION require_primary_project_to_activate() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM user_projects WHERE user_id = NEW.id AND is_primary
            ) THEN
                RAISE EXCEPTION '{MARKER}A user must have a primary project before they can be made active'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_require_primary_project_to_activate
        BEFORE UPDATE OF active ON users
        FOR EACH ROW WHEN (NEW.active IS TRUE AND OLD.active IS DISTINCT FROM TRUE)
        EXECUTE FUNCTION require_primary_project_to_activate()
    """)

    # 3. An active user's primary membership can't be unset or deleted unless
    # another membership of theirs is primary. Deleting the user or the project
    # cascades to the membership and is allowed: by then the user or project row
    # is gone, so there is nothing left to check.
    op.execute(f"""
        CREATE OR REPLACE FUNCTION keep_primary_project_for_active_user() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE id = OLD.user_id AND active)
               AND EXISTS (SELECT 1 FROM projects WHERE id = OLD.project_id)
               AND NOT EXISTS (
                   SELECT 1 FROM user_projects WHERE user_id = OLD.user_id AND is_primary
               ) THEN
                RAISE EXCEPTION '{MARKER}An active user must keep a primary project, make another project primary first'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NULL;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_keep_primary_project_on_unset
        AFTER UPDATE OF is_primary ON user_projects
        FOR EACH ROW WHEN (OLD.is_primary AND NOT NEW.is_primary)
        EXECUTE FUNCTION keep_primary_project_for_active_user()
    """)
    op.execute("""
        CREATE TRIGGER trg_keep_primary_project_on_delete
        AFTER DELETE ON user_projects
        FOR EACH ROW WHEN (OLD.is_primary)
        EXECUTE FUNCTION keep_primary_project_for_active_user()
    """)


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS trg_keep_primary_project_on_delete ON user_projects')
    op.execute('DROP TRIGGER IF EXISTS trg_keep_primary_project_on_unset ON user_projects')
    op.execute('DROP FUNCTION IF EXISTS keep_primary_project_for_active_user()')
    op.execute('DROP TRIGGER IF EXISTS trg_require_primary_project_to_activate ON users')
    op.execute('DROP FUNCTION IF EXISTS require_primary_project_to_activate()')
    op.execute('DROP TRIGGER IF EXISTS trg_demote_other_primary_projects ON user_projects')
    op.execute('DROP FUNCTION IF EXISTS demote_other_primary_projects()')
