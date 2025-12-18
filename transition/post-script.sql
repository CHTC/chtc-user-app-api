-- GROUPS TABLE MODIFICATIONS --

UPDATE groups
    SET point_of_contact = NULL
    WHERE point_of_contact = '';

-- Add CHECK constraint for groups
ALTER TABLE groups
    ADD CONSTRAINT chk_unix_gid_range CHECK (unix_gid BETWEEN 40000 AND 60000) NOT VALID,
    ADD CONSTRAINT chk_group_name_valid CHECK (name ~ '^[a-zA-Z0-9_-]{1,32}$');

-- Add trigger function to enforce cross-table uniqueness of unix_gid/unix_uid
CREATE OR REPLACE FUNCTION check_unix_gid_uid_unique()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM users WHERE unix_uid = NEW.unix_gid
    ) THEN
        RAISE EXCEPTION 'unix_gid in groups must be unique across users.unix_uid';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_unix_gid_uid_unique
BEFORE INSERT OR UPDATE ON groups
FOR EACH ROW EXECUTE FUNCTION check_unix_gid_uid_unique();

-- Function to assign lowest unused unix_gid
CREATE OR REPLACE FUNCTION assign_lowest_unix_gid()
RETURNS TRIGGER AS $$
DECLARE
    candidate INTEGER;
BEGIN
    IF NEW.unix_gid IS NULL THEN
        SELECT gid INTO candidate FROM (
            SELECT generate_series(40000, 60000) AS gid
            EXCEPT
            SELECT unix_gid FROM groups
            EXCEPT
            SELECT unix_uid FROM users
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
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_assign_lowest_unix_gid
BEFORE INSERT ON groups
FOR EACH ROW EXECUTE FUNCTION assign_lowest_unix_gid();

-- USERS TABLE MODIFICATIONS --

-- Add constraint to make sure netid is unique if not null --
ALTER TABLE users
    ADD CONSTRAINT uniq_netid_unique_if_not_null
UNIQUE (netid)
DEFERRABLE INITIALLY DEFERRED;

-- Add constraint: username or netid must not both be null
ALTER TABLE users
    ADD CONSTRAINT chk_username_or_netid_not_null
    CHECK (username IS NOT NULL OR netid IS NOT NULL);

-- Add constraint: if username is not null, password must not be null
ALTER TABLE users
    ADD CONSTRAINT chk_password_if_username_not_null
    CHECK (username IS NULL OR password IS NOT NULL);

-- Add constraint: username must not contain ':' or ';'
ALTER TABLE users
    ADD CONSTRAINT chk_name_no_colon_semicolon
    CHECK (name !~ ':' AND name !~ ';');



-- Remove the invalid generated column if present
ALTER TABLE users DROP COLUMN IF EXISTS is_pi;

-- PROJECTS TABLE MODIFICATIONS --

-- Add constraint: staff1 and staff2 must not be equal when both are non-null
ALTER TABLE projects
    ADD CONSTRAINT chk_staff1_not_equal_staff2
    CHECK (staff1 IS NULL OR staff2 IS NULL OR staff1 <> staff2);

-- General Notes --
-- Make sure GID is unique and we have removed the gids in uid range --

-- PROJECTS TABLE MODIFICATIONS --

-- Update ints to enums --

-- 1. Create the enums
CREATE TYPE role_enum AS ENUM ('MEMBER', 'PI');
CREATE TYPE position_enum AS ENUM ('SELECT', 'FACULTY', 'STAFF', 'POSTDOC', 'GRAD_STUDENT', 'UNDERGRADUATE', 'OTHER');

-- 2. Convert user_projects.role from int to role_enum
ALTER TABLE user_projects
    ALTER COLUMN role DROP DEFAULT,
    ALTER COLUMN role TYPE role_enum USING (
        CASE role
            WHEN 1 THEN 'MEMBER'
            WHEN 2 THEN 'PI'
        END::role_enum
    );

-- 3. Convert users.position from int to position_enum
ALTER TABLE users
    ALTER COLUMN position DROP DEFAULT,
    ALTER COLUMN position TYPE position_enum USING (
        CASE position
            WHEN 1 THEN 'SELECT'
            WHEN 2 THEN 'FACULTY'
            WHEN 3 THEN 'STAFF'
            WHEN 4 THEN 'POSTDOC'
            WHEN 5 THEN 'GRAD_STUDENT'
            WHEN 6 THEN 'UNDERGRADUATE'
            WHEN 7 THEN 'OTHER'
        END::position_enum
    );

-- Trigger function to ensure users added to a note are associated with the project
CREATE OR REPLACE FUNCTION check_user_in_project_for_note()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.user_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM user_projects WHERE user_id = NEW.user_id AND project_id = NEW.project_id
    ) THEN
        RAISE EXCEPTION 'User % is not associated with project % for this note', NEW.user_id, NEW.project_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_user_in_project_for_note
BEFORE INSERT OR UPDATE ON user_notes
FOR EACH ROW EXECUTE FUNCTION check_user_in_project_for_note();


-- Create a view with just PIs and their projects
DROP TABLE IF EXISTS pi_projects;
CREATE OR REPLACE VIEW pi_projects AS
SELECT
    u.id AS user_id,
    u.username,
    u.name,
    u.email1,
    u.netid,
    u.phone1,
    p.id AS project_id,
    p.name AS project_name
FROM users u
JOIN user_projects up ON up.user_id = u.id
JOIN projects p ON p.id = up.project_id
WHERE up.role = 'PI';


-- USER PROJECTS VIEW --

CREATE OR REPLACE VIEW joined_projects AS
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
    JOIN projects p ON up.project_id = p.id;

-- USER SUBMIT VIEW --

CREATE OR REPLACE VIEW user_submit_nodes AS
    SELECT DISTINCT
        us.user_id,
        us.submit_node_id,
        us.disk_quota,
        us.hpc_joblimit,
        us.hpc_corelimit,
        us.hpc_diskquota,
        us.hpc_fairshare,
        us.hpc_inodequota,
        s.name as submit_node_name
    FROM user_submits us
    JOIN submit_nodes s ON us.submit_node_id = s.id;

-- Clean up tables --

-- USERS TABLE --

UPDATE users
    SET email1 = 'default@email.org'
    WHERE email1 = '' OR email1 IS NULL;

UPDATE users
    SET name = 'Unknown Name'
    WHERE name = '' OR name IS NULL;

UPDATE users
    SET email2 = NULL
    WHERE email2 = '';

UPDATE users
    SET netid = NULL
    WHERE netid = '';

UPDATE users
    SET phone1 = NULL
    WHERE phone1 = '';

UPDATE users
    SET phone2 = NULL
    WHERE phone2 = '';

-- PROJECTS TABLE --

UPDATE projects
    SET staff1 = NULL
    WHERE staff1 = '';

UPDATE projects
    SET staff2 = NULL
    WHERE staff2 = '';

UPDATE projects
    SET url = NULL
    WHERE url = '';

-- NOTES TABLE --

UPDATE notes
    SET ticket = NULL
    WHERE ticket = '';

-- GROUPS TABLE --
