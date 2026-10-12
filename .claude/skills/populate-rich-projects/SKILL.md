---
name: populate-rich-projects
description: >-
  Use this to propose values for the CHTC User App's "rich project" fields —
  display_name, description, url, college_and_department_id, and fos_id — on
  rows in the `projects` table that don't have them (or don't have a working
  `url`) yet. Trigger whenever someone
  asks to backfill, populate, enrich, or research project metadata / department
  / college / field-of-science / description data for chtc-user-app-api,
  mentions mapping_all.csv, a project activity/usage file, college_and_departments,
  fields_of_science, or the OSG topology registry (opensciencegrid/topology) in
  connection with project data, or asks to prepare a batch of project field
  updates for review. This
  skill only produces a reviewable proposal — it never writes to the database
  or calls the update API itself, so it's safe to use any time someone wants a
  first pass at this data before a human signs off on it.
---

# Populate rich project fields

The `projects` table has five fields — `display_name`, `description`,
`url`, `college_and_department_id`, `fos_id` — that describe a project's
name, purpose, a link to more about it, department, and field of science.
Any given project may be missing one, several, or all of them, whether
because it was never set, the project is new, or upstream data has changed
since it was last set. `url` is a special case: a project can have a `url`
that's set but no longer works, and a dead link is exactly as much a gap as
a blank one — see Step 1. This skill helps you draft real values for
whatever set of projects you're given, backed by whatever evidence you can
find, for a human to review before anything touches the database.

If you have project memory from earlier runs of this skill, it can be
useful context — but this file is the current, authoritative source for how
to run it. Memory reflects what a past session did or figured out, which can
predate a fix made here since; where the two disagree, follow this file, not
the memory. This has already gone wrong once: a stale memory re-asserted a
workaround for a blocked DB connection that this skill explicitly overrode.

## What you're producing, and what you're not

You are producing a **proposal**, not a database write. For each project you
process, output one row of suggested field values. A human reads that table
and decides what to apply — this skill reads from the dev database to
gather evidence, but makes no write requests of any kind, at any point.
There's no API fallback: use the database, directly, and nothing else.
Treat "propose" as a hard boundary, not a
formality: even a value you're fully confident in goes in the table, not
into the database.

There is no single correct algorithm here — that's deliberate. You have
several data sources of quite different quality and coverage (below), and
the right mix depends on which project you're looking at. Use your judgment
per row. You'll likely be running this over hundreds or thousands of
projects at once, so keep your reasoning terse: a good default row is just
the proposed values with nothing else attached. Save commentary for the rows
that actually need a reviewer's attention (see Step 3) rather than
explaining every row equally — that's what keeps this affordable at scale.

This also isn't a mandate to reason through every project by hand, one at a
time, in the conversation. Parts of this are genuinely mechanical —
computing which projects are in both `mapping_all.csv` and the activity file
(Step 0), or resolving `college_and_department_id`/`fos_id` once you know
which department or code you're matching on — and a script that does that
directly, or that assembles the final CSV from values you've already worked
out, is often faster and less error-prone than typing each row out. Save
your own reasoning for the parts that actually need judgment: which source
to trust for a given project, and what a description should say. Use
whichever mix of scripting and direct reasoning gets you a correct file with
the least wasted effort — that's your call to make, not something this skill
prescribes.

## If something you need is blocked, stop

This skill touches things that are sensitive on purpose — a real dev
database, credentials, `kubectl` access to a cluster — and sometimes the
environment won't let you do that: the VPN isn't connected, the dev
database connection isn't reachable, even a `git clone` failing for network
reasons. When that happens, don't quietly substitute a workaround that
changes what you were actually asked to do, and don't keep going as if it
didn't happen. **Stop, and tell the user, once, clearly:**
- what you were trying to do and why
- exactly what got blocked (the command, and the error as given)
- a concrete next step — for the dev database specifically, per
  [references/schema.md](references/schema.md): the VPN needs to be
  connected before `kubectl` can reach the cluster at all. There is no API
  fallback to offer instead — don't propose an admin session cookie, a dev
  API base URL, or anything API-related; this skill doesn't use the API at
  all.

