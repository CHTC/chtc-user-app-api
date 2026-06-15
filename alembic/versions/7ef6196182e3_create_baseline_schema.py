"""Create baseline schema

Establishes the pre-migration schema that existed before any recorded Alembic
migrations ran. The original database was converted from SQLite; this migration
captures that initial state so a fresh database can be bootstrapped from empty
with a single ``alembic upgrade head``.

Written as raw SQL (``op.execute``) for full control over enum and view
creation, matching the style of the view/DDL blocks in the later migrations.

Integer primary keys use SERIAL so they get an autoincrement sequence
(``nextval('<table>_id_seq')``) — exactly what an integer-PK ORM column emits
on Postgres. Without this, inserts that omit ``id`` fail a NOT NULL violation.

Key characteristics of the initial state captured here:
  - groups.point_of_contact, notes.author, projects.staff1/staff2 are plain
    text columns (not yet integer FKs — f3a9c2e81d04 converts them).
  - users contains auth_netid, auth_username, username, password columns
    (a674e0eb726a and b8ae04f033ae remove them; 47f8adc9859b re-adds username
    as a unix username field).
  - user_groups and user_projects have no managed_by/created_at/updated_at
    (f2ec55925c4c adds them).
  - forms/user_form tables do not exist yet (f91affa16676 creates them).
  - user_submit_nodes is the only view never created by any migration;
    it is created here and is never touched again.

Revision ID: 7ef6196182e3
Revises:
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op


revision: str = '7ef6196182e3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums ---------------------------------------------------------------
    # position_enum and role_enum predate all recorded migrations. Later
    # migrations that reference them (f91affa16676, etc.) create with
    # checkfirst=True, so they skip silently once these exist.
    op.execute("""
        CREATE TYPE position_enum AS ENUM (
            'SELECT', 'FACULTY', 'STAFF', 'POSTDOC',
            'GRAD_STUDENT', 'UNDERGRADUATE', 'OTHER'
        )
    """)
    op.execute("CREATE TYPE role_enum AS ENUM ('MEMBER', 'PI')")

    # --- Tables --------------------------------------------------------------
    # submit_nodes has no FKs so it can come first.
    op.execute("""
        CREATE TABLE submit_nodes (
            id   SERIAL NOT NULL,
            name VARCHAR(60),
            PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX ix_submit_nodes_id ON submit_nodes (id)")

    # users is the central FK target for most other tables.
    op.execute("""
        CREATE TABLE users (
            id                 SERIAL NOT NULL,
            name               VARCHAR(255) NOT NULL,
            email1             VARCHAR(255) NOT NULL,        -- made nullable by cf94844cecc1
            email2             VARCHAR(255),
            netid              VARCHAR(255),
            username           VARCHAR(255),                 -- dropped by b8ae04f033ae, re-added by 47f8adc9859b
            password           VARCHAR(255),                 -- dropped by b8ae04f033ae
            netid_exp_datetime TIMESTAMP,
            phone1             VARCHAR(255),
            phone2             VARCHAR(255),
            is_admin           BOOLEAN,                      -- ORM default=False is client-side
            date               TIMESTAMP DEFAULT now() NOT NULL,
            unix_uid           INTEGER,
            position           position_enum,
            auth_netid         BOOLEAN DEFAULT false NOT NULL,  -- dropped by a674e0eb726a
            auth_username      BOOLEAN DEFAULT false NOT NULL,  -- dropped by a674e0eb726a
            PRIMARY KEY (id),
            CONSTRAINT users_username_key UNIQUE (username),
            -- netid unique (nulls distinct, so multiple NULLs allowed); matches the ORM's
            -- UniqueConstraint('netid', name='uniq_netid_unique_if_not_null').
            CONSTRAINT uniq_netid_unique_if_not_null UNIQUE (netid)
        )
    """)
    op.execute("CREATE INDEX ix_users_id ON users (id)")

    # groups: point_of_contact is a plain text column here; f3a9c2e81d04
    # converts it to an integer FK referencing users.id.
    op.execute("""
        CREATE TABLE groups (
            id               SERIAL NOT NULL,
            name             VARCHAR(32) NOT NULL,
            point_of_contact VARCHAR(50),                 -- becomes int FK in f3a9c2e81d04
            unix_gid         INTEGER,
            has_groupdir     BOOLEAN NOT NULL,            -- ORM default=True is client-side
            PRIMARY KEY (id),
            CONSTRAINT groups_name_key UNIQUE (name),
            CONSTRAINT groups_unix_gid_key UNIQUE (unix_gid)  -- ORM Column(unique=True)
        )
    """)
    op.execute("CREATE INDEX ix_groups_id ON groups (id)")

    # notes: author is a plain text column; f3a9c2e81d04 converts it.
    op.execute("""
        CREATE TABLE notes (
            id     SERIAL NOT NULL,
            ticket VARCHAR(9),
            note   TEXT NOT NULL,
            author VARCHAR(255),                          -- becomes int FK in f3a9c2e81d04
            date   TIMESTAMP DEFAULT now() NOT NULL,
            PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX ix_notes_id ON notes (id)")

    # projects: staff1/staff2 are plain text; f3a9c2e81d04 converts them.
    op.execute("""
        CREATE TABLE projects (
            id               SERIAL NOT NULL,
            name             VARCHAR(255) NOT NULL,
            pi               INTEGER,
            staff1           VARCHAR(255),                -- becomes int FK in f3a9c2e81d04
            staff2           VARCHAR(255),                -- becomes int FK in f3a9c2e81d04
            status           VARCHAR(255),
            access           VARCHAR(255),
            accounting_group VARCHAR(255) NOT NULL,
            url              VARCHAR(255),
            date             TIMESTAMP DEFAULT now() NOT NULL,
            ticket           INTEGER,
            last_contact     TIMESTAMP,
            PRIMARY KEY (id),
            CONSTRAINT projects_name_key UNIQUE (name)
        )
    """)
    op.execute("CREATE INDEX ix_projects_id ON projects (id)")

    op.execute("""
        CREATE TABLE tokens (
            id          SERIAL NOT NULL,
            created_by  INTEGER,
            token       VARCHAR(255) NOT NULL,
            description VARCHAR(255),
            created_at  TIMESTAMP DEFAULT now() NOT NULL,
            expires_at  TIMESTAMP,
            PRIMARY KEY (id),
            CONSTRAINT tokens_token_key UNIQUE (token),
            FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_tokens_id ON tokens (id)")

    op.execute("""
        CREATE TABLE access (
            id         SERIAL NOT NULL,
            user_id    INTEGER,
            token_id   INTEGER,
            route      VARCHAR(255) NOT NULL,
            payload    VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT now() NOT NULL,
            expires_at TIMESTAMP,
            PRIMARY KEY (id),
            FOREIGN KEY (user_id)  REFERENCES users (id),
            FOREIGN KEY (token_id) REFERENCES tokens (id)
        )
    """)
    op.execute("CREATE INDEX ix_access_id ON access (id)")

    # user_groups has no managed_by/created_at/updated_at yet (added by f2ec55925c4c).
    op.execute("""
        CREATE TABLE user_groups (
            id       SERIAL NOT NULL,
            group_id INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT user_groups_distinct UNIQUE (user_id, group_id),
            FOREIGN KEY (group_id) REFERENCES groups (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id)  REFERENCES users (id)  ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_user_groups_id ON user_groups (id)")

    op.execute("""
        CREATE TABLE user_notes (
            id         SERIAL NOT NULL,
            project_id INTEGER NOT NULL,
            note_id    INTEGER NOT NULL,
            user_id    INTEGER,
            PRIMARY KEY (id),
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
            FOREIGN KEY (note_id)    REFERENCES notes (id)    ON DELETE CASCADE,
            FOREIGN KEY (user_id)    REFERENCES users (id)    ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_user_notes_id ON user_notes (id)")

    # user_projects has no managed_by/created_at/updated_at yet (added by f2ec55925c4c).
    op.execute("""
        CREATE TABLE user_projects (
            id         SERIAL NOT NULL,
            project_id INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            role       role_enum,
            is_primary BOOLEAN NOT NULL,                -- ORM default=False is client-side
            PRIMARY KEY (id),
            CONSTRAINT user_projects_distinct UNIQUE (user_id, project_id),
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id)    REFERENCES users (id)    ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_user_projects_id ON user_projects (id)")

    op.execute("""
        CREATE TABLE user_submits (
            id             SERIAL NOT NULL,
            user_id        INTEGER NOT NULL,
            submit_node_id INTEGER NOT NULL,
            for_auth_netid BOOLEAN,
            disk_quota     INTEGER,
            hpc_diskquota  INTEGER NOT NULL,            -- ORM defaults below are client-side
            hpc_inodequota INTEGER NOT NULL,
            hpc_joblimit   INTEGER NOT NULL,
            hpc_corelimit  INTEGER NOT NULL,
            hpc_fairshare  INTEGER NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT user_submits_distinct UNIQUE (user_id, submit_node_id, for_auth_netid),
            FOREIGN KEY (user_id)        REFERENCES users (id)        ON DELETE CASCADE,
            FOREIGN KEY (submit_node_id) REFERENCES submit_nodes (id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX ix_user_submits_id ON user_submits (id)")

    # --- Views ---------------------------------------------------------------
    # user_submit_nodes is the only view never created by any subsequent
    # migration. All other views (joined_projects, pi_projects, group_users,
    # etc.) are first created—and owned—by their respective upgrade scripts
    # using DROP VIEW IF EXISTS before CREATE, so they don't need to exist here.
    #
    # The original body predates Alembic and is in no migration; prod has since
    # dropped this view (026216ef4d8a), so no ground-truth definition survives.
    # This body is kept byte-for-byte identical to 026216ef4d8a's downgrade
    # reconstruction so the create/recreate paths agree.
    op.execute("""
        CREATE VIEW user_submit_nodes AS
        SELECT
            us.user_id,
            us.submit_node_id,
            sn.name AS submit_node_name,
            us.disk_quota,
            us.hpc_diskquota,
            us.hpc_inodequota,
            us.hpc_joblimit,
            us.hpc_corelimit,
            us.hpc_fairshare
        FROM user_submits us
        JOIN submit_nodes sn ON sn.id = us.submit_node_id
    """)

    # --- Functions / triggers ------------------------------------------------
    # These predate Alembic (original DB) and are in no migration. Bodies are
    # copied verbatim from prod (pg_get_functiondef). They enforce POSIX uid/gid
    # invariants and note integrity:
    #   * assign_lowest_unix_gid: BEFORE INSERT on groups — if unix_gid is NULL,
    #     assign the lowest free value in [40000, 60000] not already used by a
    #     group gid or a user uid.
    #   * check_unix_gid_uid_unique: BEFORE INSERT/UPDATE on groups — reject a
    #     gid that collides with any users.unix_uid (one shared number space).
    #   * check_user_in_project_for_note: BEFORE INSERT/UPDATE on user_notes —
    #     the note's user must belong to the note's project.
    # On a groups INSERT, BEFORE triggers fire alphabetically, so assign_ runs
    # before check_ — allocate, then validate.
    op.execute("""
        CREATE OR REPLACE FUNCTION assign_lowest_unix_gid() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            candidate INTEGER;
        BEGIN
            IF NEW.unix_gid IS NULL THEN
                SELECT gid INTO candidate FROM (
                    SELECT generate_series(40000, 60000) AS gid
                    EXCEPT SELECT unix_gid FROM groups
                    EXCEPT SELECT unix_uid FROM users
                    ORDER BY gid
                    LIMIT 1
                ) AS available;
                IF candidate IS NULL THEN
                    RAISE EXCEPTION 'No available unix_gid in range 40000-60000';
                END IF;
                NEW.unix_gid := candidate;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION check_unix_gid_uid_unique() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM users WHERE unix_uid = NEW.unix_gid
            ) THEN
                RAISE EXCEPTION 'unix_gid in groups must be unique across users.unix_uid';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
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

    op.execute("""
        CREATE TRIGGER trg_assign_lowest_unix_gid
        BEFORE INSERT ON groups
        FOR EACH ROW EXECUTE FUNCTION assign_lowest_unix_gid()
    """)
    op.execute("""
        CREATE TRIGGER trg_check_unix_gid_uid_unique
        BEFORE INSERT OR UPDATE ON groups
        FOR EACH ROW EXECUTE FUNCTION check_unix_gid_uid_unique()
    """)
    op.execute("""
        CREATE TRIGGER trg_check_user_in_project_for_note
        BEFORE INSERT OR UPDATE ON user_notes
        FOR EACH ROW EXECUTE FUNCTION check_user_in_project_for_note()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_check_user_in_project_for_note ON user_notes")
    op.execute("DROP TRIGGER IF EXISTS trg_check_unix_gid_uid_unique ON groups")
    op.execute("DROP TRIGGER IF EXISTS trg_assign_lowest_unix_gid ON groups")
    op.execute("DROP FUNCTION IF EXISTS check_user_in_project_for_note()")
    op.execute("DROP FUNCTION IF EXISTS check_unix_gid_uid_unique()")
    op.execute("DROP FUNCTION IF EXISTS assign_lowest_unix_gid()")

    op.execute("DROP VIEW IF EXISTS user_submit_nodes")

    op.execute("DROP TABLE IF EXISTS user_submits")
    op.execute("DROP TABLE IF EXISTS user_projects")
    op.execute("DROP TABLE IF EXISTS user_notes")
    op.execute("DROP TABLE IF EXISTS user_groups")
    op.execute("DROP TABLE IF EXISTS access")
    op.execute("DROP TABLE IF EXISTS tokens")
    op.execute("DROP TABLE IF EXISTS projects")
    op.execute("DROP TABLE IF EXISTS notes")
    op.execute("DROP TABLE IF EXISTS groups")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS submit_nodes")

    op.execute("DROP TYPE IF EXISTS role_enum")
    op.execute("DROP TYPE IF EXISTS position_enum")
