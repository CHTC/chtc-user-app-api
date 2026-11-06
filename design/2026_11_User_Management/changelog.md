# Highlights

- UI pages are deferred to a second round that starts only after column/field sign-off; this round is API + DB ([details](#defer-ui-work-to-a-second-round)) [ui, scope, omission, hil]
- No `login_access` table is created; `submit_nodes.group_id` stays as the login-access mechanism ([details](#keep-submit_nodes-instead-of-adding-login_access)) [schema, login-access, deviation, hil]
- The `/managed/*` sync endpoints are kept and now sync the direct user members of a group ([details](#keep-managed-sync-endpoints-on-group_members)) [api, managed-sync, schema, addition, hil]
- The existing `groups` table is altered in place rather than replaced, so ids, names and unix_gids survive ([details](#alter-groups-in-place)) [schema, migration, clarification, hil]
- Foreign-key columns use the repo's `_id` suffix: `owner_group_id`, `pi_group_id`, `project_group_id` ([details](#foreign-key-column-naming)) [schema, naming, clarification, autonomous]
- The design names the project member group both `project_group` and `member_group`; `project_group_id` is used ([details](#project_group-vs-member_group)) [schema, design-issue, autonomous]
- Effective membership is materialized one row per (group, user, path) and fully recomputed under an advisory lock on every membership write ([details](#materialize-effective-membership-per-path)) [schema, membership, performance, addition, autonomous]
- `audit_log.group_id` is nullable and non-group targets (projects, submit nodes, users) are identified in `details` ([details](#audit-log-targets-outside-groups)) [schema, audit, clarification, hil]
- Audit log append-only-ness is enforced by the application (no update/delete routes), not by a database trigger ([details](#append-only-audit-log-enforced-in-app)) [audit, clarification, autonomous]
- The design contradicts itself on who edits a group description; owners and staff can ([details](#group-description-edit-permission)) [permissions, groups, design-issue, hil]
- Membership routes move from `/groups/{id}/users` to a `/groups/{id}/members` family that handles user and group members ([details](#replace-groupsidusers-routes-with-members-routes)) [api, groups, clarification, hil]
- Auto-created administrator groups are named from the base group with `_owners`/`_managers` (projects: `_pi`/`_managers`), truncated to 32 chars and de-duplicated with a numeric suffix ([details](#naming-of-auto-created-administrator-groups)) [groups, naming, addition, autonomous]
- The data migration maps every existing project and membership automatically; the "by hand" mappings the design mentions are not done ([details](#automatic-data-migration)) [migration, clarification, hil]
- A `/unix_groups` export endpoint lists each unix group with its effective member usernames ([details](#unix-groups-export-endpoint)) [api, unix-groups, addition, autonomous]
- Non-staff users listing groups only see groups they can administer ([details](#non-staff-group-listing)) [api, permissions, clarification, autonomous]
- `RoleEnum` and `primary_project_role` are removed; PIs are managed through staff-only `/projects/{id}/pis` routes ([details](#remove-roleenum-and-add-project-pi-routes)) [api, projects, clarification, autonomous]
- The baseline trigger that auto-assigns a `unix_gid` to every new group is dropped, so a null `unix_gid` means "no unix group" and generated pi/managers/owners groups are not unix groups ([details](#drop-automatic-unix_gid-allocation)) [schema, unix-groups, deviation, hil]
- `check_user_in_project_for_note` is rewritten to test effective membership of the project group instead of reading the dropped `user_projects` table ([details](#note-trigger-reads-group-membership)) [schema, migration, notes, addition, autonomous]
- Group deletion records cleared owner references as `owner_group_changed`, not `metadata_changed` ([details](#owner-references-cleared-by-deletion-use-owner_group_changed)) [audit, groups, clarification, autonomous]
- `GET /groups` answers an anonymous caller with 403, as it did when the router was admin-only, not 401 ([details](#get-groups-keeps-403-for-anonymous-callers)) [api, permissions, clarification, autonomous]
- `joined_projects` rows carry `direct`, and for users with access only through another group `created_at` and `updated_at` are NULL, so those schema fields are optional ([details](#joined_projects-membership-columns-are-nullable)) [schema, views, clarification, autonomous]
- Generated group names get their `_2`, `_3` suffix after the role suffix, and the migration and the service share one rule ([details](#numeric-suffix-goes-after-the-role-suffix)) [groups, naming, clarification, autonomous]
- `create_project_groups` also points the project at the groups it creates ([details](#create_project_groups-sets-the-project-columns)) [projects, services, clarification, autonomous]
- The migration puts every `user_projects` row (PIs included) in the project group and `projects.pi` in the pi group only when it names an existing user ([details](#migration-mapping-details)) [migration, clarification, autonomous]
- Parts of the wave 2 work were done early where wave 1 code would not import or run without them ([details](#wave-2-behaviour-pulled-forward)) [api, scope, addition, autonomous]
- `AuditLog` has Get and Post placeholder schemas but no Patch, because the log is append-only ([details](#auditlog-has-no-patch-schema)) [audit, schema, omission, autonomous]
- `GET /groups/{id}/member_of` paths run from the containing group down to the group, matching effective-membership paths ([details](#member_of-path-orientation)) [api, groups, clarification, autonomous]
- Design inconsistency: the design says a null `unix_gid` means no unix group, but the existing database assigns one on insert ([details](#design-inconsistency-unix_gid-null-vs-automatic-allocation)) [schema, design-issue, autonomous]
- `GET /users/{id}/audit_log` and `GET /groups/{id}/audit_log` answer 404 for an unknown user or group, and deleted groups stay readable ([details](#per-group-and-per-user-log-routes-404-on-unknown-ids)) [api, audit, clarification, autonomous]
- `AuditLogGet` gains nested `actor`, `member_user` and `member_group` next to the flat ids, through read-only relationships on `AuditLog` ([details](#auditlogget-nests-actor-member-user-and-member-group)) [audit, schema, addition, autonomous]
- `GET /groups/{id}/access` rows also carry the referenced `group_id`, and a project reached as both pi group and project group appears as two rows ([details](#access-summary-shape)) [api, groups, clarification, autonomous]
- `/unix_groups` skips members without a username ([details](#unix-group-member-rules)) [api, unix-groups, clarification, autonomous]
- `PUT /submit_nodes/{id}` logs only fields whose value changed and answers an unknown id with 404 ([details](#submit-node-audit)) [audit, submit-nodes, clarification, autonomous]
- The query parser now parses ISO 8601 timestamps and a malformed filter is a 400 instead of a 500, on every list route ([details](#query-parser-timestamps-and-400-on-bad-filters)) [api, query-parser, error-handling, addition, autonomous]
- `POST /projects` with only one of `pi_group_id` / `project_group_id` creates just the missing side; a missing project group also gets a managers group, a missing pi group is created alone ([details](#post-projects-with-one-group-supplied)) [projects, groups, clarification, autonomous]
- Project viewing (`GET /projects/{id}`, `/users`, `/pis`) is allowed to staff, pi-group effective members and project-group administrators through a dependency local to `projects.py` ([details](#project-view-rule)) [permissions, projects, addition, autonomous]
- A PUT on a project by a non-staff PI that names `pi_group_id`, `project_group_id`, `accounting_group`, `staff1` or `staff2` is refused even when the value is unchanged ([details](#pi-put-field-restriction)) [permissions, projects, clarification, autonomous]
- `DELETE /projects/{id}/users/{uid}` and `/pis/{uid}` answer 404 and name the groups through which a non-direct member still has access ([details](#removal-404-names-the-access-path)) [api, projects, clarification, autonomous]
- Every change of `users.primary_project_id` (user create, `PATCH /users`, form approval, managed sync) is audited as `metadata_changed` with entity `user` ([details](#primary-project-changes-are-audited)) [audit, users, addition, autonomous]
- `PATCH /users/{id}` accepts `primary_project_id` from staff (null clears it) and ignores it from a user editing themselves ([details](#patch-users-primary_project_id)) [api, users, clarification, autonomous]
- A managed project sync clears the primary project of a listed user whose entry says `is_primary: false` when that project is currently their primary ([details](#managed-sync-with-is-primary-false-clears-the-primary)) [managed-sync, users, clarification, hil]
- `PUT /managed/{m}/groups/{id}/users` returns the group's direct `group_members_view` rows, and a project sync on a project without a project group is 404 ([details](#managed-sync-responses)) [managed-sync, api, clarification, autonomous]
- `PATCH /users/{id}/projects/{id}` and `PATCH /users/{id}/groups/{id}` tests were deleted with `test_user_membership_patch.py`; the group route `PATCH /groups/{id}/members/users/{id}` was removed later with per-membership `managed_by` ([details](#membership-patch-tests-removed)) [tests, omission, autonomous]
- Test helpers `audit_rows`, `db_rows`, `plain_user_factory` and `client_as` live in `conftest.py` and audit assertions only look at entries written since the test began ([details](#test-helpers-and-audit-assertions)) [tests, addition, autonomous]
- Non-staff viewers who can load a group page get `canAdminister=true` on the members panel, because the API only lets staff and owners load it ([details](#canadminister-for-non-staff)) [ui, permissions, clarification, autonomous]
- The members table links to `/users/edit` only for staff, since user pages are not open to group owners ([details](#user-links-in-members-table-are-staff-only)) [ui, permissions, clarification, autonomous]
- The groups layout no longer has an "Add Group" button for everyone; "Create Group" and "Show deleted" render in the list view for staff only ([details](#create-and-show-deleted-controls-live-in-the-list-view)) [ui, groups, clarification, autonomous]
- Owner and group cells in the lists show "Group {id}" links because list rows carry ids only; no extra name lookups ([details](#group-cells-show-ids-not-names)) [ui, lists, omission, autonomous]
- Audit log Group column shows "Group {id}" since `AuditLogGet` nests actor, member user and member group but not the group ([details](#audit-log-group-column-shows-ids)) [ui, audit, omission, autonomous]
- Audit log filters apply on a Search button, not per keystroke ([details](#audit-filters-apply-on-search)) [ui, audit, addition, autonomous]
- `GroupAutocomplete` gained an optional `label` prop; new `src/utils/fetchList.ts` holds shared fetch helpers ([details](#shared-helpers-and-label-prop)) [ui, addition, autonomous]
- A deleted group hides the Members panel; it still shows Member of, Access and History ([details](#deleted-group-page)) [ui, groups, clarification, autonomous]
- No alert key was added; `ADD_MEMBER_SUCCESS` and `REMOVE_MEMBER_SUCCESS` are used for both user and group members ([details](#alerts)) [ui, clarification, autonomous]
- ProjectForm's PI/Project group pickers are local GenericAutocompletes, non-staff get the staff-only inputs disabled and left out of the PUT body, and the project page's group chips carry static labels rather than fetched names ([details](#group-pickers-on-projectform)) [ui, projects, permissions, clarification, autonomous]
- The project members table merges the group members route with the project users route by user id; ProjectUserTable is replaced by ProjectMembersTable and ProjectPiTable, and a 403 on the project page shows a message instead of crashing ([details](#members-and-pi-tables)) [ui, projects, clarification, autonomous]
- UserForm's primary project is an optional staff-only field; ProjectAutocomplete gained label/helperText props for it ([details](#primary-project-on-userform)) [ui, users, clarification, autonomous]
- A user's project row shows "via group" instead of Remove when access is indirect, the groups table uses MembershipPaths, and the email PI filter sends is_pi ([details](#user-tables)) [ui, users, clarification, autonomous]
- Every members table lists member groups as well as users and adds either kind; the project routes gained `/groups` and `/pi_groups` for the project group's and pi group's member groups ([details](#member-groups-on-every-members-table)) [api, ui, projects, membership, addition, hil]
- Expiry (`expires_at` on groups and projects) and data access (`backing_stores`, `data_access`, their routes and pages) are left out of this update, and project deletion is a hard delete again ([details](#expiry-and-data-access-are-left-out-of-this-update)) [schema, api, ui, data-access, projects, omission, hil]
- `managed_by` is a column of `groups`, not of `group_members`: a managed sync claims the group and replaces all of its direct user members ([details](#managed_by-moves-from-memberships-to-groups)) [schema, api, managed-sync, migration, ui, deviation, hil]
- Review fixes: submit nodes must point at a live group, primary-project audit rows name the user as member, `PUT /groups/{id}` refuses `managed_by: null`, and the PI table reads member groups through `/projects/{id}/pi_groups` ([details](#review-fixes-after-the-managed_by-move)) [api, ui, audit, submit-nodes, addition, autonomous]

# Detailed

## Defer UI work to a second round

**Design says:** The "UI details" section specifies the project page, basic access management pages and group page.

**What was done:** This round implements only the data model, migration, services and API. UI work starts after the API lands and the user signs off on proposed columns and fields.

**Decided by:** HIL (user). Asked "How much of the design should this round cover?"; the user chose "API + DB now, UI after sign-off".

**Why:** The UI depends on the API shape, and the user's standing guidance is to get sign-off on UI columns/fields before building them.

**Impact:** The "UI details" section is unimplemented until the second round. The API is built so each page described there has the endpoints it needs.

**Tags:** [ui, scope, omission, hil]

## Keep submit_nodes instead of adding login_access

**Design says:** "Login access" defines `login_access(login_node, group)` with `(login_node, group)` unique.

**What was done:** No `login_nodes` or `login_access` tables are created. `submit_nodes` keeps its `group_id`; the effective members of that group are the users who can log in. Group deletion sets `submit_nodes.group_id` to null, which is what the design asks for `login_access.group`.

**Decided by:** HIL (user). Asked how `login_node`/`login_access` should map onto `submit_nodes`; the user replied "I never intended a login_access table. Please keep submit_node tables as is."

**Why:** The user says the login-access section of the design was not intended as a new table.

**Impact:** The design's "Login access" section should be read as describing `submit_nodes`. One submit node maps to one group, so a node cannot grant access to several groups without a wrapper group.

**Tags:** [schema, login-access, deviation, hil]

## Keep managed sync endpoints on group_members

**Design says:** Silent on the `/managed/manifest` and `/managed/morgridge-ad` sync endpoints, which today replace `user_projects`/`user_groups` rows tagged with `managed_by`.

**What was done:** `PUT /managed/{manager}/groups/{id}/users` replaces the direct user members of that group. `PUT /managed/{manager}/projects/{id}/users` does the same for the project's `project_group`; an entry with `is_primary: true` also sets `users.primary_project_id`. Which system owns a group's membership is `groups.managed_by` (originally a column of `group_members`; see "managed_by moves from memberships to groups").

**Decided by:** HIL (user). Asked what should happen to the managed endpoints; the user chose "Keep them, syncing group members".

**Why:** External systems (manifest, Morgridge AD) already call these endpoints.

**Impact:** Managed rows are direct memberships like any other; effective membership and audit logging apply to them.

**Tags:** [api, managed-sync, schema, addition, hil]

## Alter groups in place

**Design says:** "Changes to existing tables" lists `Group` under both "Tables replaced ... Removed" and "Tables Created".

**What was done:** The migration alters `groups` in place: adds `owner_group_id`, `description`, `managed_by`, `deleted_at`, `created_at`, `updated_at`; drops `point_of_contact` and `has_groupdir`. Group ids, names and unix_gids are unchanged.

**Decided by:** HIL (user). Asked whether to alter in place or re-key; the user chose "Alter in place".

**Why:** `submit_nodes.group_id` and external consumers reference existing ids and unix_gids.

**Impact:** `point_of_contact` and `has_groupdir` disappear from the API. Anything that used `has_groupdir` to mean "has a group directory" should use a `data_access` entry instead.

**Tags:** [schema, migration, clarification, hil]

## Foreign-key column naming

**Design says:** Uses `owner_group`, `pi_group`, `project_group` and `group` as column names.

**What was done:** Columns are `groups.owner_group_id`, `projects.pi_group_id`, `projects.project_group_id`. API fields use the same names.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Every existing FK column in the schema ends in `_id` (`college_and_department_id`, `group_id`, `fos_id`).

**Impact:** Naming only. Reviewers reading the design should map `owner_group` → `owner_group_id`, etc.

**Tags:** [schema, naming, clarification, autonomous]

## project_group vs member_group

**Design says:** "Project" defines `project_group: group.id`; "Changes to existing tables" says "Project: pi turns into pi_group, add member_group".

**What was done:** The column is `project_group_id`. There is no `member_group`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** `project_group` is the name used throughout the Project section and its diagram; `member_group` appears once.

**Impact:** None beyond naming. The design doc should be corrected.

**Tags:** [schema, design-issue, autonomous]

## Materialize effective membership per path

**Design says:** "The application stores effective membership in a materialized table. Every membership change recomputes it in the same transaction." The UI section wants a column showing `direct` or the group path(s) that grant access.

**What was done:** `group_effective_members(group_id, user_id, path integer[])` holds one row per distinct path from a group to a user; direct membership is `path = ARRAY[group_id]`. Every membership or ownership write takes `pg_advisory_xact_lock` on a fixed key, runs the cycle checks, applies the change, and recomputes the whole table with one recursive CTE in the same transaction. The `DISTINCT (group_id, user_id)` projection is the flat effective set.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Storing paths makes the "how does this user have access" column a read of the table instead of a recursive query per page load, and full recomputation is simpler and safer than incremental maintenance at this scale (hundreds of groups, thousands of users).

**Alternatives considered:** Incremental recompute of affected groups only (more code, same lock); computing paths at read time (recursive query per page view).

**Impact:** Each membership write costs a full recompute, serialized across writers. Measure once real data is loaded; if it is too slow, switch to recomputing only the ancestors of the changed group.

**Tags:** [schema, membership, performance, addition, autonomous]

## Audit log targets outside groups

**Design says:** The audit log schema has `group_id: group.id` (not null) but "Logged changes" includes project metadata, quotas and access entry groups, which have no group.

**What was done:** `audit_log.group_id` is nullable. `details` for `metadata_changed` is `{"entity": "group"|"project"|"submit_node"|"user", "entity_id": int, "changes": {"field": {"old": ..., "new": ...}}}`. Group-related entries still fill `group_id`.

**Decided by:** HIL (user), 2026-11-03. The user confirmed ("Okay").

**Why:** A not-null `group_id` cannot hold a project metadata change.

**Impact:** Querying "everything that happened to project 12" filters on `details->>'entity'` and `details->>'entity_id'`. Staff may prefer a dedicated nullable `project_id` column; that is a small follow-up migration.

**Tags:** [schema, audit, clarification, hil]

## Append-only audit log enforced in app

**Design says:** "Every change writes an append-only audit log entry".

**What was done:** There are no update or delete routes for `audit_log` and the service only inserts. No database trigger blocks updates or deletes.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** `actor_id` and `member_user_id` are `ON DELETE SET NULL`, which is an update the database performs when a user is deleted; a blanket block-update trigger would break user deletion.

**Impact:** A database superuser or a script can still alter rows. A trigger that blocks `DELETE` and non-FK updates can be added later.

**Tags:** [audit, clarification, autonomous]

## Group description edit permission

**Design says:** The "Permissions" table marks "Edit description" as staff only. The "Group page" section says "Only a group's owners and staff can edit its description."

**What was done:** `PUT /groups/{id}` is staff only for every field, `description` included. Owners administer members (`/groups/{id}/members`) and nothing else. The first implementation let owners edit the description; it was reverted on the user's decision.

**Decided by:** HIL (user), 2026-11-03. The user said: "Only staff can edit group descriptions."

**Why:** The two statements conflict; the group page section is the more specific one, and letting owners edit a free-text description does not change access.

**Impact:** The design's permissions table is the rule; the group-page sentence saying owners edit the description should be corrected in the design doc.

**Tags:** [permissions, groups, design-issue, hil]

## Replace /groups/{id}/users routes with /members routes

**Design says:** Silent on API shape. Members "can include users and groups".

**What was done:** `GET /groups/{id}/members` (effective users with paths), `GET /groups/{id}/direct_members`, `POST /groups/{id}/members` (`user_id` or `group_id`), `DELETE /groups/{id}/members/users/{user_id}`, `DELETE /groups/{id}/members/groups/{group_id}`. The old `/groups/{id}/users` routes and `PATCH /users/{id}/groups/{group_id}` are removed.

**Decided by:** HIL (user), 2026-11-03. The user confirmed ("Okay").

**Why:** A member can now be a group, so a user-only route family does not fit.

**Impact:** The UI's group and user pages must move to the new routes in the UI round.

**Tags:** [api, groups, clarification, hil]

## Naming of auto-created administrator groups

**Design says:** When staff create a group that needs delegation, `O` and `M` are created with it; projects get a `pi_group`, managers group and `project_group`. No names are specified. Group names are at most 32 characters.

**What was done:** For a group `B`: owners group `{B}_owners`, managers group `{B}_managers`. For a project with name `N`: `{slug}_pi`, `{slug}_managers`, `{slug}` where `slug` is `N` lower-cased with characters outside `[a-z0-9_-]` replaced by `_`. The base is truncated so the full name fits in 32 characters; if a name is taken, `_2`, `_3`, ... is appended. Staff can pass explicit names or existing group ids instead.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Something deterministic is needed for the migration and for `POST` defaults.

**Impact:** The migration creates three groups per existing project with these names. Staff should review the generated names, especially where a project and an existing group share a name (the project group then gets a numeric suffix).

**Tags:** [groups, naming, addition, autonomous]

## Automatic data migration

**Design says:** "A migration script moves data from the existing groups, user_groups, projects, and user_projects tables. Some records will be mapped by hand."

**What was done:** One alembic revision does the whole mapping: existing groups keep their rows (owner null); `user_groups` rows become direct user members; each project gets a pi group (members: `user_projects.role = 'PI'` rows plus `projects.pi` if it is a user id), a managers group (owner: pi group; member: pi group) and a project group (owner: managers group; members: pi group plus every `user_projects` row, `created_at` preserved; the group takes the rows' most common external manager as its `managed_by`); `is_primary` becomes `users.primary_project_id` (latest `updated_at` wins if a user has several). Effective membership is recomputed at the end. No records are mapped by hand.

**Decided by:** HIL (user), 2026-11-03. The user confirmed the automatic mapping ("Okay").

**Why:** The migration has to be runnable in CI against an empty database and in production without a manual step in the middle.

**Impact:** If some projects should reuse an existing group as their project group (for example a group that already has the project's unix_gid), staff do that after the migration by repointing `project_group_id` and deleting the generated group.

**Tags:** [migration, clarification, hil]

## Unix groups export endpoint

**Design says:** "A group with a non-null unix_gid maps to a Unix group. Every effective member of the group is a member of the Unix group." Effective membership is read by "Unix group generation, and downstream consumers".

**What was done:** `GET /unix_groups` (staff or API token) returns `[{id, name, unix_gid, members: [username, ...]}]` for every non-deleted group with a `unix_gid`, built from `group_effective_members` and `users.username`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The design names unix group generation as a consumer but gives it no interface.

**Impact:** Downstream tooling can switch from reading `user_groups` to this endpoint.

**Tags:** [api, unix-groups, addition, autonomous]

## Non-staff group listing

**Design says:** "Every group has a group page. Only its owners and staff can view it." Silent on listing.

**What was done:** `GET /groups` for a non-staff user returns only groups whose `owner_group_id` is a group the user is an effective member of. Staff see all; `include_deleted=true` (staff only) includes soft-deleted groups.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** A list that shows groups the user cannot open is not useful and leaks names.

**Impact:** None for staff.

**Tags:** [api, permissions, clarification, autonomous]

## Remove RoleEnum and add project PI routes

**Design says:** "role replaced by PI and member groups on project"; "pi_group has a null owner_group. Only staff change it."

**What was done:** `RoleEnum`, `user_projects.role`, `UserPostFull.primary_project_role` and `ManagedUserProjectPut.role` are removed. `GET /projects/{id}/pis`, `POST /projects/{id}/pis {user_id}` and `DELETE /projects/{id}/pis/{user_id}` (staff only) manage direct user members of `pi_group`. `joined_projects` and `GET /projects/{id}/users` expose `is_pi` (effective member of the pi group) and `is_primary` (`users.primary_project_id` matches) so existing consumers keep a flag.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The role is now derived from group membership; a PI route keeps the common case (add a PI to a project) a single call.

**Impact:** `isye-manifest-sync` and any other `/managed` caller that sends `role` must stop; unknown fields are rejected.

**Tags:** [api, projects, clarification, autonomous]

## Drop automatic unix_gid allocation

**Design says:** "unix_gid: unix group id, unique (null implies no unix group)".

**What was done:** The migration drops `trg_assign_lowest_unix_gid` (baseline `7ef6196182e3`) before it inserts any group, and downgrade recreates it. `trg_check_unix_gid_uid_unique` and the `chk_unix_gid_range` constraint stay. `POST /groups` without `unix_gid` creates a group with a null `unix_gid`. Staff allocate one on demand with `POST /groups/{id}/unix_gid` (`membership.allocate_unix_gid`): the lowest gid in 40000-60000 held by no group and no user's uid, taken under an advisory lock, audited as `metadata_changed` with `reason: allocated`; 409 if the group already has one or the range is full.

**Decided by:** HIL (user), 2026-11-03. Shown the dropped trigger, the user said: "Please make an endpoint that will allocate a unix_gid using the previous methodology."

**Why:** With the trigger in place every generated group (three per project in the migration, plus `_owners` and `_managers` groups on every `administration` create) would get a gid from the 40000-60000 range and appear in `/unix_groups` as a unix group. That uses up the range and exports groups nobody meant to be unix groups.

**Alternatives considered:** Keep the trigger and accept generated unix groups; keep it but skip it for generated groups through a session setting.

**Impact:** New groups are not unix groups until staff allocate or set a gid. The UI group page gets an "Allocate GID" action.

**Tags:** [schema, unix-groups, deviation, hil]

## Note trigger reads group membership

**Design says:** Silent. The baseline trigger `trg_check_user_in_project_for_note` rejects a `user_notes` row whose user has no `user_projects` row for the project.

**What was done:** The migration replaces `check_user_in_project_for_note()` so it checks that the user is an effective member of the project's `project_group_id` (`group_effective_members`). Downgrade restores the old function body.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Dropping `user_projects` would otherwise make every note tied to a user fail at runtime with "relation user_projects does not exist".

**Impact:** A note can be attached to a user who has access to the project through the pi group or any nested group, as well as a direct member. A project without a `project_group_id` accepts no user-tied notes.

**Tags:** [schema, migration, notes, addition, autonomous]

## Owner references cleared by deletion use owner_group_changed

**Design says:** Deletion "sets references to the group to null: `owner_group`, ..." and "writes audit log entries for all of the above". The contract says `metadata_changed` for each cleared reference.

**What was done:** For `groups.owner_group_id` the entry is `owner_group_changed` with `details {"old": <deleted id>, "new": null, "reason": "group_deleted"}`, `group_id` = the group that lost its owner, `member_group_id` = the deleted group, `caused_by` = the `group_deleted` entry. Data access, submit node, `pi_group_id` and `project_group_id` references use `metadata_changed` as the contract says, with `group_id` = the deleted group.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The design lists "`owner_group` changes" as their own logged change, and `owner_group_changed` is the action that answers "who used to own this group".

**Impact:** Anything reading the audit log for ownership history sees these under one action.

**Tags:** [audit, groups, clarification, autonomous]

## GET /groups keeps 403 for anonymous callers

**Design says:** Silent.

**What was done:** `GET /groups` raises 403 "User is not an admin" when there is neither a staff session, an API token nor a cookie user. A token without permission for the route also reaches this branch, which `test_token.py::test_use_token_on_unauthed_route` expects to be 403.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The router used to be admin-only and that test (not part of this change) pins the 403.

**Impact:** None for logged-in users.

**Tags:** [api, permissions, clarification, autonomous]

## joined_projects membership columns are nullable

**Design says:** Silent.

**What was done:** `joined_projects` LEFT JOINs the direct membership: `direct` says whether one exists, and `created_at` and `updated_at` are NULL for a user who reaches the project only through another group. `JoinedProjectView` (schema) makes those two fields optional. (`managed_by` was a column of this view while memberships carried it; it now lives on the group.)

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** There is no relationship row to take them from.

**Impact:** Consumers of `/projects/{id}/users` and `UserGetFull.projects` must handle nulls.

**Tags:** [schema, views, clarification, autonomous]

## Numeric suffix goes after the role suffix

**Design says:** The changelog says a taken name gets `_2`, `_3`, ... appended.

**What was done:** `{slug}_pi` taken becomes `{slug}_pi_2`; the base is truncated so the whole name stays within 32 characters. Deleted groups count as taken. A project whose slug is empty uses `project`. The migration and `membership.unique_group_name` implement the same rule.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Appending at the end keeps the role suffix readable.

**Impact:** The pi, managers and project groups of one project can end up with different numbers (for example `genome_lab_pi`, `genome_lab_managers`, `genome_lab_2`).

**Tags:** [groups, naming, clarification, autonomous]

## create_project_groups sets the project columns

**Design says:** Silent.

**What was done:** `create_project_groups(session, actor_id, project)` returns the three groups and also sets `project.pi_group_id` and `project.project_group_id`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Every caller needs both steps; doing them in one place keeps them from drifting.

**Impact:** The project must already be flushed (its id is written into the audit `created_for`). Wave 2 callers need not set the columns again.

**Tags:** [projects, services, clarification, autonomous]

## Migration mapping details

**Design says:** The changelog: each project gets a pi group (PI role rows plus `projects.pi` if it is a user id) and a project group (pi group plus every `user_projects` row).

**What was done:** `projects.pi` is only added when a `users` row with that id exists (it was never a foreign key). Every `user_projects` row, PIs included, becomes a direct member of the project group with `created_at` and `updated_at` kept (the group's `managed_by` is the rows' most common external manager, else `APPLICATION`); PI rows are also direct members of the pi group with the same values. `users.primary_project_id` comes from `is_primary` ordered by `updated_at DESC, id DESC`. Existing `user_groups` rows copy over unchanged. Downgrade leaves generated groups in place, rebuilds `user_projects` from direct project-group and pi-group user members, sets `projects.pi` to the lowest direct pi member, and copies direct user members of every other group into `user_groups`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Keeping PIs as direct project-group members preserves their `created_at` and keeps the sync endpoints, which own a group's direct user members, working on the same rows as before.

**Impact:** A downgrade followed by another upgrade creates a second set of generated groups (`_2` names), because the first set is kept.

**Tags:** [migration, clarification, autonomous]

## Wave 2 behaviour pulled forward

**Design says:** Wave 2 reworks projects, users, forms and managed routes.

**What was done:** To keep the app importable and the wave 1 tests runnable: `POST /projects` creates the project groups; `POST /users` adds the user to `primary_project_id`'s project group and stores `primary_project_id`; `_patch_user_submit_nodes` uses `add_member`/`remove_member`; `POST` and `DELETE /projects/{id}/users` use the project group; both managed syncs use `add_member`/`remove_member` and set or clear `users.primary_project_id`; user form approval clears the user's direct memberships, adds the project group membership and sets the primary project. `PATCH /users/{id}/projects/{project_id}`, `PATCH /projects/{id}/users/{user_id}` and `PATCH /users/{id}/groups/{group_id}` are removed. `ManagedUserProjectPut` forbids extra fields (no `role`). `ProjectPost`, `ProjectPatch` and `ProjectTableSchema` gain `pi_group_id`, `project_group_id`, `expires_at` and lose `pi`. Five wave 2 test modules had their `RoleEnum` import removed so pytest can collect them; their role assertions fail until wave 2 rewrites them. Each stubbed spot has a `# TODO(wave 2)` comment.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The code could not import otherwise, and `user_factory` needs these paths.

**Impact:** Wave 2 agent P can keep or replace these; the audit of primary-project changes and the permission checks for project administrators are not done.

**Tags:** [api, scope, addition, autonomous]

## AuditLog has no Patch schema

**Design says:** The audit log is append-only.

**What was done:** `userapp/core/schemas/audit_log.py` has `AuditLogGet` and `AuditLogPost` only.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** A Patch schema for rows nothing may update would invite misuse.

**Impact:** None.

**Tags:** [audit, schema, omission, autonomous]

## member_of path orientation

**Design says:** "Every group this group is a member of, directly or through another group."

**What was done:** `GET /groups/{id}/member_of` returns `[{group, paths}]` where each path runs from the containing group down to `{id}` (for example `[C, B, A]`), shortest paths first, the same orientation as `group_effective_members.path`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** One orientation across every path the API returns.

**Impact:** The UI reads these paths the same way as the members table.

**Tags:** [api, groups, clarification, autonomous]

## Design inconsistency: unix_gid null vs automatic allocation

**Design says:** "unix_gid ... (null implies no unix group)" and "A group with a non-null unix_gid maps to a Unix group". The existing schema gives every inserted group a gid through `trg_assign_lowest_unix_gid`, and the old tests treat that as a feature.

**What was done:** See "Drop automatic unix_gid allocation".

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The two cannot both hold once groups are created as a by-product of other things.

**Impact:** Staff should confirm null-means-none is the intended rule.

**Tags:** [schema, design-issue, autonomous]

## Per-group and per-user log routes 404 on unknown ids

**Design says:** Silent. The contract only gives the filter conditions.

**What was done:** `GET /groups/{id}/audit_log` returns 404 when no group row exists (soft-deleted groups are found, so staff read their history). `GET /users/{id}/audit_log` returns 404 when no user row exists. A non-staff caller who is not allowed gets 403 first, as the dependencies run before the lookup.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** An empty list for a typo in an id looks like "nothing happened". A deleted user's entries have their ids set to null by the FK, so that route cannot show them anyway.

**Impact:** None for existing callers.

**Tags:** [api, audit, clarification, autonomous]

## AuditLogGet nests actor, member user and member group

**Design says:** The audit log lists ids only.

**What was done:** `AuditLog` has `actor`, `member_user` and `member_group` relationships (`lazy="selectin"`, `viewonly=True`). `AuditLogGet` returns them as `UserGet`/`GroupGet` next to the flat ids, on the list and the single-entry routes alike.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The pages that show the log need names, and the ids are kept so filters and `caused_by` chains still work. The `group_id` target is not nested; the group page already knows it, and the global list can look it up.

**Impact:** Each page of the log costs up to three extra `IN` queries (one per relationship). `group_id` has no nested group.

**Tags:** [audit, schema, addition, autonomous]

## Access summary shape

**Design says:** The group page shows "every access object the group is associated with, directly or through membership in another group". The contract gives `via` per object and `{project_id, name, display_name, as, via}` for projects.

**What was done:** Every row also has `group_id`, the group the object references, so a reader can tell which ancestor grants it. A project whose `pi_group_id` and `project_group_id` both fall in the group's reach gets one row per role (sorted by project id then role). Projects have no `group_id` on the contract list; it was added to them as the brief says. Deleted groups have no memberships, so nothing is reached through them. Asking about a deleted group returns 200 with whatever still references it (nothing, since deletion nulls the references).

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Without `group_id` a project reached through two ancestors cannot say which path belongs to which group, and one row per role matches the UI's "as" column.

**Impact:** The UI can group rows by `group_id`; a PI-group project can show twice.

**Tags:** [api, groups, clarification, autonomous]

## Unix group member rules

**Design says:** "Every effective member of the group is a member of the Unix group."

**What was done:** `/unix_groups` lists `users.username` only when it is not NULL, so a member without a username is skipped (they have no account to be a member of).

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** A NULL in a member list would break consumers.

**Impact:** A user whose username is later set appears on the next call.

**Tags:** [api, unix-groups, clarification, autonomous]

## Submit node audit

**Design says:** Audit log covers "access entry groups"; submit nodes are the login access entries (changelog).

**What was done:** `PUT /submit_nodes/{id}` compares each sent field with the stored value and writes one `metadata_changed` entry (`entity` "submit_node", `group_id` = the group after the change) listing only the fields that changed; nothing is written when nothing changed. An unknown id is 404 as before. Create and delete of submit nodes are not audited (the contract asks for PUT only).

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Matches how group updates are logged.

**Impact:** Creating or deleting a submit node, and the group clearing done by group deletion, are recorded only through the deletion's own entries.

**Tags:** [audit, submit-nodes, clarification, autonomous]

## Query parser timestamps and 400 on bad filters

**Design says:** Silent; this is the pre-existing filter syntax (README "Query Parser Docs").

**What was done:** `userapp/query_parser.py::cast_to_column_type` parses `datetime`/`date` columns with `fromisoformat`, so `?occurred_at=gt.2026-11-03T10:00:00` works on `/audit_log` and `?created_at=...` on any other list. `userapp/main.py` gains an exception handler that turns `ParserException` into a 400 `{"detail": "Invalid query parameters: ..."}`. Agent A's route-local `occurred_at` parsing in `audit_log.py` was removed in favour of this. Tests: `test_query_parser.py::test_gt_timestamp`, `test_invalid_timestamp`; `test_audit_log.py` covers the 400.

**Decided by:** Autonomous (Claude, reviewer). The user was not asked; found while reviewing agent A's workaround.

**Why:** `datetime(value)` is not a constructor, so every timestamp filter crashed, and an unhandled `ParserException` reached the generic 500 handler.

**Impact:** Any client that filtered on a timestamp column and got a 500 now gets results. Clients sending a bad filter now get a 400 with the parser's message instead of a 500.

**Tags:** [api, query-parser, error-handling, addition, autonomous]

## POST /projects with one group supplied

**Design says:** The contract: "if one is given, validate it exists and is not deleted and create only the missing one (record this as a delta)". The design's Project section describes the three-group structure only for the default case.

**What was done:** Both ids absent calls `create_project_groups`. With only `pi_group_id`: the managers group (owner = the given pi group, pi group a member) and the project group (owner = managers, pi group a member) are created, named from the project slug. With only `project_group_id`: only a pi group (no owner) is created and nothing about the supplied project group is changed. Both ids present: nothing is created. Created groups get `group_created` audit entries with `created_for` set to the project and the role.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** A project group without a managers group would have no delegation tier, so a missing project group brings the managers group with it. A supplied project group is staff's choice, so its owner and members are not edited.

**Impact:** A project created around an existing project group has a pi group that is not a member of it; staff add that membership if they want PIs to receive project access.

**Tags:** [projects, groups, clarification, autonomous]

## Project view rule

**Design says:** "Members of the pi_group edit the project's metadata." Silent on who may view a project.

**What was done:** `GET /projects/{id}`, `/projects/{id}/users` and `/projects/{id}/pis` allow staff, effective members of the pi group, and administrators of the project group (the managers). `GET /projects` and the notes routes stay staff only. The rule is `check_can_view_project` in `routes/projects.py`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The people who can edit the project or its members need to see it; security.py was not editable in this wave.

**Impact:** The dependency could move into security.py next to `check_can_edit_project`.

**Tags:** [permissions, projects, addition, autonomous]

## PI PUT field restriction

**Design says:** "Members of the pi_group edit the project's metadata"; "pi_group ... Only staff change it."

**What was done:** A non-staff PI whose body names any of `pi_group_id`, `project_group_id`, `accounting_group`, `staff1`, `staff2` gets 403, whether or not the value differs from the stored one. Staff changing `pi_group_id` or `project_group_id` must name a live group (404 otherwise).

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Checking the field set rather than the diff keeps the rule independent of what the client last read.

**Impact:** A UI form that always sends the whole project must omit those fields for PIs.

**Tags:** [permissions, projects, clarification, autonomous]

## Removal 404 names the access path

**Design says:** Silent. The contract asks the 404 to say when access comes only through another group.

**What was done:** `DELETE /projects/{id}/users/{uid}` and `DELETE /projects/{id}/pis/{uid}` look the user up in `group_members_view`. A non-direct member gets 404 "User is not a direct member of this project's group; access comes through A > B, C" (the groups below the project group on each path); no row gets 404 "User is not a member of this project's group". The pi route says "pi group". The removal itself goes through `remove_member`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The caller can only act on the groups below the one they edited.

**Impact:** The path text is meant for people; clients should not parse it.

**Tags:** [api, projects, clarification, autonomous]

## Primary project changes are audited

**Design says:** "Metadata changes ... project metadata" are logged; the primary project is silent.

**What was done:** `routes/_util.py::set_primary_project` sets `users.primary_project_id` and writes `metadata_changed` with `{"entity": "user", "entity_id", "changes": {"primary_project_id": {"old", "new"}}}`, doing nothing when the value is unchanged. It is used by `PATCH /users/{id}`, form approval and the managed project sync. `POST /users` writes the same entry as a change from null when `primary_project_id` is given.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The primary project decides where usage is attributed, so changes to it need a trail; the contract asked for it on PATCH and wave 1 left TODOs for the rest.

**Impact:** Entries have no `group_id`; filter on `details->>'entity' = 'user'`.

**Tags:** [audit, users, addition, autonomous]

## PATCH users primary_project_id

**Design says:** Silent. The contract: "staff may set primary_project_id".

**What was done:** `UserPatch` gains `primary_project_id`. Staff sending it set it (null clears it, an unknown project is 404, membership is not required or created). A non-staff user editing themselves goes through `RestrictedUserPatch`, which ignores the field like every other staff-only field. `PATCH /users` now calls `session.expire_all()` before re-reading so the `projects` view rows show the new `is_primary`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The design says the primary project need not reference a membership.

**Impact:** None.

**Tags:** [api, users, clarification, autonomous]

## Managed sync with is primary false clears the primary

**Design says:** "A user keeps their primary project after removal from that project's group." Silent on a sync that lists a user without `is_primary`.

**What was done:** In `PUT /managed/{m}/projects/{id}/users`, a listed user with `is_primary: true` gets `primary_project_id` set to the project; a listed user with `is_primary: false` whose primary is this project has it cleared. Users the sync removes keep their primary project.

**Decided by:** HIL (user), 2026-11-03. The user confirmed this behaviour ("Okay").

**Why:** The old `is_primary` column was replaced on every sync, so a caller that stops saying "primary" expects it cleared. Removal is different and follows the design.

**Impact:** A sync that omits `is_primary` for a user whose primary is that project clears it.

**Tags:** [managed-sync, users, clarification, hil]

## Managed sync responses

**Design says:** Silent.

**What was done:** `PUT /managed/{m}/groups/{id}/users` returns the group's direct `GroupMembersView` rows (it returned `user_groups_view` rows before), and the project variant the project's direct `joined_projects` rows. A project sync on a project without a project group answers 404 (wave 1 answered 400). Syncs pass the cookie user as `actor_id`, None for an API token. The response query uses `populate_existing` so the `is_primary` it reports is the one just written.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Contract and identity-map correctness.

**Impact:** `isye-manifest-sync` readers of the group response now see `group_members_view` columns.

**Tags:** [managed-sync, api, clarification, autonomous]

## Membership PATCH tests removed

**Design says:** Silent.

**What was done:** `test_user_membership_patch.py` is deleted: it covered `PATCH /users/{id}/projects/{id}` and `PATCH /users/{id}/groups/{id}`, which wave 1 removed. The replacement route, `PATCH /groups/{id}/members/users/{user_id}`, went too when `managed_by` moved to the group; `test_groups.py::test_removed_routes` checks all three are gone.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** Nothing the file tested survives.

**Impact:** None.

**Tags:** [tests, omission, autonomous]

## Test helpers and audit assertions

**Design says:** Silent.

**What was done:** `conftest.py` gains `db_rows` (read-only SQL), `audit_rows` (audit entries since the current test started, via an autouse fixture that remembers `MAX(audit_log.id)`), `plain_user_factory` (users without project or group, cleaned up) and `client_as`. `test_users.py` also stopped reusing the fixed username `unixuser100`.

**Decided by:** Autonomous (Claude). The user was not asked.

**Why:** The baseline seed resets id sequences each session, so user and project ids repeat across runs on the same database and old audit entries would match.

**Impact:** `test_membership.py` keeps its own copies of the same helpers.

**Tags:** [tests, addition, autonomous]

## canAdminister for non-staff

**Design says:** Owners and staff can edit membership; only they can view the pages.

**What was done:** `GroupMembersPanel` takes `canAdminister`; the group page passes `true` after the page fetch succeeded. Staff-only parts (user links) depend on `currentUser.is_admin`.

**Decided by:** Autonomous (Claude), per brief.

**Why:** `check_can_view_group` admits only staff and administrators.

**Impact:** If the API ever lets a non-owner view these pages, remove controls will show and the API will 403 them.

**Tags:** [ui, permissions, clarification, autonomous]

## User links in members table are staff only

**Design says:** The brief says the members table links to the user.

**What was done:** The link icon renders only for staff.

**Decided by:** Autonomous (Claude).

**Why:** `/users/edit` is a staff page; owners would land on an error.

**Impact:** Non-staff owners see names without links.

**Tags:** [ui, permissions, clarification, autonomous]

## Create and Show deleted controls live in the list view

**Design says:** Staff get "Create Group" and "Show deleted"; non-staff just see their list.

**What was done:** `src/app/groups/layout.tsx` (a server component with no auth) drops its "Add Group" button; the list view renders the buttons for staff. "Create Group" on `/groups/create` shows "Only staff can create groups." to non-staff.

**Decided by:** Autonomous (Claude).

**Why:** The layout cannot know who is viewing.

**Impact:** None for staff.

**Tags:** [ui, groups, clarification, autonomous]

## Group cells show ids, not names

**Design says:** Owner (link to the group).

**What was done:** The link text is "Group {id}". `/groups` rows have ids only.

**Decided by:** Autonomous (Claude).

**Why:** Resolving names needs an extra request per page and the list filters do not take `in.` lists as far as the contract says.

**Impact:** Names show on the target page. The API could nest `owner_group` to fix this.

**Tags:** [ui, lists, omission, autonomous]

## Audit log Group column shows ids

**Design says:** Group (link).

**What was done:** "Group {id}" link; Actor, Member user and Member group show names from the nested objects.

**Decided by:** Autonomous (Claude).

**Why:** `AuditLogGet` has no nested `group`.

**Impact:** API could add one.

**Tags:** [ui, audit, omission, autonomous]

## Audit filters apply on Search

**Design says:** Filters above the table.

**What was done:** Filter inputs apply on a Search button (and Enter); Clear resets. The group page history has no filters.

**Decided by:** Autonomous (Claude).

**Why:** Typing an id would otherwise fire a request per keystroke.

**Impact:** One extra click.

**Tags:** [ui, audit, addition, autonomous]

## Shared helpers and label prop

**Design says:** Silent.

**What was done:** `src/utils/fetchList.ts` adds `fetchJson`, `fetchList` (rows plus `X-Total-Count`), `ForbiddenError` and `submitJson`. `GroupAutocomplete` takes an optional `label`. `GroupMemberOfPanel` is exported from `GroupAccessPanel/`.

**Decided by:** Autonomous (Claude).

**Why:** Four pages needed the same 403 handling and totals.

**Impact:** `GroupAutocomplete` change is backwards compatible (agent P files untouched).

**Tags:** [ui, addition, autonomous]

## Deleted group page

**Design says:** "A deleted group shows an Alert and no edit controls."

**What was done:** Alert plus read-only form; the Members panel is hidden (deletion removes all memberships); Member of, Access and History remain.

**Decided by:** Autonomous (Claude).

**Why:** Nothing can be added to a deleted group (the API 404s).

**Impact:** None.

**Tags:** [ui, groups, clarification, autonomous]

## Alerts

**Design says:** Silent.

**What was done:** Group members use `ADD_MEMBER_SUCCESS(name)` / `REMOVE_MEMBER_SUCCESS(name)`; failures use `ACTION_ERROR`. Deleted-group and GID messages use the existing keys.

**Decided by:** Autonomous (Claude).

**Why:** No new keys needed.

**Impact:** None.

**Tags:** [ui, clarification, autonomous]

## Group pickers on ProjectForm

**Design says:** Staff-only PI group and Project group; blank on create generates the three groups.

**What was done:** Local GenericAutocomplete<Group> inputs labelled "PI Group" and "Project Group". On edit, a group id is sent only when set. Create has a "PIs" multi-select sending `pi_ids` when non-empty. The "generated group names as links in edit mode" requirement is met by the "PI group"/"Project group" chips on the project page (static labels; no group fetch, since a PI may not be allowed to read the groups).

**Decided by:** Autonomous (Claude).

**Why:** Avoids touching agent G's component; chips avoid a possible 403.

**Impact:** The chips show "PI group"/"Project group", not the generated names.

**Tags:** [ui, projects, permissions, clarification, autonomous]

## Members and PI tables

**Design says:** Members table below the metadata; PIs table; PI/primary flags.

**What was done:** ProjectMembersTable merges `GET /groups/{project_group_id}/members` with `GET /projects/{id}/users` (page_size=10000) by user id. Add/remove/primary use existing alert keys (ADD_MEMBER_SUCCESS, REMOVE_MEMBER_SUCCESS, UPDATE_PRIMARY_PROJECT_SUCCESS); failures go through ACTION_ERROR. MembershipPaths links groups only for staff. A project with no project group shows a short message. Remove renders only on direct rows (later superseded for both tables by the shared MembersTable, see "Member groups on every members table").

**Decided by:** Autonomous (Claude).

**Why:** Matches the ui-contract; the API enforces permissions.

**Impact:** None beyond the above.

**Tags:** [ui, projects, clarification, autonomous]

## Primary project on UserForm

**Design says:** Primary project replaces primary_project_role; only staff change it.

**What was done:** Role select removed. Primary project autocomplete shows for staff in create (optional, helper "Also adds the user to the project") and edit (null clears; sent only when changed). Non-staff do not see it.

**Decided by:** Autonomous (Claude).

**Why:** The API ignores the field for non-staff.

**Impact:** The create form no longer requires a project.

**Tags:** [ui, users, clarification, autonomous]

## User tables

**Design says:** Silent on the user page tables beyond the primary project rule.

**What was done:** UserProjectTable: PI check, Primary star (PATCH /users/{id} {primary_project_id}), Remove only for a direct row (`direct`), otherwise "via group". UserGroupTable uses UserGroupsView with MembershipPaths (linkGroups follows adminView) and Remove for direct rows; the Point Of Contact column is dropped (field removed). Email page sends `is_pi=eq.true`.

**Decided by:** Autonomous (Claude).

**Why:** Follows the contract.

**Impact:** The non-staff view of these tables shows no controls, as before.

**Tags:** [ui, users, clarification, autonomous]

## Member groups on every members table

**Design says:** Section "Access management UI": "The members view is a table of every user with access through the group. One column shows how each user has access", and "All access management pages include membership management for their group." The project section says PIs and managers manage project membership; it does not say whether the page offers groups as members.

**What was done:** One shared `MembersTable` component (`src/components/MembersTable/MembersTable.tsx`) renders the member groups (a "Direct" chip, removable) above every user with access and their paths, with an "Add user" and an "Add group" picker side by side. `GroupMembersPanel` (group page, data access page), `ProjectMembersTable` and `ProjectPiTable` all render it with their own routes. For the project pages the API gained `GET/POST /projects/{id}/groups`, `DELETE /projects/{id}/groups/{gid}` (project group; staff, PIs and managers, as `/users`) and `GET/POST /projects/{id}/pi_groups`, `DELETE /projects/{id}/pi_groups/{gid}` (pi group; staff only, as `/pis`), returning `group_members` rows (`GroupMemberGet`). The GET routes use the project view rule, so a non-staff PI, who cannot read the pi group through `/groups/{id}/direct_members` because that group has no owner, still sees its member groups.

**Decided by:** HIL (user). The user asked "Why can I only add users to the project group, make it so I can add groups as well. Also I want to see the groups in the project members membership, not just the users," then "the same goes for all places where I can add members to groups I want to see all the members and be able to add members of both types."

**Why:** The group page already listed and added member groups; the project pages went through `/projects/{id}/users` and `/pis`, which only take a user id. Project-level routes keep the project page on the project's permission rule rather than the groups' owner rule.

**Impact:** Additive API surface: six routes, tested in `test_projects.py` (`TestProjectGroupMembers`, `TestProjectGroupMemberPermissions`). Adding the pi group to the project group at creation now shows as a member group row on the project members page, which is the design's wiring made visible. The user pages (a user's own groups and projects) are unchanged: they add a user to groups, not members to a group.

**Tags:** [api, ui, projects, membership, addition, hil]

## Expiry and data access are left out of this update

**Design says:** The "Project" section gives projects `expires_at`, groups have `expires_at` in the groups schema, and the "Data access" section describes `backing_stores` and `data_access` as access metadata on groups, with list/edit pages in the UI.

**What was done:** Removed from the migration, models, schemas, routes, tests and UI: `groups.expires_at`, `projects.expires_at` (with `GET /projects?include_expired` and the "Expire project" control), the `backing_stores` and `data_access` tables, `/backing_stores` and `/data_access`, the `data_access` part of `GET /groups/{id}/access`, the Data Access nav and pages, the project Data Access tab and the group page's data access table. `DELETE /projects/{id}` deletes the row again (as before this work, plus the project's notes); the project's groups stay, `users.primary_project_id` is cleared by the database, and the UI has a staff-only "Delete project" button in its place.

**Decided by:** HIL (user), 2026-11-05: "I would like to keep this update a bit more simple and stick to just migrating to the new groups based user management. Can you please clear out any code that related to the `expires` additions and data access tables." Returning project deletion to a hard delete and leaving the project's groups in place was Claude's reading of that (the soft delete existed only because of `expires_at`); the user was informed in chat.

**Why:** Scope: this update is the group-based membership migration only.

**Impact:** Supersedes the earlier entries on expiry, soft project deletion, backing stores and data access, which are removed from this log. Deleting a project leaves its `_pi`, `_managers` and project groups behind as ordinary groups; staff delete them separately if they are not wanted. The design's data access section is unimplemented and can be a later round.

**Tags:** [schema, api, ui, data-access, projects, omission, hil]

## managed_by moves from memberships to groups

**Design says:** Silent on `managed_by`; the previous schema tagged each `user_projects` / `user_groups` row with the system that owned it, and this log's earlier entry kept that per membership row.

**What was done:** `groups.managed_by entity_manager_enum NOT NULL DEFAULT 'APPLICATION'`; `group_members` has no `managed_by`. Staff set it on `POST /groups` and `PUT /groups/{id}` (audited as `metadata_changed`); `GroupMemberPost`, `UserProjectPost` and the member views no longer carry it, and `PATCH /groups/{id}/members/users/{uid}` is gone. A managed sync (`PUT /managed/{m}/groups/{id}/users`, `/projects/{id}/users`) claims the group: an `APPLICATION` group becomes `{m}`-managed (audited, reason `managed_sync`), a group another system manages is refused with 409, and then every direct *user* member not in the list is removed and every listed user added; member *groups* (for a project group, its pi group) are left alone. The migration gives a group the manager found on its old membership rows (the most common non-`APPLICATION` one if several), else `APPLICATION`, and maps it back per row on downgrade. The UI shows a "Managed by X" chip on the group page, a "Managed by" select on the group form (staff only), and a warning above the members table of a managed group (also on the project members page) that the next sync replaces hand-made changes.

**Decided by:** HIL (user), 2026-11-05: "I want to move the `managed_by` field to the group. A group can be managed but not individual memberships to a group." The sync rules (claim on first sync, 409 for a foreign manager, full replacement of user members, groups untouched), the migration's most-common-manager rule and the UI warning are Claude's; the user was informed in chat.

**Why:** A membership is either synced from a system or made by hand; mixing both in one group made the old per-row ownership rules (skip rows owned by someone else) hard to reason about.

**Impact:** Behaviour change for the external syncs: a hand-added user in a Manifest-managed project used to survive syncs and is now removed by the next one. Before migrating, projects or groups whose rows mix managers should be checked: `SELECT project_id, array_agg(DISTINCT managed_by) FROM user_projects GROUP BY project_id HAVING count(DISTINCT managed_by) > 1` (and the same on `user_groups`). Supersedes the entries on per-membership `managed_by`, which are removed from this log; `joined_projects` carries `direct` instead of `managed_by`.

**Tags:** [schema, api, managed-sync, migration, ui, deviation, hil]

## Review fixes after the managed_by move

**Design says:** Silent on all four points. The "Audit log" section asks for membership and access-entry changes to be logged; the "Access management UI" section says the project pages are for PIs and managers.

**What was done:** (1) `POST /submit_nodes` and `PUT /submit_nodes/{id}` check the group with `get_live_group`: an unknown or deleted group is a 404 (an unknown one used to be a 400 from the foreign key). (2) The `metadata_changed` entries for `users.primary_project_id` (`set_primary_project`, and the one written by `POST /users`) carry `member_user_id`, so `GET /users/{id}/audit_log`, which selects on member or actor, shows them. (3) `PUT /groups/{id}` with `managed_by: null` is a 400 instead of a NOT NULL violation. (4) `POST /users` with `submit_nodes: null` is treated as an empty list instead of a 500. (5) UI: `ProjectPiTable` reads the pi group's member groups through `GET /projects/{id}/pi_groups` again; reading `/groups/{pi_group_id}/direct_members` returned 403 for every non-staff PI, because the generated pi group has no owner, and the whole table was replaced by the access error. (6) UI: the primary-project star on a user's projects table and on the project members table also revalidates the cached user record, so the user form cannot write the old primary project back. Edge-case tests were added for these and for: the data migration itself (`test_migration_data.py` builds a scratch database at `b2f6d8e4a9c1`, seeds `user_projects`/`user_groups`/`projects.pi` rows, upgrades and checks names, memberships, `managed_by`, primary projects, views and audit rows, then downgrades and checks the rows that come back), duplicate names and uid collisions on `PUT /groups/{id}`, a deleted group as an owner on `POST /groups`, two projects whose names slug the same, a managed sync dropping a user who keeps access through a member group, a sync reclaiming a group staff handed back, and a refused sync writing no audit row.

**Decided by:** Autonomous (Claude), from the review the user asked for on 2026-11-05; the user was informed in chat.

**Why:** Each is a case where the implementation contradicted its own rules (the audit route's selection, the PI table's permission, the enum column's NOT NULL) rather than a new design choice.

**Impact:** `POST /submit_nodes` with an unknown group changes from 400 to 404. The migration test needs CREATEDB on the test role (CI's postgres superuser has it) and skips otherwise; it runs in about four seconds.

**Tags:** [api, ui, audit, submit-nodes, addition, autonomous]