This matters even when there's a technically-available fallback. Step 1
below is the clearest example: if the DB connection is blocked, you *could*
keep generating proposals using only local files, but you'd have no way to
know whether you're overwriting a value that's already good — so that's a
reason to stop and ask, not a reason to route around the gap silently.

## The five fields

| Field | Type | Points to |
|---|---|---|
| `display_name` | free text | — |
| `description` | free text | — |
| `url` | free text (a link) | — missing *or dead* both count as needing a value |
| `college_and_department_id` | FK | `college_and_departments` (`id`, `college`, `department`) |
| `fos_id` | FK | `fields_of_science` (`fos_id`, `sed_cip_title`, `broad_field`, `major_field`, `detailed_field`) |

Full table/column details, plus how to reach the dev database:
[references/schema.md](references/schema.md).

## This doesn't have to be one straight pass

Nothing about this requires committing to a method on project one and
running it unchanged through the last one, and nothing requires treating the
file as finished the moment every row has values in it. Two points where
it's worth deliberately slowing down:

**Before you settle into a rhythm**, try a handful of varied projects first —
a clean topology match, a messy `mapping_all.csv`-only one, something that
doesn't obviously match anything — and see what actually works. What you
learn (a query pattern worth reusing, a rename crosswalk you'll need
repeatedly, a source that's turning out unreliable for this particular
batch) should shape how you handle the rest, rather than being rediscovered
project by project.

**Before you hand the file back**, go over the rows you weren't fully sure
about — anything with a `note`, or anything you moved through quickly — and
check them again rather than letting first-pass momentum be the last word.
If a value still feels like a guess, it's worth another look, or even a
quick fact-check (the CAI-named-as-CDIS kind of thing) before it ships.
Being unsure about some rows isn't a problem — a `note` exists for exactly
that. Staying unsure about a row you never went back to is.

**For a batch that's actually going to be applied — not a small test run —
this self-review isn't enough on its own; hand the file to an independent
second pass.** A prior batch's self-review missed two real errors (a match
that a stricter re-check found, an invalid `fos_id` that looked plausible
until someone re-derived it from scratch) that only surfaced once a separate
agent redid the work independently, without seeing the first pass's
reasoning, and compared notes. That's a meaningfully stronger check than
re-reading your own output, because it doesn't share your blind spots — you
can't catch your own "this looks right" if the thing that made it look
right was the mistake itself. Worth the roughly-doubled cost before a real
batch goes to a reviewer; not worth it for a handful of rows you're just
sanity-checking the approach with.

**Work against the actual CSV file on disk as you go, not in your own
reasoning until some final step.** Write the header, then append rows — a
section at a time, a subset at a time, one script's output at a time,
whatever grouping makes sense for how you're working — rather than building
the whole file up as a block of text you plan to write out at the end. A
long run can end before you're done, for reasons outside your control; rows
already appended to the file on disk survive that, rows still sitting
unwritten in a heredoc or in your own reasoning don't. This is also just the
natural shape of working iteratively per the point above: finish a batch,
write it, move to the next one, come back and revise a row later if needed —
the file is the running state, not a one-time export at the very end.

## Step 0: scope to projects that are actually active

There's also an activity file — a plain list of project identifiers with
usage in roughly the last year, one per line, no header (ask the user for
its current path if you don't already have one, same as `mapping_all.csv`).
**Only generate a proposal for a project if it appears in both
`mapping_all.csv` and this activity file.** A project can be in
`mapping_all.csv` without being in this file, or vice versa — that means
either it's dormant (present in the crosswalk but nobody's actually running
jobs under it) or new (active but not yet in the crosswalk). Neither is
worth spending a description-writing effort, a `url` fetch, or a web search
on: proposing rich metadata for a project nobody's using is wasted work for
the reviewer to wade through, and this file is how you find out which is
which before you start.

