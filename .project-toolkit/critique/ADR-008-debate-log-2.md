# ADR Debate Log: ADR-008 Protocol Automation via Lifecycle Hooks (debate 2)

Prior debate log: `.project-toolkit/critique/ADR-008-debate-log.md`. It closed
with consensus on the first 2026-11-20 amendment. This log covers the second
2026-11-20 amendment and restarts at round 1.

Claims ledger: `.project-toolkit/critique/ADR-008-claims-ledger.md`. It
records 21 claims and the four `adr-generator` exit gates.

## Summary

- **Scope**: correction to an accepted ADR. The Context Loader hook prints a
  static 770-byte guide to finding past retrospectives. It injects no
  retrospective content. The decision text is unchanged; status stays
  `accepted`.
- **Panel**: reduced (architect, critic). The edit touches no executable
  enforcement. `tests/hooks/test_adr_hook_claims.py` reads the hooks table row,
  and the row still names a live file with an "Implemented" status. The
  architect confirmed the reduced panel is right.
- **Rounds**: 2 (Phase 1 independent review, Phase 4 convergence).
- **Outcome**: Consensus. Architect Accept, critic Accept.

## Round 1 Summary

### Key Issues Addressed

- architect and critic, P1: the entry adopted an unmeasured guide on the same
  day the first entry retired machinery for lacking a measured benefit, and did
  not say so. The amendment now names an owner-directed, bounded exception. It
  states the cost going from zero to 770 bytes. It adds a review trigger:
  retire the guide if the #7471 counterfactual delta shows no change. It
  closes the first entry's "retire the hook outright" question, because the
  hook is no longer inert.
- critic, P1: the count of 117 numbered filenames did not reproduce from a
  paraphrase of the matcher. The ledger now holds the exact command, which
  prints `117 21`. The critic reran it and withdrew the 120 to 125 figure.
- architect, P2: 21 of the 117 numbers name an ADR or a session, not an issue
  or PR. Ledger row 7 had said "issue or PR number". It now says what the
  matcher counts.
- architect, P2: the sample held 4 ADR or session files that could never
  match an issue title. The real sample was recounted by kind: 3 of 25 issue
  or PR files hit, 0 of 4 ADR or session files. The amendment says 3 of 25.
- architect, P2: the first entry had no forward pointer to the second. It
  now ends "Partly superseded by the second entry below".
- critic, P2: the guide said `memory-search` "or" `read_memory`. It now says
  search first, then open a hit. A test pins the order (`122d56c74`).
- critic, P2: the symlink test checked only empty output. It now asserts the
  `(none)` audit line. The missing-directory audit test was renamed.
- critic, P2: "every session" became "every Claude Code session". Ledger row
  20 verifies that no plugin or Copilot `hooks.json` registers the hook.
- critic, P2: `CONTRIBUTING.md` still described the hook as a reminder only.
  Its hook table row now names the guide.
- critic, P2: byte figures now carry the commit they were measured at.

### Major Changes Made

1. Exception, review trigger, and closed question added to the amendment.
2. Sample denominator corrected from 29 to 25.
3. Numbered-filename count restated against the exact matcher in the ledger.
4. Guide text and two tests changed in a follow-up commit, `122d56c74`.

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept (round 1 Disagree-and-Commit, resolved) | P1 exception and review trigger fixed. P2 pointer, matcher wording, and denominator fixed. Ran 465 tests across the hook-claims and loader suites |
| critic | Accept (round 1 Revise, resolved) | Both P1s fixed. Reran the ledger matcher and got `117 21`. Ran 491 tests across five files |

### Dissent Recorded

- critic, P2, not blocking: the review trigger fires only when someone runs
  the #7471 counterfactual delta for this guide. It names no owner, no date,
  and no open issue, and #7471 is closed. If nobody runs the eval, the guide
  stays, which is the outcome the first entry's rule exists to prevent. The
  critic asks the owner to name who runs it and when, or to link an open
  issue. This is the owner's decision; the review left it open.

## Next Steps

- Owner decision: name who runs the #7471 counterfactual delta for the guide,
  and when, or link an open issue for it.
- Noticed, outside this change: `.project-toolkit/retrospective/INDEX.md`
  line 6 says it lists "11 of the 140 files". The directory held 244 at
  `15c13340a` (2026-11-20).

## Post-Consensus PR Review Correction (2026-11-22)

- CodeRabbit (PR #7503, review on `1be21fc33`, P2): the second amendment stated
  the guide cost as "770 bytes in every Claude Code session", but the hook
  registers on `SessionStart` with no matcher (`.claude/settings.json`,
  `dispatch_groups.json`) and emits on every `SessionStart` event without
  filtering by trigger source. Because `SessionStart` can repeat within a
  session (for example, at startup and after compaction), ADR-008 now states
  the cost as 770 bytes (estimated 190 tokens) per `SessionStart` event and
  notes that a session can pay that cost more than once. No behavioral or
  decision change.
