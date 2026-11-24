# ADR Debate Log 3: ADR-126 After Merging PR #7523

## Summary

- **Prior debate logs**: [1](ADR-126-debate-log.md) and
  [2](ADR-126-debate-log-2.md), both closed by consensus.
- **Rounds**: 1, with a re-vote.
- **Panel**: reduced, architect and critic.
- **Claims ledger**: [ADR-126 claims ledger](ADR-126-claims-ledger.md), rows
  10, 11, 17, and 19 to 22.

## Change under review

PR #7523 (merged as `a6ccc9e6`, ADR-109 amendment 2026-11-20) ships the prompt
recall hook and the `memory_enhancement` package to Claude plugin installs. This
branch merged it. ADR-126 gains Decision 7, the hook's trust boundary, and
ADR-109 gains an `**Amended by**:` footer for its no-output statement.

## Round 1

Both seats voted Block.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Both | P0 | The hook found its root through `.git` alone, so in a nested layout it read a different store than search | Code changed: the hook uses the shared root rule, then requires a `.git` at or above that root. The root parity test gained a hook column; removing the check fails 4 tests |
| Both | P0/P1 | ADR-109 was amended by reference with no footer, against the repository convention | Footer added to ADR-109; Impact table row added |
| Both | P0/P1 | Confirmation cited a nonexistent test; ledger rows 10, 11, and 17 were false | Citation renamed; rows corrected and re-run, with the earlier error recorded |
| Architect | P0 | Text said the rules do not live in `lib/`, while the package now ships there | Context and Negative consequences say the package ships only in the Claude lib and the skill ships to five more trees |
| Both | P1 | The trust boundary sat in an unnumbered paragraph after Decision 6 | Now Decision 7, naming the `.git` requirement and the no-fallback on an escaping Serena folder |
| Both | P1 | Confirmation did not name the trust-boundary tests | Three tests named by file |
| Architect | P1 | One parity test leaked the session's `CLAUDE_PROJECT_DIR` | Test clears it; row 20 records passing with and without it |
| Both | P2 | Security text, "recall hooks" plural, and `stores.py` docstring | Reworded |

## Re-vote

The critic voted Accept, with one P2: no ledger row checked the five skill
trees, now row 23. The architect voted Block on one remaining sentence: Decision
4 still said the rules do not live in `lib/`, though `stores.py` ships there.
That sentence now names the two skill copies and the three reasons they stay out
of `lib/`, which was the architect's stated condition for Accept. Its P2s on the
missing PR numbers in the ADR-106 and ADR-109 footers stay open until the PR
exists.

## Verdict

Consensus: critic Accept; architect Accept on its stated condition, now met.

## Post-consensus hardening

The early `/review` security and correctness axes, run before the full review,
found two exposures. First, the hook accepted a `.git` anywhere above the
memory root, so an untracked folder nested in a work tree could feed recall.
Decision 7 now requires the root itself to hold `.git`. Second, a linked note
could point at any repository file, such as `.env`. Links now count only inside
their own store, in all three readers. Both changes narrow behavior the panel
accepted; neither widens it. Ledger rows 20 and 24 carry the evidence.

