"""drop the triggers that make active users keep a primary project

Revision ID: b2f6d8e4a9c1
Revises: e5b1d9a7c3f4
Create Date: 2026-11-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2f6d8e4a9c1'
down_revision: Union[str, Sequence[str], None] = 'e5b1d9a7c3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# See userapp.api.util.user_visible_db_message
MARKER = 'user-visible: '


def upgrade() -> None:
    # An active user may now have no primary project. This removes rules 2 and 3 from
    # e4b9a2c6d1f7; rule 1 (one primary project per user) is kept.
    op.execute('DROP TRIGGER IF EXISTS trg_keep_primary_project_on_delete ON user_projects')
    op.execute('DROP TRIGGER IF EXISTS trg_keep_primary_project_on_unset ON user_projects')
    op.execute('DROP FUNCTION IF EXISTS keep_primary_project_for_active_user()')
    op.execute('DROP TRIGGER IF EXISTS trg_require_primary_project_to_activate ON users')
    op.execute('DROP FUNCTION IF EXISTS require_primary_project_to_activate()')


def downgrade() -> None:
    # Recreates the triggers exactly as e4b9a2c6d1f7 defined them
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
