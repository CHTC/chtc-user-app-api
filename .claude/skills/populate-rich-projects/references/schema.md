# Schema and access reference

## `projects` table

Defined in `userapp/core/models/tables.py`; API schema in
`userapp/core/schemas/projects.py`. Columns relevant to this skill:

| Column | Notes |
|---|---|
| `id` | primary key |
| `name` | the accounting/project identifier, e.g. `AnimalSciencesGianola` — this is what you'll join against `mapping_all.csv` and topology filenames |
| `accounting_group` | related identifier, sometimes differs from `name` |
| `display_name` | one of the five fields you're proposing values for |
| `description` | one of the five fields you're proposing values for |
| `url` | one of the five fields you're proposing values for — but check it before assuming it's already handled: a non-null `url` can still be a dead link, which counts the same as blank (see SKILL.md Step 1) |
| `pi`, `staff1`, `staff2` | user IDs — join to `users` for names if useful context |
| `college_and_department_id` | FK, one of the five fields |
| `fos_id` | FK, one of the five fields |
| `status` | existing context, not something you're changing |

## `college_and_departments` reference table

UW–Madison's official college → department list, 146 rows. Seeded from
`alembic/data/colleges_and_departments.csv` (that CSV is a convenient local
copy if you don't want to hit the DB for it — it won't change while you
work). Columns: `id`, `college`, `department`. Unique on `(college,
department)`.

Note the college names are the *official* long forms — `"College of Letters
& Science"`, `"School of Medicine and Public Health"`, `"Wisconsin School of
Business"` — not the informal short forms you'll see in other sources
(`"Letters and Sciences"`, `"Medicine and Public Health"`, `"Business"`).
Match on `department` first where you can; it's less ambiguous than `college`
naming.

**`proposed_college_and_department_id` must be the actual integer `id` of
the matching row, not a description of one.** Query the
`college_and_departments` table directly rather than assuming a value.
`proposed_college_and_department_name` (a separate output column, see
SKILL.md Step 3) is `college` and `department` from that same row, pulled
from the table — not typed from memory.

**The row's `id` is just its 1-indexed position in
`alembic/data/colleges_and_departments.csv`.** The table was seeded with
`op.bulk_insert` straight from that CSV in file order (see the migration's
own comment on this), and Postgres assigned `id` sequentially as it went —
so row 2 of the CSV got `id = 2`, row 70 got `id = 70`, and so on. This was
confirmed against the live dev DB (`SELECT id, college, department FROM
college_and_departments WHERE id IN (2, 4, 70)` returned exactly the rows
the CSV positions predicted), so it's a reliable way to sanity-check a
lookup, or even to get the id directly by counting CSV rows if you don't
want to hit the DB for every one. The DB lookup is still the thing to trust
if the two ever disagree.

## `fields_of_science` reference table

The NSF SED-CIP taxonomy, 1,651 rows, seeded from
`alembic/data/fields_of_science.csv`. Columns: `fos_id` (a CIP-style code,
e.g. `26.1104`), `sed_cip_title`, `broad_field` (16 top-level categories),
`major_field` (66 categories), `detailed_field`.

This table is fine-grained — picking the *correct* `fos_id` for a project
usually needs either an exact code from an external source (topology gives
you this directly) or a deliberate choice of which "detailed"/"other" row
within a `major_field` bucket best fits a coarser hint. Either way,
`proposed_fos_id` should be the literal code (e.g. `26.0202`), looked up
directly from the `fields_of_science` table — never a description of which
row you mean. `proposed_fos_name` (a separate output column, see SKILL.md
Step 3) is that row's `sed_cip_title`, pulled from the same lookup — if the
code doesn't actually exist in the table, this lookup comes back empty,
which is exactly how you catch a bad code before it ships.

## Reaching the dev database

**Two absolute rules, before anything else in this section:**

- **Only ever connect to the dev instance** — the `chtcdev` Kubernetes
  namespace, nothing else. Never touch prod, under any circumstance, for
  any reason. If you're ever unsure whether something in front of you is
  dev or prod, stop and ask rather than guessing.
- **Read-only, always, even within dev.** Every command in this section is a
  `SELECT`. Never run anything that writes, updates, or deletes a row —
  `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `ALTER`, `DROP`, none of it —
  regardless of how confident you are or how small the change seems. This
  skill's entire purpose is producing a proposal for a human to apply; it
  never applies anything itself.

This skill runs in manual permission mode — you run these commands
yourself, directly, and confirm each one the normal way. There's no
classifier to work around here and nothing in this section needs a special
permission rule.

1. **Check connectivity first.** Find the dev postgres pod:
   ```bash
   kubectl get pods -n chtcdev -l "postgres-operator.crunchydata.com/role=master,postgres-operator.crunchydata.com/cluster=chtc-userapp" -o jsonpath='{.items[0].metadata.name}'
   ```
   If this fails or hangs, the VPN isn't connected (or `kubectl` isn't
   pointed at the right context). **Stop and tell the user** — this is the
   "if something you need is blocked, stop" case from earlier: report that
   the cluster isn't reachable and ask them to connect the VPN, rather than
   retrying blindly.

2. **Open the tunnel yourself, as a background process**, once you have the
   pod name:
   ```bash
   kubectl -n chtcdev port-forward <pod> 5432:5432 > /tmp/chtcdev-port-forward.log 2>&1 &
   disown
   ```
   Leave it running for the rest of your work in this session.

3. **For the actual reads, use `kubectl exec` straight into the pod**
   (container name `database`) — this has been the reliable path, bypassing
   the port-forward's own fragility under rapid or repeated connections:
   ```bash
   kubectl exec -n chtcdev <pod> -c database -- env PGPASSWORD="$DB_PASSWORD" \
     psql -U "$DB_USER" -d "$DB_NAME" -h localhost -c "<query>"
   ```
   (Heredocs piped over `kubectl exec` stdin have been flaky — pass the
   query with `-c` instead.) Batch what you need into as few calls as
   practical (all matched projects in one query where you can) rather than
   one call per project.

This connects to a real shared dev database — use it for `SELECT` queries
only. Don't run anything that writes, updates, or deletes rows; this skill
only proposes values; it doesn't apply them.

There is no API fallback for any of this. The app does have a REST API, but
this skill doesn't use it — not for reads, not as a backup when the DB
connection is down, not for anything. If the DB is unreachable, that's the
"if something you need is blocked, stop" case in [SKILL.md](../SKILL.md);
don't improvise an API-based workaround instead.
