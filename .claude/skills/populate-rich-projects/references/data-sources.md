# Data sources: coverage and known issues

## 1. OSG topology registry — `github.com/opensciencegrid/topology`

`projects/*.yaml`, one file per OSG-registered project across *all*
participating institutions (not CHTC-specific). You can clone it directly:

```bash
git clone --depth 1 https://github.com/opensciencegrid/topology.git
```

Each YAML looks like:

```yaml
Department: Astronomy
Description: 'Research interests: High energy astrophysics and the astrophysical
  application of computational fluid mechanics...'
FieldOfScience: Astronomy and Astrophysics
FieldOfScienceID: '40.0201'
Organization: "University of Wisconsin–Madison"
PIName: Sebastian Heinz
InstitutionID: 'https://osg-htc.org/iid/fq8thqsj99zh'
```

**Why it's valuable:** `FieldOfScienceID` uses the *exact same* CIP-code
scheme as our `fields_of_science.fos_id` — codes like `26.1104`, `11.0701`,
`30.3001`, `40.0201` exist verbatim in both, with matching titles. That's a
precise, human-chosen `fos_id`, not a guess. `Description` is genuine prose
in the large majority of matched cases (only a small minority are just a bare
URL, and essentially none are empty) — a much better source than anything
you'd generate from scratch.

**Coverage and pitfalls:**
- Only ~172 of ~1,589 total topology projects are tagged
  `Organization: University of Wisconsin–Madison`, and of those, only around
  half match something in the CHTC user app by name. Topology only covers
  projects that registered for national OSG resource access — most
  CHTC-local-only projects simply won't be here. Don't be surprised when a
  project has no match; that's the expected case, not a bug in your search.
- **Match on the project's `name` (or `accounting_group`) against the YAML
  filename, normalizing case/punctuation** — but a filename match is not
  enough on its own. Cross-institution name collisions happen (e.g. a file
  that looks like it's ours actually belongs to a different UW System
  campus, like Eau Claire or La Crosse, not Madison). **Always check the
  `Organization` field says University of Wisconsin–Madison before trusting
  a match.**
