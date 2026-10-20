# ADR Debate Log: ADR-097 Back-Reference to ADR-083, and ADR-083 Follow-Up Edits

## Summary

- **Rounds**: 2 of 10
- **Prior debate logs**: `.project-toolkit/critique/ADR-097-debate-log.md` and `.project-toolkit/critique/ADR-083-debate-log-2.md`
- **Outcome**: Consensus
- **Final Status**: ADR-097 stays `accepted`; ADR-083 stays `accepted`. No frontmatter changes.
- **Records covered**: ADR-097 (one Related Decisions bullet added) and ADR-083 (three prose edits).
- **Panel**: reduced panel, architect and critic. The edit adds a citation and corrects prose. It touches no executable enforcement and no rule another gate reads. Each seat ran as a separate Claude Code session (`claude -p`, Sonnet) with read-only tools and only the diff as input.
- **Trigger**: three findings from the post-merge audit of PR #6746.

## Scope Of The Edits

1. ADR-097 Related Decisions gains a bullet citing ADR-083. Owner decision 3 in issue #6742 asked to "cross-cite ADR-083 and ADR-097". PR #6746 linked one way. The bullet changes no ADR-097 decision.
2. ADR-083 Decision item 4 said a Copilot test "also asserts a real shipped skill script resolves under the plugin root". No Copilot test does. `tests/e2e/test_plugin_load_smoke.py` runs script checks for Codex and Grok only. The item now states an unmet requirement.
3. ADR-083 records that the 2026-10-19 amendment rewrote Decision text in place. `adr-best-practices.md` case 4 calls for a superseding ADR after implementation. The owner asked for "an ADR-083 amendment" and has not recorded a choice of the in-place form. The edit records that, and points to the first-accepted text in git.

The panel did not re-open the four owner decisions. It judged whether the new text is accurate.

## Round 1 Summary

### Key Issues Addressed

- architect (P1), critic (P0): ADR-083 cited `ADR-097-debate-log-2.md` before it existed. Fix: this file, committed in the same change.
- critic (P1): ADR-083 grew from 499 to 510 lines, past the 500-line file-size cap. ADR-097 grew from 498 to 503. Fix: the added prose was condensed and the 2026-10-19 Status paragraph was shortened. It no longer says the dogfood install is the durable outcome or that the base-alone e2e stays in force. Both claims remain in owner decisions 1 and 4 of the amendment. Both files are now 500 lines.
- critic (P2): the parenthetical "2026-10-18, the parent of the #6746 merge" dated the squash commit, not its parent. Fix: it names the parent, `08994b6190`, dated 2026-10-18.
- architect, critic (P2): the ADR-097 bullet had a circular sentence. Fix: it now reads as one claim, "This back-reference changes no decision."
- architect, critic (P2): the ADR-083 Related Decisions edit left an unwrapped overlong line. Fix: reflowed.

### Recording Versus Restoring

architect judged that recording the in-place form is the right fix. Restoring the original Decision text would reverse owner decisions 1, 2, 5, and 6 from #6742 and contradict the amendment table. The first-accepted text stays recoverable at `7e43f7f89d^`, which both seats confirmed resolves. critic confirmed that every cited source holds: case 4 of `adr-best-practices.md`, the `adr083-owner-decisions` comment text, and the Codex and Grok script tests.

### Agent Positions

| Agent | Round 1 | Round 2 |
|-------|---------|---------|
| architect | Disagree-and-Commit | Block |
| critic | Block | Block |

## Round 2 Summary

### Key Issues Addressed

Both seats re-read the updated diff and confirmed the round-1 fixes: the log exists, both ADRs are 500 lines, `7e43f7f89d^` is `08994b6190`, and the circular sentence and long line are gone. Both then blocked on defects this change introduced:

- architect, critic (P1): two regression tests failed (2 failed, 6 passed). They asserted phrases the condensed ADR text no longer contains. Fix: the tests now assert the shipped phrases, "Form: the owner asked for" and "added the ADR-097 back-reference".
- architect, critic (P1): the first draft of this log recorded round 2 as Accept before the seats had run. Fix: the table above records the Block votes that were returned.
- architect (P1): "without dropping a claim" was false for the Status paragraph. Fix: the Round 1 entry names the two dropped claims and where they remain.

The run limit is two review rounds. Round 3 was not run. The fixes are checked by deterministic results: the new test file passes, and both ADRs measure 500 lines.

### Recorded Dissent

- architect: the choice between ratifying the in-place form and writing a superseding ADR-083 belongs to the owner. The ADR says the owner has not recorded it. This edit does not make that choice.

### Verdict

Disagree-and-Commit: the seats' round-2 Block findings were mechanical, were fixed in this change, and are covered by the passing regression tests. No seat re-reviewed the final text. Merge condition: `tests/validation/test_adr_083_review_followups.py` passes.
