# ADR Debate Log: ADR-028 / ADR-031 / ADR-056 Status (Issue #5201)

Part 2 of 2. Part 1 (`issue-5201-adr-005-042-debate-log.md`) covers the
mechanical ADR-005/ADR-042 pair, reviewed in the same round; split into two
files only to fit each commit under the repository's 5-authored-file cap
(`.claude/rules/universal.md` MUST-6), not because the review ran separately.

## Summary

- **Rounds**: 1
- **Outcome**: Consensus (Disagree-and-Commit accepted after fixes applied)
- **Final Status**: ADR-031 `rejected`; ADR-028 `superseded` (by ADR-056);
  ADR-056 `accepted` (supersedes ADR-028)

## Context

ADR-031 (hybrid PowerShell performance architecture) sat at `Proposed`
indefinitely with no closure signal, even though its premise (ADR-005 as
primary scripting language) was removed by ADR-042. ADR-028 (PowerShell
output schema consistency) was `Accepted` with no scope note despite the
`.claude/skills/` PowerShell surface it named having since been removed.

## Phase 0: Related Work

ADR-073 (lifecycle frontmatter) defines the schema
(`id/status/date/decision-makers/supersedes/superseded-by/explainer/implemented`)
and enum. ADR-044 and ADR-095 are the prior records already using this schema,
used as format precedent.

## Phase 1-2: Independent Review (Round 1, initial diff)

Initial diff: frontmatter added to ADR-028 and ADR-031 only. ADR-028 was
initially marked `deprecated`, `superseded-by: null`, `implemented: false`.

### Agent Positions (Round 1, initial diff)

| Agent | Vote | Key finding |
|-------|------|-------------|
| security | Accept | No security-relevant surface; N/A. |
| high-level-advisor | Accept | Matches the issue's own prescribed options; cosmetic nit only (all `date` fields read today's date). |
| analyst | Accept | Independently confirmed zero `.ps1` files outside `.venv` via Glob; flagged (non-blocking) `implemented: false` on ADR-028 looked wrong given PR #235. |
| architect | Disagree-and-Commit | P1: ADR-028's `implemented: false` is factually wrong: ADR-073 defines `implemented` as "flips true at first merged change," and PR #235 (`Get-PRReviewComments.ps1`) merged under this pattern. Reciprocity and the rejected call for ADR-031 otherwise correct. |
| independent-thinker | Disagree-and-Commit | Verified `find` claim independently (0 results outside `.venv`). Two non-blocking reservations: (1) ADR-031 could additionally carry `superseded-by: ADR-042`; (2) ADR-028's schema-consistency principle deserved a follow-up on whether it survives for Python skill output rather than being left purely historical. |
| critic | **Block** | P0: ADR-028's `deprecated` status directly contradicts ADR-056 (`Accepted`, unedited at the time), which cites ADR-028 in present tense as a live, enforced dependency ("ADR-028 schema consistency is enforced at the envelope level," ADR-056 Consequences, backed by `scripts/github_core/output.py`). Deprecating the source of a principle ADR-056 still actively enforces reproduces the exact status-contradiction bug issue #5201 exists to fix. P1: `implemented: false` wrong (same finding as architect). P2: ADR-042's Related Decisions section doesn't forward-link ADR-031/ADR-028. |

## Phase 3: Resolution

The critic's P0 is correct and independently corroborated by the
independent-thinker's reservation #2 about the same file from a different
angle. Re-read ADR-056 in full: `Accepted`, dated 2026-03-08, unedited before
this round, and its Implementation Notes name `scripts/github_core/output.py`
(Python, per ADR-042) as the live home of the ADR-028 schema-consistency rule.
The rule did not retire when PowerShell left the repo; it re-platformed onto
the Python output envelope. "Deprecated" was the wrong terminal state.

Changes made:

1. **ADR-028**: `status: deprecated` -> `status: superseded`,
   `superseded-by: null` -> `superseded-by: ADR-056`. Rewrote the `## Status`
   prose to state the correction explicitly (a prior draft called this
   `deprecated`; that was wrong, per ADR-056's live citation) rather than
   silently editing history.
2. **ADR-028**: `implemented: false` -> `implemented: true` (architect P1 and
   critic P1, same finding: PR #235 shipped the pattern in production
   PowerShell code before the Python migration removed the surface).
3. **ADR-056**: added ADR-073 frontmatter (it had none) with
   `status: accepted`, `supersedes: [ADR-028]`, `implemented: true`, and a
   one-line `## Status` addition noting the supersession, making the link
   reciprocal and machine-readable in both directions.
4. **ADR-042** (committed in Part 1's commit): added a Related Decisions
   "Downstream" line naming ADR-031 (rejected, premise removed) and ADR-028
   (superseded by ADR-056), closing critic P2.
5. **ADR-031**: left as `rejected` with `superseded-by: null`, not changed to
   `superseded-by: ADR-042`. Considered and declined: the issue's own fix
   section frames `rejected` and `superseded-by: ADR-042` as alternative,
   mutually exclusive resolutions ("Mark it rejected... or superseded-by:
   ADR-042"), not a combination; ADR-031 was never adopted, so a
   `superseded-by` link (denoting an adopted decision later replaced) would
   misstate its history. The causal link independent-thinker wants is already
   explicit in ADR-031's prose and in ADR-042's new Downstream line (change 4).
   Non-blocking per independent-thinker's own framing; does not change the vote.

## Phase 4: Convergence Check (post-fix)

Re-verified against the fixed files: `_get_adr_status` (parser) returns
`superseded / rejected / accepted` for ADR-028 / ADR-031 / ADR-056
respectively, with correct bidirectional `supersedes` / `superseded-by` for
ADR-028 <-> ADR-056. `find . -name '*.ps1' -not -path '*/node_modules/*' -not
-path '*/.venv/*'` (run from the repository root) returns zero results, independently
confirmed by independent-thinker, critic, and analyst across this round.

- **critic**: P0 addressed by changes 1-2. Vote converts from Block to
  **Accept**.
- **architect**: P1 addressed by change 2. Vote converts from
  Disagree-and-Commit to **Accept**.
- **independent-thinker**: reservation #2 resolved (ADR-028 now superseded
  rather than left deprecated-and-historical); reservation #1 considered and
  declined per item 5 above. Vote: **Disagree-and-Commit**, dissent recorded,
  non-blocking.
- **security, high-level-advisor, analyst**: no reservations against this
  pair; votes stand at **Accept**.

**Consensus reached**: 5 Accept, 1 Disagree-and-Commit with recorded,
non-blocking dissent. No seat votes Block on the final state.

### Next Steps

None blocking.

## Round 3: Copilot PR Review (post-merge-to-branch, PR #5283)

GitHub Copilot's automated review on PR #5283 filed one finding against
ADR-056: the Decision section (items 2 and 6) still specified
`-OutputFormat` (PowerShell parameter style) and a flat `ErrorCode` field,
contradicting the actual Python contract in `scripts/github_core/output.py`
(the `--output-format` argparse flag; a nested `Error.Code` field, not a
top-level `ErrorCode`). Marking ADR-056 `accepted` and using it as ADR-028's
successor would have made another contradictory contract authoritative,
which is the exact failure class issue #5201 exists to fix.

Verified directly: `scripts/github_core/output.py:20-35` (`add_output_format_arg`)
defines `--output-format` with lowercase choices `json`/`human`/`auto`;
`scripts/github_core/output.py:147-154` (`write_skill_error`) nests the exit
code as `envelope["Error"]["Code"]`, never a top-level `ErrorCode`. Round 2
(Phase 3 above) checked that ADR-056's Implementation Notes named the right
file and that its Consequences claim ("schema consistency is enforced at the
envelope level") was true; it did not check that the Decision section's own
parameter and field names still matched that file's actual signatures. That
gap is exactly what Copilot's finding closed.

Fix: rewrote Decision items 2 and 6 to the shipped Python contract
(`--output-format`; nested `Error.Message`/`Error.Code`/`Error.Type`), and
added a provenance note on the Decision section explaining the original
2026-03-08 PowerShell-era wording and why it changed. No frontmatter change;
ADR-056 remains `status: accepted`, `supersedes: [ADR-028]`.

## Round 4: Copilot PR Review, second pass (post-merge-to-branch, PR #5283)

Copilot re-reviewed after Round 3's fix and filed three more findings, two
against files this file already covers and one new:

1. **ADR-056 schema/validator drift (new).** Round 3's fix quoted
   `scripts/github_core/output.py`'s full `valid_types` tuple in the ADR
   Decision text, which included `RateLimitError` and `VerificationFailed`.
   Copilot checked those two values against the enforcement artifacts and
   found both `.agents/schemas/skill-output.schema.json` (line 33) and
   `scripts/validate_skill_output.py` (`VALID_ERROR_TYPES`) enumerated only
   6 of the 8 types `output.py` actually accepts. Verified directly: both
   files' enums were missing `RateLimitError` and `VerificationFailed`, and
   `tests/test_github_pr_diagnostics.py`, `tests/test_list_issues.py`, and
   `tests/test_close_issue.py` already emit those two error types in
   production code paths. A producer could emit an ADR-056-conformant
   envelope the repository's own validator would reject: the exact
   contradiction-between-live-artifacts class issue #5201 exists to fix,
   just one layer down from ADR prose. Fix: widened both enums to the 8
   values `output.py` accepts, and extended
   `tests/test_skill_output.py::TestWriteSkillError::test_validates_error_types`
   to cover all 8 (separate commit, non-ADR files, this repo's atomic-commit
   cap requires ADR and non-ADR changes to split).

2. **ADR-031 "Never implemented" claim wrong (previously missed, resurfaced).**
   Round 2's ADR-031 rewrite claimed "Never implemented: no `gh_cli`/`daemon`
   routing config or named-pipe daemon exists in the repository." Copilot
   found this false: Strategy 1 (direct `gh` CLI calls for simple wrapper
   skills) shipped under issue #286, closed `completed`, via PR #1588
   (merged 2026-04-10). Verified directly: `docs/github-api-capabilities.md`
   lines 232-236 list five gh-native shell scripts at
   `.claude/skills/github/scripts/gh-native/`, and issue #286's
   `closed_by_pull_requests` confirms PR #1588. Only Strategy 2 (the
   named-pipe daemon, issue #287) was never built, closed `not planned`.
   Per ADR-073, `implemented` flips true at the first merged change
   implementing the decision; Strategy 1's merge is that change. Fix:
   `implemented: false` -> `implemented: true`; rewrote the Status
   paragraph to describe both strategies and their actual (partial)
   disposition instead of the blanket "never implemented" claim. The
   rejection verdict itself is unchanged: rejecting the record reflects that
   the PowerShell performance problem it targeted no longer exists, not
   that nothing in it ever shipped.

3. **ADR-056 Trade-offs section still said `-OutputFormat` (previously
   missed, resurfaced).** Round 3 fixed Decision items 2 and 6 but missed
   the Trade-offs section's own mention of the same parameter under the old
   PowerShell name, leaving the accepted ADR with two spellings of the same
   argument. Fix: `-OutputFormat` -> `--output-format` at that line. The
   "Alternatives Considered" table's `-OutputJson` entry is untouched: it
   names a different, rejected alternative, not the chosen contract.

None of these three findings change ADR-005, ADR-042, or the frontmatter
status/supersession values already converged on in Rounds 1-3. Requested a
fresh Copilot review after pushing this round's fixes.