The two files don't use consistent naming for the same project — this
activity file mixes bare `accounting_group`-style names (`Anthropology_Hawks`)
with full `project_name`-style ones (`UWMadison_ISyE_Cha`), and neither file
is consistent about a `UWMadison_` prefix, spacing, or case. Match the same
way you'd match against topology filenames: normalize (strip whitespace/
punctuation, lowercase) before comparing, on both `accounting_group` and
`project_name` from `mapping_all.csv`, rather than expecting exact string
equality.

## Step 1: see what's already there

Before proposing anything, pull the current state of the projects you're
working on from the dev database (covered in
[references/schema.md](references/schema.md)). Some rows may already have
one or more of these fields set. Never propose silently overwriting a
non-null value — if a field is already populated, either skip it (the
common case, needs no comment) or note why you think it should change
anyway (the exception, and the only case worth a comment).

**`url` is the one field where "already populated" isn't the end of the
check.** A non-null `url` can still be dead — the page 404s, the domain's
gone, the link rotted. A dead link carries exactly as little information as
a blank one, so treat it the same way: eligible for a `proposed_url`, not
something to skip past just because the column isn't empty. Check it before
deciding (fetch it; a single failure isn't proof it's dead — see the retry
guidance in [references/data-sources.md](references/data-sources.md)), and
if it's genuinely broken, that's worth a short `note` ("existing url is
dead") since you're proposing a change to a field that looked populated. A
`url` that's set and working is like any other good value — leave it alone,
don't propose a "better" one just because you found an alternative.

**If the DB is genuinely unreachable**, this is the "if something you need
is blocked, stop" case from earlier — stop and ask rather than generating
proposals you can't vouch for, since there's no way to know whether a value
would overwrite something already good. Don't suggest an API-based
workaround; there isn't one. The local reference CSVs
(`alembic/data/colleges_and_departments.csv`,
`alembic/data/fields_of_science.csv`) still work without DB access if you
get the go-ahead to continue anyway — only the "what's already there" check
is actually blocked.

## Step 2: gather evidence, source by source

Work through these roughly in order — but "roughly" is doing real work in
that sentence, so read the caveats before leaning on any of them. Full
detail on all of them, including known data-quality issues to watch for, is
in [references/data-sources.md](references/data-sources.md).

1. **The OSG topology registry** (`github.com/opensciencegrid/topology`,
   `projects/*.yaml`) — when a project has a confident match here, this is
   your best source: real prose descriptions written by the project's own
   registrant, and a `FieldOfScienceID` that turns out to use the *exact same*
   code scheme as our `fields_of_science.fos_id` — i.e. a precise, human-picked
   answer rather than a guess. The catch: it only covers a small fraction of
   our projects, and filenames alone produce false-positive matches across
   institutions (a name that looks right can belong to a different school
   entirely). Always confirm the YAML's `Organization` field before trusting
   a match. This is a one-time repo clone, not a per-project network call, so
   it's cheap to check for every project. Some entries' `Description` is
   itself nothing but a bare URL rather than prose — when that's what you
   get, it's not a description source, it's a `proposed_url` candidate; check
   it's live the same as any other url before using it.

2. **`mapping_all.csv`** (a preliminary hand-built crosswalk, ask the user for
   its current location if you don't already have a path) — decent coverage
   for `Department`/`College` once you account for naming-convention drift
   between the file and the reference table, weak for `fos_id` since its
   `Domain`/`NSFDomain` columns don't key cleanly into the fields-of-science
   taxonomy. Treat it as a strong hint for the college/department pair and
   only a rough hint for field of science. Also cheap — it's a local file
   lookup, not a network call.

3. **The project's own `url` field, if set** — fetch it rather than treating
   it as inert metadata. It's often a lab or PI homepage and can be a real
   source of prose for `description`, the same way a topology match would
   be. This is one targeted fetch of a link you already have, which is a lot
   cheaper than an open-ended search, so it's worth doing whenever `url` is
   set and the sources above didn't already give you a description.

4. **Structured fields already in the DB** — project `name`, PI (and
   staff) names via the `users` table, `accounting_group`, existing
   `status`. If nothing above gave you a real description, this is enough
   for an honest, if generic, `display_name` and `description` — e.g. turning
   `AnimalSciencesGianola` + PI `Daniel Gianola` + department `Animal and
   Dairy Sciences` into something readable. This is a perfectly fine place to
   stop for most rows; a generic-but-true description doesn't need "fixing"
   with a search just because it's plain.

5. **General web search — last resort, only if there's nothing else.**
   Internet searches are the slowest and most expensive step here, and
   you'll typically be running this over hundreds or thousands of projects,
   so don't reach for it by default. Only consider it for a project where
   every source above came up empty *and* it clearly looks like a real,
   ongoing research project (not a test/service/course account) where a
   generic structured-fields description would be a real loss of
   information. Even then, it's optional, not required — accepting the
   generic baseline description is always an acceptable outcome. See
   [references/data-sources.md](references/data-sources.md) for how to keep
   a search from landing on the wrong person or project. If this turns up a
   page you're confident is genuinely the project's own (a lab site, a PI's
   faculty page — the same identity bar as everywhere else in this list),
   that's also a `proposed_url` candidate, not just a description source.

Do not invent research focus, findings, funding, or lab specifics that
aren't present in whatever source you used — a plain, honest description
beats a specific-sounding fabricated one every time, regardless of which
step produced it. If you genuinely have nothing to go on beyond the project
name, say so in `note` rather than reaching for something that sounds
plausible.

Nothing stops you from combining sources for a single project (e.g. topology
gives you a description but not a clean department match) — that's normal
and doesn't need calling out on its own.

## Step 3: output

If `proposed_description` (or `proposed_display_name`) names the college,
department, or any other entity you already resolved elsewhere in the same
row, use the exact name your lookup returned — not a name recalled from
general knowledge. Institution names drift (reorgs, rebrands, mergers), and
what you remember about an org's name can be a year or a decade stale even
when everything else you're saying about it is right. You already did the
authoritative lookup for `proposed_college_and_department_id`; reuse its
result instead of re-deriving the name from memory a second time.

**The deliverable is a CSV file, not a chat reply.** Write one row per
project to an actual `.csv` file with this exact header:

```
project_id, name, proposed_display_name, proposed_description, proposed_url,
proposed_college_and_department_id, proposed_college_and_department_name,
proposed_fos_id, proposed_fos_name, note
```

Quote fields that contain a comma (most `proposed_description` values will)
per standard CSV escaping, so the file opens cleanly in a spreadsheet or
`csv.DictReader` without special-casing. Don't substitute a markdown table
or a summary in the response — that's fine as a short spoken recap, but the
proposal itself belongs in the file.

**`proposed_url` follows the same source priority every other free-text
field does, roughly in the order Step 2 lists them: keep an existing url if
it's live; otherwise a bare-URL topology `Description` beats a page you had
to go searching for.** Leave it blank rather than filling it with something
low-confidence — an empty `proposed_url` costs nothing, a wrong one sends a
reviewer to the wrong page. Whatever you propose, you should have actually
fetched it and confirmed it resolves to something real and relevant; don't
propose a url you found written down somewhere but never checked.

**This column has the same "only the literal value" rule as the id
columns, and it's just as easy to violate without noticing.** It must be a
properly formatted link, starting `http://` or `https://`, and nothing
else — no description of the page, no "the group's site," no explanation of
how you found it, even when that explanation is accurate. If you can't
paste the exact string into a browser's address bar and land on the page,
it doesn't belong in this column. Anything you'd want to say about the url
goes in `note`, same as with the ids.

`proposed_college_and_department_id` and `proposed_fos_id` contain **only**
the literal value that would be written into that column — the bare `id`
integer, the bare `fos_id` code — and nothing else. No inline commentary, no
" — because...", no explanation of how you got there, even a short one, even
if it's correct and you're proud of the reasoning. Anything you want to say
about a value goes in `note`, never appended to the id itself: these two
columns need to be machine-usable as-is, and a string like `4 — matches
Biochemistry` cannot be written into an integer column. If you're not sure
which row is correct, put the id you're leaning toward (or leave it
blank/null) and explain the uncertainty in `note` — the id cell itself stays
clean either way. Same for a placeholder like "best fit — verify" — that's
not a value at all, it's prose sitting where a value should be.

**`proposed_college_and_department_name` and `proposed_fos_name` exist to
force a real lookup, not to give you a second place to summarize.** Once you
land on an id/code — from whichever source — go back to the actual
reference table and copy what it says for that exact row: `college` +
`department` for the first, `sed_cip_title` for the second. Don't write what
you think the name is, or what a source called it; write what the table
itself returns for that id. This makes a bad id self-revealing: if the id
doesn't actually exist, the lookup comes back empty, and that's your signal
to stop and pick a different one rather than carry a guess forward. (This is
exactly the gap that let an invalid topology `fos_id` — `40.08`, not a real
row — slip through in an earlier batch; an id and a name pulled from the
same lookup wouldn't have let that happen silently.)

This works in either direction, and the rule is the same either way. Some
rows you'll resolve id-first (you know the department, look up its id, then
pull the name back to confirm). Others you might start from the text — you
recognize a department or field of science by name and want its id — in
which case look the name up in the table to get the id, and the `_name`
column is just that same confirmed text, not a re-typing of what you
started from. Either way, the id and the name in a row must come from the
same real table row: never pair a looked-up id with a name you made up, or
a name that sounds right with an id you're only guessing at.

`note` is the one place to spend extra tokens, and it's optional — **only
fill it in if the row needs attention.** Leave it empty for the ordinary
case where a source gave you a clean, confident answer; that's most rows.
Fill it in when there's something a reviewer genuinely needs to know before
applying the row, e.g.:
- you had nothing to go on and are proposing null/skip rather than a guess
- two sources disagreed and you picked one
- you're only confident in some of the five fields for this row, not all of them
- a field was already populated and you're proposing a change to it anyway

Before writing anything in `note`, check whether it's actually telling the
reviewer something new. `proposed_display_name` and `proposed_description`
already say what kind of project this is — a lab, a course section, a core
facility, a staff account — so restating that classification in `note`
teaches the reviewer nothing they didn't just read two columns over. A note
earns its place only if it wouldn't be obvious from reading the rest of the
row: a disagreement between sources, a reason a value might be wrong, a
project elsewhere in the DB this one relates to. If you can point at another
column and say "the answer's right there," leave `note` empty.

Think of it as an exception report, not a running commentary — most rows
across a large batch should have an empty `note`. That's what keeps this
usable at the scale you're actually running it at (hundreds to thousands of
projects), rather than paying for a paragraph of justification per row.

Six real, worked examples — a topology match, a `mapping_all.csv`-only
match, a project filled in from its own `url` and a search, two projects
with none of the above where a well-known name makes web search worth it
for one but not the other, and one built specifically around `proposed_url`
(a dead existing link, a topology entry whose only contribution is a bare
url) — are in [references/examples.md](references/examples.md). Read these
before your first batch if anything above feels abstract; they show how the
quality of your evidence should visibly shape both the description you
write and whether the row needs a `note` at all.

## When you're done

Hand back the CSV file (say where you saved it). That's the deliverable.
Applying it is a separate, explicit action the human takes after reviewing
your work — not something this skill does for them, and not something this
skill needs to know how to do.
