# ADR Debate Log: ADR-083 Amendment 2026-10-19, 90-Day Review Outcome

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-083-debate-log.md` (closed by consensus, including its 2026-07-19 amendment debate)
- **Outcome**: Consensus
- **Final Status**: accepted (frontmatter `status` unchanged; `implemented` flipped to `true`; `review-by` moved to 2027-01-17)
- **Records covered**: ADR-083. ADR-097 and ADR-084 were read as cross-references and not edited.
- **Panel**: architect, critic, and security. Security sat because Decision item 5 bound a security control. Each seat ran as an independent Claude Code session with its own agent definition and read-only tools.
- **Trigger**: issue #6742. ADR-083's `review-by: 2026-10-18` passed and `review-by-past-due` went from 1 to 2, which turned the required `Run Python Tests` check red on every PR.

## Scope Of The Amendment

The owner decided four things in issue #6742 (comment marked `adr083-owner-decisions`), after the review evidence in the comment marked `adr083-review-6742`:

1. Retire the `surface` tag (Decision item 1). The dogfood install is the durable outcome.
2. Remove the internal overlay (Decision items 2 and 6), per the Reversibility section.
3. Amend Decision item 5 to record the retirement of `invoke_security_gate` and `invoke_security_commit_gate`, cross-citing ADR-097. No control changes.
4. Restate Confirmation Criterion 1 with `skill list` on a base-alone install as the primary signal.

The panel reviewed whether the text records these decisions accurately. It did not re-open them.

One author correction was in scope from the start. The owner's wording said ADR-097 "retired" the two hooks. Git history shows commit 8318d1c350 (PR #3306, issue #3295, 2026-07-22) deleted both files, and ADR-097 (2026-08-19) calls them "already-retired". The amendment names ADR-097 the decision of record and does not claim ADR-097 deleted them. All three seats judged this accurate and faithful to the owner's intent. The pre-written Review Date outcome ("the tag plus the dogfood install") was also false, because the tag never shipped, so the amendment does not repeat it.

## Round 1 Summary

### Key Issues Addressed

- architect (P1): "PR #3295" was an issue number. Fix: "PR #3306 (issue #3295)" in owner decision 3 and Decision item 5. Verified: PR #3306 merged, titled "chore(hooks): purge internal-only hooks from vendored surface (#3295)".
- architect, critic (P1, P2): the net-negative rationale attributed both outages to both hooks and lacked a direct source. Fix: the text now quotes issue #3219, which records the #3197 finding. It adds that `invoke_security_gate` ran in consumer repos and `invoke_security_commit_gate` was `skip_if_consumer_repo` gated (ADR-084).
- security (P1): withdrawing the MUST hid that consumers lost an agent-time gate on Write and Edit in July. Fix: a Consequences > Negative bullet states the loss, that it is not restored, and that a rebuild needs a new proposal under ADR-097.
- security (P2): no record showed ADR-084's carve-out was weighed when the hooks were deleted by ROI. Fix: Decision item 5 says so, and names the owner decision as the after-the-fact authorization.
- architect, security (P2): Related Decisions said ADR-084's carve-out governs restoring a control. It covers retiring only. Fix: the carve-out bars retiring; ADR-084 rule 6 and `tool-use-hook-bar.md` govern restoring.
- critic (P1): "Every retained decision has shipped" was false, because Decision item 4's Copilot script-resolution assertion has no test. Resolution: the sentence is removed. `implemented` stays `true` on ADR-073's definition (flips at the first merged change; PR #3251 merged 2026-07-19). The missing Copilot assertion is recorded as noticed, not changed.
- critic (P2): Criterion 1 was looser than its test. Fix: "no `argument-hint` loader warning" and "every `EXPECTED_SKILLS` name".
- critic (P2): the 2027-01-17 review had no exit. Fix: it names the owner as the only required reviewer on `agent-copilot` (ADR-114) and requires a decision: approve Copilot legs, or drop Criterion 1.
- architect (P2): "The base ships zero hooks (ADR-097)" overstated ADR-097, which covers tool-use hooks only. Fix: cites the empty `hooks.json` as measured state plus ADR-097.
- critic (P2): stale live text in Why Change Now and References. Fix: past tense; the title is kept for citation stability, and Status says so.
- architect, critic, security: `ADR-083-debate-log-2.md` was cited before it existed. Resolution: this file, committed in the same change.

### Deferred P1: ADR-097 reciprocal citation

architect and critic raised that ADR-097 does not cite ADR-083, and that "cross-cite" reads as both directions. The task that commissioned this amendment allowed an ADR-097 edit only if the lifecycle checks require a reciprocal citation. `check_adr_lifecycle.py` checks reciprocity only for `supersedes` and `superseded-by` edges (`supersession-reciprocal`), and this is not a supersession. The amendment cites ADR-097 from Decision item 5 and Related Decisions. It records the missing back-link under "Noticed, not changed", and the PR body flags it for the owner. All three seats accepted the deferral in round 2.

### Major Changes Made

- ADR-083 Status, 2026-10-19 amendment section, Decision items 1 to 6, Rationale and Consequences notes, Impact table, Implementation Notes, Reversibility, Confirmation Criteria, Review Date, Related Decisions.
- `scripts/validation/adr_lifecycle_baseline.json`: the ADR-083 `cited-paths-exist` entry (2) is removed, because the amendment no longer cites the deleted `nightly-cli-smoke.yml` or `.claude/.claude-plugin/plugin.json`.
- `.project-toolkit/architecture/README.md`: regenerated index row.

### Agent Positions

| Agent | Round 1 | Round 2 |
|-------|---------|---------|
| architect | Block (P1: PR number, rationale, one-way cite) | Disagree-and-Commit |
| critic | Disagree-and-Commit | Disagree-and-Commit |
| security | Block (P1: residual consumer risk) | Accept |

## Round 2 Summary

### Key Issues Addressed

- Every claim in changed text was re-checked against its primary source. No claim was refuted.
- critic nit: the measurement date and the UTC run window looked inconsistent. Fix: the run window is labeled UTC and the commit date US Pacific.
- security question: the Codex half of the script-resolution note. Verified: `test_codex_plugin_loads_expected_skills` (`tests/e2e/test_plugin_load_smoke.py:2928`) runs an installed skill script.
- The "0 of 80 Copilot legs" count stays UNVERIFIED by the panel. The ADR attributes it to the review comment as a dated snapshot.

### Recorded Dissent (Disagree-and-Commit)

- architect: owner decision 3 asked to cross-cite both ADRs. The amendment links one way only, under a bound set by the orchestrating task rather than the owner. A reader who starts at ADR-097 cannot find that ADR-083 once required these hooks.
- critic: one-way linking meets the task bound but not the plain reading of "cross-cite". The owner should answer one question: is one-way enough, or should an ADR-097 edit add the back-reference?

### Strategic Review

- Chesterton's Fence: PASS. The amendment records why the tag, overlay, and security MUST existed, and the evidence that each no longer holds.
- Path Dependence: PASS. The overlay and tag were never built, so retiring them deletes nothing. Reverting the amendment is a revert of prose.
- Core vs Context: N/A.
- Second-System Effect: PASS. The amendment removes unbuilt scope and adds none.

### Verdict

**Consensus: 1 Accept, 2 Disagree-and-Commit, 0 Block.** Accepted as amended. Merge condition from all three seats: this log lands in the same change.
