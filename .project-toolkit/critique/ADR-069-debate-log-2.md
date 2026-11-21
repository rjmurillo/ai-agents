# ADR Debate Log: ADR-069 The Curated Context Corpus IS the Product (Debate 2)

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-069-debate-log.md` (closed at round 2, consensus)
- **Outcome**: Consensus
- **Final Status**: accepted

The first debate closed on 2026-11-20 with consensus on `status: accepted` and `implemented: true`.
Edits made after that vote are the subject of this debate, per the closed-log rule in `debate-protocol.md`.
The change is prose only and touches no enforcement, so the reduced panel (architect and critic) ran.
Both panelists were fresh agents, with no context from the first debate.

## Background: Edits After The First Consensus

These edits came from two sources. One was findings applied after the first debate's votes. The other was three rounds of the pre-merge `/review`.

- The `implemented` paragraph rests only on the artifact test. PR #7482 cites ADR-069 only to exclude it.
- Implementation Notes credits follow-up PR #7489 with a gate.
- Item 4 cites the 2026-09-28 control ablation, which returned `MIXED`.
- A Revisit condition points at the research-frontier Program 1 falsifiable milestone.
- The `implemented` paragraph states that `true` routes a later material change to supersession.
- The Context section marks the catalog as a 2026-05-02 snapshot and names the one entry PR #5887 rewrote.
- The Status section names both debate logs. The Decision opener ends with a period.

An interim panel vote on an intermediate text was recorded inside the first log. That broke the closed-log rule, so this change removed it from the first log. Edits followed that vote, so it closes nothing. This log holds the closing vote.

### Carried-Forward Issue

The first log's closing vote has the critic at Disagree-and-Commit. Its "Resolution Of The Split" explains why the critic moved to `true`, and it records no separate reservation. The issue carried here comes from the interim vote this change removed from the first log. In that vote the critic recorded one reservation: `implemented: true` routes later material change to supersession, while the principle's effect is unmeasured.

## Round 1 Summary

### Votes

| Agent | Vote |
|-------|------|
| architect | Needs-revision |
| critic | Needs-revision |

### Key Issues Addressed

- Both: the Status section named this log before it existed. Resolved by design: this log lands in the same commit as the voted text.
- architect: the ablation sentence hid that the reduced arm loaded no files.
- critic: "its effect is unmeasured" did not match the sources. Issue #7471's verdict calls the ablation a measurement, and the result was `MIXED`.
- architect: `instruction_bytes.py` came from PR #5999, not from issue #5400.
- critic: the snapshot sentence, the inventory pointer, and the Revisit mechanism each claimed more than the sources support.
- critic: the PR #7489 sentence read like evidence for `true`.

## Round 2 Summary

### Major Changes Made

- Item 4 names the arms: 6 always-loaded files (40,324 bytes) against no files.
- Item 4 says the test is small, below the Program 1 bar, and neither confirms nor falsifies the record. The effect is "not established".
- The `instruction_bytes.py` source reads "(PR #5999, issue #5400)".
- The snapshot sentence reads "except one entry".
- Item 1 is "the instruction-corpus inventory". Retrieval surfaces have none.
- The Revisit condition says a negative result requires a superseding record.
- The `implemented` paragraph says neither PR is part of the basis for `true`.
- The research-frontier and research-methodology skill templates use "not established" to match.

### Votes

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Accept |

### Resolution Of The Carried-Forward Issue

The critic judged the carried-forward issue resolved. A negative Program 1 result now requires a superseding record, so the open effect has a defined exit.

### Finding Not Applied

architect P2 (optional): "per accepted task" could read "per accepted durable task", matching the metric file. The number does not change. It was not applied, because any ADR edit after this vote would start a new debate.

### Claims Checked

| Claim | Result |
|---|---|
| Ablation arms: 6 files, 40,324 bytes against 0 files | VERIFIED (`control-ablation-v0.7.0.md` Setup, 2026-11-20) |
| 9 of 15 against 10 of 15 accepted durable, 47 percent lower cost | VERIFIED (same file) |
| PR #5999 merged 2026-09-29 and added `instruction_bytes.py` | VERIFIED (`gh pr view`, `git log --diff-filter=A`) |
| PR #5887 merged 2026-09-23 | VERIFIED (`gh pr view`) |
| No em or en dashes and no banned words in the ADR | VERIFIED (critic scan, 2026-11-20) |

## Next Steps

- `.project-toolkit/architecture/ADR-107-canonical-skill-contracts-and-harness-projections.md` (Related Decisions) still calls ADR-069 `proposed`. Editing ADR-107 needs its own debate log, so this change leaves it. The PR for this change names it as an open follow-up.
