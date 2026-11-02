# Worked examples

Six real projects, showing how the evidence you find actually turns into a
proposal row — not just a mechanical reformat of whatever you were handed.
Shown here as tables for readability; the real output is one CSV row per
project, per [SKILL.md](../SKILL.md)'s Step 3.

## Example 1: topology match

Topology's `projects/Biochemistry_Raman.yaml` (confirmed `Organization:
University of Wisconsin–Madison`):

```yaml
Department: Biochemistry
Description: 'The Raman laboratory takes a systems and synthetic biology approach
  to understanding and designing different biological systems: biomolecules,
  regulatory pathways, and organisms. We are interested in understanding and
  designing allosteric proteins, synthetic bacteriophages with new host range
  and regulation, and developing high-throughput functional assays to predict
  the effect of variants in disease-relevant genes.'
FieldOfScience: Biochemistry
FieldOfScienceID: '26.0202'
PIName: Vatsan Raman
```

`mapping_all.csv` independently has this project under `Department:
Biochemistry, College: Agricultural and Life Sciences`, which agrees with
topology and resolves cleanly to `college_and_departments` (`Biochemistry`
under `College of Agricultural & Life Sciences`). Two independent sources
lining up like this is exactly what a high-confidence, no-`note` row looks
like.

| Column | Value |
|---|---|
| `name` | `Biochemistry_Raman` |
| `proposed_display_name` | Raman Laboratory |
| `proposed_description` | The Raman laboratory takes a systems and synthetic biology approach to understanding and designing different biological systems: biomolecules, regulatory pathways, and organisms. The lab is interested in designing allosteric proteins and synthetic bacteriophages, and in developing high-throughput functional assays to predict the effect of variants in disease-relevant genes. |
| `proposed_url` | *(empty — topology's `Description` here is prose, not a link, and no other source was needed)* |
| `proposed_college_and_department_id` | `4` |
| `proposed_college_and_department_name` | College of Agricultural & Life Sciences — Biochemistry |
| `proposed_fos_id` | `26.0202` |
| `proposed_fos_name` | Biochemistry |
| `note` | *(empty)* |

## Example 2: `mapping_all.csv` match, no topology entry

`mapping_all.csv` row 646: `accounting_group: AnimalSciences_Gianola,
project_name: AnimalSciencesGianola, Department: Animal & Dairy Sciences,
College: Agricultural and Life Sciences, Domain: Life Sciences, NSFDomain:
Biological Sciences`. No file in the topology repo matches this project —
plenty of CHTC-local projects simply never registered there, and that's the
common case, not an error.

`Department` normalizes cleanly to `Animal and Dairy Sciences` under
`College of Agricultural & Life Sciences`, which is row 2 in
`colleges_and_departments.csv` — and since that table's `id` is assigned by
CSV row order at seed time (see [schema.md](schema.md)), `2` is the actual
`college_and_department_id`, not a description of one. `NSFDomain:
Biological Sciences` is too coarse to trust on its own here (see
[data-sources.md](data-sources.md)), but the department name itself gives a
better answer than the CSV column does: `fields_of_science` has an exact row
for `Animal Sciences, General` (`01.0901`) under the Agricultural sciences
broad field, which fits an Animal & Dairy Sciences project better than the
generic biology bucket the CSV hint would have pointed to. With no prose
source anywhere, the description falls back to what's actually known: the
project name and department.

| Column | Value |
|---|---|
| `name` | `AnimalSciencesGianola` |
| `proposed_display_name` | Gianola Lab |
| `proposed_description` | Research project in the Department of Animal and Dairy Sciences. |
| `proposed_url` | *(empty — nothing found worth proposing)* |
| `proposed_college_and_department_id` | `2` |
| `proposed_college_and_department_name` | College of Agricultural & Life Sciences — Animal and Dairy Sciences |
| `proposed_fos_id` | `01.0901` |
| `proposed_fos_name` | Animal Sciences, General |
| `note` | fos_id from department name, no source |

## Example 3: no topology entry, filled in from the `url` field and a search

`mapping_all.csv` has `Physics_Saffman` under `Department: Physics, College:
Letters and Sciences`, resolving to `College of Letters & Science, Physics`.
The project's own `url` field is already set and live — fetched per source
3, it points to a group homepage describing work on trapped,
individually-controlled neutral
(Rydberg) atoms for quantum computing and quantum information — a search on
the PI's name alongside the department corroborates the same focus area
rather than turning up someone else. That's specific enough to place this in
`fields_of_science` at the detailed level, not just the broad "Physics"
bucket the CSV's `NSFDomain` alone would have given: `40.0802`, Atomic/
Molecular Physics, fits the actual research a lot better than a generic
Physics catch-all. If the fetch had failed on the first try, the move isn't
to write the url off — retry once, per [data-sources.md](data-sources.md);
only after a retry still fails does this fall through to the next source,
and even then it's worth a `note` rather than silence, since a link that's
actually fine just had a bad moment is a different situation than a link
that's genuinely gone.

| Column | Value |
|---|---|
| `name` | `Physics_Saffman` |
| `proposed_display_name` | Saffman Group |
| `proposed_description` | Research group developing quantum computing and quantum information systems built on individually trapped and controlled neutral (Rydberg) atoms, including scalable qubit arrays and atom-based quantum logic gates. |
| `proposed_url` | *(empty — the existing url already works; a working link doesn't get replaced just because you found it useful)* |
| `proposed_college_and_department_id` | `70` |
| `proposed_college_and_department_name` | College of Letters & Science — Physics |
| `proposed_fos_id` | `40.0802` |
| `proposed_fos_name` | Atomic/ Molecular Physics |
| `note` | fos_id from web search, no source |

## Example 4: no topology, no `url`, but a name worth searching

`mapping_all.csv` has `cms` under `Department: Physics, College: Letters and
Sciences, Category: National Project` — no topology entry under this exact
project name (topology has plenty of `cms.org.<institution>.yaml` files for
individual sites' participation, but none named just `cms`), and no `url`
set. Unlike example 5 below, this name is instantly recognizable rather than
opaque: CMS is one of the two general-purpose detector experiments at the
LHC, a large, decades-running international collaboration — exactly the
kind of project where a search is worth the cost. A search on the project
name alongside the department turns up UW–Madison's own CMS physics group
page, confirming this isn't a false hit on an unrelated "CMS" and giving a
real basis for the description instead of a generic template — and since
there's no existing `url` to protect, and this page is clearly the group's
own (not just a page that mentions them), it's also a reasonable
`proposed_url`.

That same search result is specific enough to place this at the detailed
level in `fields_of_science` — `40.0804`, Elementary Particle Physics —
rather than the general "Physics" row `NSFDomain: Physics` alone would have
pointed to.

| Column | Value |
|---|---|
| `name` | `cms` |
| `proposed_display_name` | CMS Experiment |
| `proposed_description` | UW–Madison's participation in the CMS experiment at CERN's Large Hadron Collider, one of the two general-purpose particle detectors that co-discovered the Higgs boson. |
| `proposed_url` | `https://hep.wisc.edu/cms` |
| `proposed_college_and_department_id` | `70` |
| `proposed_college_and_department_name` | College of Letters & Science — Physics |
| `proposed_fos_id` | `40.0804` |
| `proposed_fos_name` | Elementary Particle Physics |
| `note` | fos_id from web search, not source |

