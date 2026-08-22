# Owner Direction: Status Prose That Restates Frontmatter

**On this file's name.** Called a debate log because
`git_hook_policy._is_debate_log_path` requires the substring `debate` in the
filename before it accepts an artifact as ADR-change evidence. No agent debate
happened; the repository owner decided. Issue #5205 covers the fact that the gate
reads a filename pattern rather than a review.

## Governing evidence

Two inline review comments from @rjmurillo on PR #5209:

- `.agents/architecture/ADR-005-powershell-only-scripting.md` line 16: "Duplicative. Already in frontmatter"
- `.agents/architecture/ADR-024-github-actions-runner-selection.md` line 16: "Redundant"

## The principle, stated once

Prose says what frontmatter cannot. It never restates what frontmatter carries.

## What I got wrong in between

Answering the first comment I claimed the other four records were exempt because
their prose "carries what the enum cannot," and listed ADR-024's
acceptance-as-ADR-014 provenance as the reason. That provenance is on **line 18**.
Line 16, the line he flagged, was a restatement of the enum followed by me
narrating my own edit: "ADR-055 recorded the supersession in its own accepted
prose before this change ... and now carries `supersedes: [...]` in frontmatter."

That is pull-request commentary. It belongs in a PR body, not in a decision
record. The second comment was needed because my first answer defended the whole
section instead of reading the line.

## What changed

Every Status section this campaign wrote opened by restating the enum and then
narrating the frontmatter. The restatement is removed; the content frontmatter
cannot carry is kept and moved under a heading that names it.

| Record | Removed | Kept, under |
|---|---|---|
| ADR-024 | "Superseded by ADR-055 ... now carries `supersedes:` in frontmatter" | `## Provenance`: acceptance as ADR-014, the PR #476 renumbering, the duplicate-slug note, the retired marker |
| ADR-025 | the identical sentence | `## Provenance`: measured ARM adoption behind the supersession |
| ADR-055 | "Accepted (2025-12-29). Supersedes ADR-024 and ADR-025, both now marked ..." | `## Provenance`: duplicate-slug analysis, exception-marker decision, the PR #1604 rename |
| ADR-042 | "Accepted (2026-01-17, PR #963)." | `## Acceptance Evidence`: the debate-log path and four supporting artifacts |

## Why the sections were renamed rather than trimmed

`prose-frontmatter-agree` requires a `## Status` section to **open** with the
enum word. Keeping the heading and deleting the restatement would trip it. The
check therefore mandates the restatement it is meant to police, for any record
whose status prose would otherwise lead with something else.

Renaming resolves it honestly: a section holding provenance is called Provenance.
Frontmatter holds status, so no Status section is owed, and none is claimed.

## The bug this surfaced

Removing the top Status sections exposed a defect in the gate. It searched the
whole document for a status marker and took the first hit anywhere, so it read:

- ADR-042 `### Status` at line 171, a subsection of a migration phase
- ADR-055 `**Status**: COMPLETE` at line 119, a phase result
- ADR-055 `**Status**: APPROVED` at line 168, an exception ruling

as those records' lifecycle status. All three were masked while a redundant
Status section sat higher in the file. The gate shipped green and only a content
change revealed it.

It is the same defect this campaign filed as issue #5189 against
`_get_adr_status`, which regexed `^status:` across an entire ADR rather than its
frontmatter. The fix is the same: bound the search to the region that can hold
the answer. Committed alongside this change with two negative controls built
from the records that broke.

## Verification

`prose-frontmatter-agree` returns to 1, its baseline, and that one is ADR-068,
pre-existing and untouched here. Lifecycle total holds at 71. 89 tests pass.

## Corrections from a later Copilot review round on PR #5209

Two more factual defects in the records this log covers, both found by
automated review, neither a governance decision:

**ADR-024's Provenance line conflated pull request numbers with commit
identifiers.** It read "Accepted 2025-12-23 as ADR-014 in PR #224 (commit PR
#224). Renumbered to ADR-024 by PR #476 (commit PR #476)." Both parentheticals
are wrong: #224 and #476 are pull request numbers, not commits. Removed the
parentheticals; the PR numbers alone are unambiguous.

**ADR-055's `implemented: false` conflated "fully compliant" with "acted on".**
ADR-073's own schema comment defines the field as flipping "at first merged
change", and this decision's Metrics section already recorded 111 of 132
`runs-on` declarations migrated to ARM, well past that bar. Set to `true`; the
remaining 21-job compliance gap (documented in the same Metrics section and in
issue #5199) is a completeness question, not a reason to say the decision
was never acted on.

Neither correction changes a lifecycle status, a supersession, or an
acceptance. Recorded here rather than in a new log because both are factual
fixes to records this log already covers, and appending keeps the audit trail
in one place instead of scattering it across a fifth file for a one-line
fix each.
