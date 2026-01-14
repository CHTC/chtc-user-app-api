-- Indexes --

CREATE INDEX CONCURRENTLY idx_user_notes_userid_projectid_noteid
  ON user_notes (user_id, project_id, note_id);

-- Also a specialized index for fetching the latest note by user quickly:
CREATE INDEX CONCURRENTLY idx_user_notes_userid_noteid_desc
  ON user_notes (user_id, note_id DESC);

CREATE INDEX CONCURRENTLY idx_user_submits_userid_submitnodeid_incl
  ON user_submits (user_id, submit_node_id)
  INCLUDE (disk_quota, hpc_diskquota, hpc_inodequota, hpc_joblimit, hpc_corelimit, hpc_fairshare);
