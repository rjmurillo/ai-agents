---
paths:
  - ".project-toolkit/architecture/**"
priority: high
---

# ADR Record Rules

Conventions for authoring a record under `.project-toolkit/architecture/`. The generated
index reads these files mechanically, so a record can be correct prose and still
render wrong in the index.

## MUST

1. **The first sentence of `## Status` MUST stand alone.** The generated ADR
   index strips a leading bare status token from that paragraph before rendering
   it as the Proposed table's blocker cell. The stripper is
   `build/scripts/generate_adr_index.py:161`:

   ```python
   _LEADING_PROPOSED_RE = re.compile(r"^Proposed\b[ \t]*[.:-]?[ \t]*", re.IGNORECASE)
   ```

   applied by `_blocking_condition` at
   `build/scripts/generate_adr_index.py:503-514` to the first paragraph of the
   `## Status` section. It consumes the word plus at most one trailing `.`,
   `:` or `-`. It does not consume a comma, so a record opening
   `Proposed, and concluded without consensus.` renders in the index as
   `, and concluded without consensus.`

   Write a status paragraph whose first sentence carries its own subject:
   `Proposed. The panel concluded without consensus.` renders as
   `The panel concluded without consensus.`

   The strip is deliberate and tested, not a defect to fix in the generator:
   `tests/build_scripts/test_generate_adr_index.py:195` is
   `test_proposed_blocker_drops_the_redundant_status_token`, which asserts
   `"Proposed." not in proposed_row`. The section heading already carries the
   status, so repeating it in the cell is noise. The obligation is on the author.

   Evidence: this fired twice in one session while settling ADR-101 (PR #5677).
   ADR-072's debate log had already recorded the same trap, which is why the
   convention belongs in a rule the loader reads by `paths:` rather than in a
   critique artifact nobody opens while drafting.

2. **Create or amend a record through the `adr-generator` skill, before the
   first write.** This covers a new ADR, an amendment, and a superseding
   record. It applies when a plan step needs an ADR and nobody said
   "ADR". Copying a sibling record's format by hand skips the skill's numbering,
   frontmatter defaults (ADR-073), quality checklist, and index refresh. Two edits
   belong to `adr-review` instead: applying findings inside an open debate
   round, and setting status when a review closes.

   Evidence: on 2026-11-19 a session drafted ADR-123 by hand after reading
   ADR-122 for its format. `adr-generator` was never invoked. A scan that day
   of 22,812 Claude, Codex, and Copilot session files found 67 sessions that
   created or edited an ADR. Only 3 invoked `adr-generator` before the first
   write.

## References

- `build/scripts/generate_adr_index.py`. Renders the index; owns the strip.
- `tests/build_scripts/test_generate_adr_index.py`. Pins the strip's behavior.
- `.project-toolkit/architecture/README.md`. The generated index itself.