- **An exact normalized match will miss real matches, because our naming and
  topology's naming aren't built the same way.** Our names are typically
  `<Department>_<Surname>`; topology's are often `<Institution>_<Surname>` or
  just `<Surname>` — different prefix, same person. A project literally named
  `Pathology_OConnor` in our system has been missed this way against
  topology's `UWMadison_OConnor.yaml`, even though it's the same PI and the
  same project. If the exact match fails, try again on just the trailing
  token after the last `_` (usually the PI's surname) before concluding
  there's no match — a false negative here silently downgrades a project
  from "topology match" to "generate from scratch," which is a real loss of
  a good source, not a neutral outcome.
- Even among confirmed UW–Madison matches, `Department` only agrees with our
  own department string exactly ~60% of the time — mostly harmless
  formatting drift (`"Electrical and Computer Engineering"` vs `"Electrical &
  Computer Engineering"`, a `"Department of "` prefix), but occasionally a
  genuinely different department than what our own records show for that
  project. Where they disagree substantively, that's worth a `note`, not
  silent acceptance of either value.

## 2. `mapping_all.csv`

A preliminary hand-built crosswalk with columns: `accounting_group`,
`project_name`, `Department`, `College`, `Domain`, `NSFDomain`, `Category`.
Ask the user for its current path if it's not already in front of you.

**Department/College → `college_and_departments`:**
- `Department` matches the reference table roughly 72% of the time after
  normalizing `&` → `and`.
- `College` almost never matches verbatim — the CSV uses informal short
  names (`"Letters and Sciences"`, `"Engineering"`, `"Medicine and Public
  Health"`, `"Business"`, `"Pharmacy"`, `"Veterinary Medicine"`,
  `"Education"`) where the reference table has official long forms
  (`"College of Letters & Science"`, `"College of Engineering"`, `"School of
  Medicine and Public Health"`, `"Wisconsin School of Business"`, etc.). A
  small alias table for ~9 colleges closes most of this gap.
- Known reorg drift the CSV doesn't reflect: **Computer Sciences, Statistics,
  and Public Affairs are listed under `College = Letters and Sciences` in
  the CSV, but the reference table already has them under the newer
  `College of Computing & Artificial Intelligence (CAI)` / `La Follette
  School of Public Affairs`.** Trust `Department` over `College` when they
  disagree for these.
- A meaningful chunk of rows are legitimately non-academic
  (`Off-Campus`, `other`/`Other`, `Universities of Wisconsin`, `CHTC`, `OSG`,
  `DoIT`, `Morgridge Institute for Research`, and various VCRGE-affiliated
  centers like Waisman, WEMPEC, Space Science & Engineering Center). These
  have no real row in `college_and_departments` and shouldn't be forced into
  one — a null `college_and_department_id` is the honest answer for them.
- Some department names are simply stale/renamed relative to the current
  official list (`Botany`/`Integrative Biology` → now `Biology`,
  `Genomics & Genetics` → `Genetics`, `Forestry & Wildlife Ecology` →
  `Forest and Wildlife Ecology`, `Soil Science` → `Soil and Environmental
  Sciences`, `Engineering Physics`/`Nuclear Engineering` → merged into
  `Nuclear Engineering and Engineering Physics`). A couple of departments in
  the CSV (Law, Geological Engineering) don't appear in the reference table
  at all.

**Domain/NSFDomain → `fields_of_science`:** much weaker. Of the CSV's 16
distinct `NSFDomain` values, only 6 match `fields_of_science`'s
`broad_field`/`major_field` vocabulary exactly (`Chemistry`, `Physics`,
`Economics`, `Mathematics`, `Education`, `Engineering`, `Social Sciences`).
The rest (`Health`, `Earth and Ocean Sciences`, `Atmospheric Sciences`,
`Computer Sciences`, `Astronomy`, `Other Social Sciences`, `Biological
Sciences`, `Business management/administration`) are close in spirit but
don't match the reference strings, and even a fuzzy crosswalk only gets you
to a `broad_field`/`major_field` *bucket* — `fields_of_science` has 1,651
rows at CIP-code granularity, so "Physics" alone doesn't tell you which
specific `fos_id` row to pick without more information than this file
provides. Treat this column as a coarse hint for building your own
bucket-level crosswalk, not a direct join key.

**Known data-entry issues to watch for**, in case they recur elsewhere in
the file: a `"Physical Sciencs"` typo (missing the 'e') on a couple of
`Physics` rows, and at least one row (`lhcb`, the LHCb particle-physics
experiment) tagged `NSFDomain = Mathematics` when everything else about it
says particle physics. Don't assume every value in this file is correct just
because it's structured data — spot-check department fields.

## 3. The project's own `url` field

Fetch it before falling back to generating a description from scratch. It's
frequently a PI or lab homepage, and reading it gives you real prose to draw
a `description` from — the same kind of gain a topology match would give
you, not just background context. Treat it like any other web source: it
can be out of date, wrong, or not really about the project at all (some are
just a department homepage or an old grant page), so use your judgment about
how much to trust what you find there rather than lifting it wholesale.

**Don't conclude a `url` is dead from one failed fetch.** A timeout or a
transient error looks identical to a genuinely gone page, and treating
either as "no source, move on" has already cost a real, live, useful
description in one batch — the url worked fine, the first check just
wrongly wrote it off. Retry once before deciding it's actually unreachable.
If it's still failing after that, that's a fine place to stop and fall
through to the next source — but say so in `note` ("url unreachable after
retry") rather than silently treating the row as if the url had never been
set; a reviewer who knows the project has a working link on record can
catch what an automatic retry couldn't.

This same fetch is also *the* check for whether `url` itself needs a
`proposed_url` (see SKILL.md Step 1) — a dead existing link isn't just a
missed description source, it's a field that needs replacing. If it's dead
after a retry and nothing later in this list turns up a live replacement,
leave `proposed_url` blank and say so in `note`; a blank is honest, a guess
isn't.

## 4. Baseline: structured fields already in the DB

If nothing above gave you a usable description, you still have whatever the
DB provides: project `name`, PI (and staff) names via the `users` table,
`accounting_group`, existing `status`. That's enough for an honest, if
generic, `display_name` and `description` — e.g. turning
`AnimalSciencesGianola` + PI `Daniel Gianola` + department `Animal and Dairy
Sciences` into something readable. It is *not* enough to say anything about
what the research actually investigates, what it's funded by, or what it has
found — don't let a plausible-sounding sentence sneak in that isn't grounded
in your input. If a project's `name` is genuinely opaque (a course code, a
one-off test account, a service account) and you have nothing else to go on,
say that plainly in `note` rather than inventing a purpose for it.

## 5. General web search — last resort

This is the expensive one. Every source above is either a one-time local
lookup (topology clone, `mapping_all.csv`) or a single targeted fetch of a
link you already have (`url`); an open-ended search is neither — it can take
several round-trips per project, and you'll typically be running this over
hundreds or thousands of projects at once. Reach for it only when a project
has come up empty everywhere else *and* it's clearly a real, ongoing
research project where the generic baseline description would be a real
loss of information — not as a routine step for every unresolved row.
Accepting the baseline description instead is always a fine outcome; a
search is an upgrade you choose to pay for, not a requirement.

When you do use it, be more careful than with a project's own `url`, since
you're the one choosing what to trust: search for the PI together with the
department and/or "University of Wisconsin–Madison", not the PI name alone —
common names collide, and it's easy to land on a page about a different
person or a similarly-named project at another institution entirely. If
nothing you find is clearly about *this* project's PI at UW–Madison, don't
use it — fall back to the baseline description rather than forcing a result.

The same identity bar applies if you're considering the page itself as a
`proposed_url`: it has to clear the same confidence threshold that lets you
use it for `description` at all. A page you weren't sure enough about to
draw a description from isn't suddenly safe to hand a reviewer as the
project's link.
