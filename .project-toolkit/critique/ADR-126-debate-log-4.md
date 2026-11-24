# ADR Debate Log 4: ADR-126 Review Fixes and Post-Consensus Hardening

## Summary

- **Prior debate log**: [3](ADR-126-debate-log-3.md), closed by consensus.
- **Rounds**: 1.
- **Panel**: reduced, architect and critic.
- **Claims ledger**: [ADR-126 claims ledger](ADR-126-claims-ledger.md), rows 25 to 30.

## Change under review

The `/review` run on `8fc047e91e` raised three ADR points.
Decision 2 did not name two skills that drive Serena-layout scripts.
The record stated no rollback path.
Security did not say the data framing is advisory.
Debate log 3 also recorded two narrowing changes without a new round:
the `.git` rule on the memory root, and linked-file containment.
This round reviews both sets.

## Round 1

Architect voted Accept. Critic voted Disagree-and-Commit.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Critic | P1 | Confirmation cited no test for linked-file containment | Five tests in `test_memory_store_containment.py` now named |
| Critic | P1 | The record did not say what a user sees on each skip path | Decision 7 names the `recall skipped` note, the escaping-folder note, and the silent linked-file skip |
| Critic | P1 | The `.git` rule left tarball, worktree, and nested layouts unstated | Decision 7 names all three; a `.git` file counts |
| Architect | P1 | Decision 4 plus Decision 7 hid that the nearest marker wins first | Decision 7 says so in one sentence |
| Architect | P1 | Containment wording did not say it covers file links only | Security says "file symlink" and records that `rglob` skips linked folders |
| Critic | P2 | Rollback bullet rendered as a separate list and ignored Decision 7 | Joined to the list; says the `.git` rule stays |
| Critic | P2 | Decision 2's skill sentence had no consequence | Negative consequences say `curating-memories` stops in a notes-only repository |
| Architect, critic | P2 | Framing bounds named only the 8000-character cap | Security names `MAX_BLOCK_CHARS` and the 3-result cap |

## Verdict

Consensus: architect Accept, critic Disagree-and-Commit.
All P1 findings were fixed in place. Each narrows or clarifies a claim.
The post-consensus hardening from debate log 3 now has a recorded round.

## Post-consensus review edit

The round 2 `/review` decision-rigor axis found two Decision 7 claims with no named test.
A new test covers the `.git` file case; the nested case already had a parity layout.
Confirmation now names both. No decision changed.
