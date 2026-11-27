# The code quality gate penalized a refactor for sharing code and removing duplicate lines

**Atomicity**: 90%
**Category**: Code quality gate
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E071. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a drop in the code-quality score mean a consolidation refactor made the code worse?

## Conventional answer

The quality score rewards deduplication and shared helpers. A regression drop signals worse code.

## First-principles position

The coupling score is 10 minus the count of non-stdlib import statements. Each file that swapped its own parser for one shared import lost a full point. The non-redundancy ratio fell for one file even though its duplicated lines fell, because the file got shorter. The gate flagged changes to the counts, even though the refactor removed duplicate code.

## Evidence with limits

- On the frontmatter consolidation branch (head 0a101a596 against base a217e3a3d1, 2026-11-24), `assess.py` exited 10 with 74 regression rows.
- The final report counted 72 coupling rows. Of those, 70 lost a point for adding one `hook_utilities` import (2026-11-24).
- One non-redundancy row for `test_frontmatter.py` fell from 7.3 to 6.0 while duplicated lines fell from 56 to 33 (2026-11-24).
- The gate change shipped in PR 7535 and is recorded in the ADR-125 amendment.
- Limits: One branch, one day. Row counts are 74 total and 72 coupling in the final message, and 70 coupling in the earlier symptom text.
- State on main at 1be533c496 (2026-11-26): fixed. ADR-125:95-99 records 74 rows and the 56 to 33 drop with the 7.3 to 6.0 ratio score. Commit 8d7c067f1a admits shared-import and shorter-file score drops.

## Decision

Read a quality-score regression as a ratio or count artifact until the absolute quantity moved the wrong way. Count coupling as distinct modules and exclude stable shared modules.

## Related

- `.serena/memories/review/review-full-rerun-cost-and-ship-marker-amplifier.md`
