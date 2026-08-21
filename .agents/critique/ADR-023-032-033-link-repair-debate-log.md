# Debate Log: ADR-023, ADR-032, ADR-033 Link Repairs

Change-set CS-3b of the corpus-repair batch. Batch-level record at
`.agents/critique/ADR-corpus-repair-5189-5201-debate-log.md`.

## Scope

Citation repairs only. No lifecycle state changes, no frontmatter added, no
decision altered in any of the three records.

## What was repaired

**ADR-033 pointed readers at the wrong decision, in nine places.** The issue that
opened this work (#5197) described one broken link. It was nine sites: the link
at line 107 to a nonexistent `ADR-032-exit-code-standardization.md`, four prose
references at 107, 111, 123 and 131 all meaning the exit-code contract, a mermaid
node `ADR032Exit` with its edge and style lines at 434, and two notes at 457 and
514 asserting "ADR-032 number reserved for Exit Code Standardization (PR #557)",
a reservation that never held. All now name ADR-035.

Lines 29, 31, 33 and 275 were deliberately left alone. They describe "the
original ADR-032 (Skill Phase Gates)", a rejected proposal that genuinely carried
that number. Rewriting them would falsify history.

**ADR-032 carried two stale slugs**: `ADR-005-powershell-only.md` and
`ADR-017-memory-index-architecture.md`, both from unpropagated renames.

**ADR-023's debate log was not missing.** The link was broken by a leading slash,
`/.agents/critique/...`, which GitHub resolves against the site root rather than
the blob tree. The file exists. Two sibling leading-slash links in the same block
had the same defect and were repaired with it.

## Root cause

The same class as CS-1's exception marker: a rename or a renumber that swept
filenames and not bodies. ADR-033's case is a numbering race rather than a
rename. It was authored 2025-12-31 04:02Z reserving ADR-032 for exit codes; the
EARS record claimed 032 sixty-two seconds later at 04:03Z. Exit codes landed at
ADR-035 and nothing updated ADR-033.

`check_adr_uniqueness.py` enforces numeric uniqueness going forward only. Nothing
checked that a prose citation naming "ADR-032" matched what ADR-032 actually is.

## Corrections to the issue that opened this work

Two findings in #5197 were the issue author's and were wrong. Both are recorded
so the corpus does not inherit them.

1. **The reported malformed nested-bracket ADR-080 links do not exist.** All
   eleven links across the three named files are well-formed and all eleven
   targets resolve. The defect was in the audit regex, which began matching at
   the opening paren of a surrounding prose parenthetical and ran through the
   `](`, producing an artifact shaped like a broken link.
2. **Two of three "missing" debate logs exist.** ADR-023's was the leading-slash
   defect above; both ADR-045 artifacts resolve. Only ADR-021's is genuinely
   absent.

## Open, deferred to the owner

ADR-021 cites `ADR-019-debate-log.md`. `git log --all` shows no commit ever
created that file under either number, so this is not a deletion to restore.
ADR-021 describes its debate as "Sessions 86 to 90, 5 Accept plus 1
Disagree-and-Commit", but sessions 86 to 90 in `.agents/archive/sessions/` are
the ADR-017 debate, and `ADR-017-debate-log.md` records a different shape. The
reference was left in place rather than deleted or invented. The owner picks:
locate and commit the artifact, or replace the citation with prose stating the
review evidence is not archived.

## One line outside the repair, disclosed

`ADR-032-ears-requirements-syntax.md:121` carried a pre-existing em-dash.
`checks_dash.py::validate_dash_prohibition` scans whole files changed on the
branch, not changed lines, so a link edit to that file would have turned the gate
red on a byte nobody in this campaign wrote. Rewritten as a colon.

## Verdicts

ACCEPT from architect, security, analyst and the tie-breaker. The
independent-thinker recorded these as "mechanical and correct". The critic's P1
stands and is not resolved here: ADR-023 was opened for repair and left without
frontmatter, so it remains in the `id-matches-filename` and
`status-section-present` violation sets. That is scope discipline, not an
oversight, and it is named so the backfill picks it up.
