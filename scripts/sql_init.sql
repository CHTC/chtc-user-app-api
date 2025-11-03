-- GROUPS TABLE MODIFICATIONS --

-- Add CHECK constraint for groups
ALTER TABLE groups
    ADD CONSTRAINT chk_unix_gid_range CHECK (unix_gid BETWEEN 40000 AND 60000),
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

-- General Notes --
-- Make sure GID is unique and we have removed the gids in uid range --

-- PROJECTS TABLE MODIFICATIONS --

-- Trigger function to ensure users added to a note are associated with the project
CREATE OR REPLACE FUNCTION check_user_in_project_for_note()
RETURNS TRIGGER AS $$
BEGIN
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