## Example 5: no topology, no `url`, nothing to search for

`mapping_all.csv` has `CS639_Spring2026_Sala` under `Department: Computer
Sciences, College: Letters and Sciences` — no topology entry, and no `url`
set on the project. This is a course project, not a lab: the name itself
(a course number plus a semester) says so, and unlike `cms` above, a web
search on an instructor teaching one semester of one course isn't going to
turn up something reliably about *this* project the way it would for an
established collaboration. This is the realistic common case for a large
share of any batch — not a failure of the process, just a project with
nothing beyond what's already structured.

`Department` still resolves cleanly (`Computer Sciences` → `College of
Computing & Artificial Intelligence (CAI)`, the same reorg-drift case as
example 2 in [data-sources.md](data-sources.md)), and `NSFDomain: Computer
Sciences` is close enough to `fields_of_science`'s `Computer science` major
field to use its general row. The description has nothing to draw on beyond
the project name and department, so it stays exactly that plain.

| Column | Value |
|---|---|
| `name` | `CS639_Spring2026_Sala` |
| `proposed_display_name` | CS 639 (Spring 2026) |
| `proposed_description` | Course project for CS 639, Spring 2026, in the Department of Computer Sciences. |
| `proposed_url` | *(empty — nothing to propose)* |
| `proposed_college_and_department_id` | `16` |
| `proposed_college_and_department_name` | College of Computing & Artificial Intelligence (CAI) — Computer Sciences |
| `proposed_fos_id` | `11.0701` |
| `proposed_fos_name` | Computer Science |
| `note` | description is name and department only, no source |

## Example 6: topology's only contribution is a `url`, and the existing one is dead

Topology's `projects/CHTC.yaml` (confirmed `Organization: University of
Wisconsin–Madison`):

```yaml
Department: CHTC
Description: http://chtc.cs.wisc.edu/
FieldOfScience: Computer Sciences
FieldOfScienceID: '30.3001'
PIName: Miron Livny
```

Not every topology entry gives you prose — here `Description` is nothing but
a bare URL. That's not a description source; per source 1, it's a
`proposed_url` candidate, and it checks out as live. This project's own
`url` field in the DB, whatever it currently holds, gets replaced by this if
it's blank *or* if it's set to something that no longer resolves — a dead
link isn't a reason to leave `proposed_url` empty, per Step 1; it's exactly
the case this field exists for.

`mapping_all.csv` lists this project's `Department` as `CHTC` and `College`
as `other` — neither is a real row in `college_and_departments`. `CHTC`
isn't an academic department; forcing it into one would be worse than
admitting there isn't a match. `proposed_college_and_department_id` is null
here, honestly, the same as the non-academic entries covered in
[data-sources.md](data-sources.md). `FieldOfScienceID` (`30.3001`) does
resolve to a real row, though, so that one's still usable even without a
department match. With no prose anywhere, `description` falls back to the
baseline: name, department, PI.

| Column | Value |
|---|---|
| `name` | `CHTC` |
| `proposed_display_name` | CHTC |
| `proposed_description` | The Center for High Throughput Computing (CHTC), led by Miron Livny. |
| `proposed_url` | `http://chtc.cs.wisc.edu/` |
| `proposed_college_and_department_id` | *(null)* |
| `proposed_college_and_department_name` | *(null — no real department to name)* |
| `proposed_fos_id` | `30.3001` |
| `proposed_fos_name` | Computational Science |
| `note` | no academic department match (CHTC isn't one); url replaces existing dead link |

Notice what changed across these six: the description gets more specific
exactly in proportion to how good your evidence is, and the `note` shows up
only where there's a real judgment call underneath the row — not as a
running commentary on every field. Examples 4 and 5 both have "nothing" from
topology/CSV/url, but they don't get the same treatment: one name is worth
the cost of a search, the other genuinely isn't. Example 5 isn't a worse job
than example 1, it's the correct output for a project that genuinely has
less to say. Example 6 shows a source contributing to only *some* fields
(here, just `url` and `fos_id`) — that's normal, not a partial failure.

