# PR Creation Rules

**Last Updated**: 2026-07-30
**Sessions Analyzed**: 2

## Constraints (HIGH confidence)

- Use `new_pr.py` for PR creation, not raw `gh pr create`. The skill-first rule
  remains a MUST in `AGENTS.md`; PR #3293 retired its runtime blocking hook.
  (Session 2, 2026-04-10; retirement 2026-07-21)
  - Historical evidence: the retired hook blocked `gh pr create` and redirected
    to `.claude/skills/github/scripts/pr/new_pr.py`.
  - Script: `python3 .claude/skills/github/scripts/pr/new_pr.py --title "..." --body "..."`

## Read your branch diff with three dots, never two (HIGH confidence)

`git diff main..HEAD` compares the two tips. Every file `main` gained since you
branched shows up as a **deletion in your branch**. The diff is arithmetically
correct and answers a question nobody asked.

Measured on a one-commit docs branch (2026-07-30), three commits behind
`origin/main`:

| Form | Result |
|---|---|
| `git diff --shortstat origin/main..HEAD` (two dots) | 253 files, 838 insertions, **5205 deletions** |
| `git diff --shortstat origin/main...HEAD` (three dots) | 3 files, 3 insertions |
| `git diff --shortstat $(git merge-base origin/main HEAD) HEAD` | 3 files, 3 insertions |

The branch contained one commit touching three lines. The two-dot form reported
it as deleting 5205 lines, including whole test files it had never touched.

**Three dots is what GitHub shows.** A PR diff is computed against the merge
base, so the three-dot form and the explicit `merge-base` form agree exactly.
The two-dot form matches nothing the reviewer will ever see.

Why this is worth a rule rather than a lookup: the failure is loud but points
the wrong way. "My branch deletes 5205 lines of tests" reads as a catastrophic
rebase accident, so the instinct is to start undoing work that was never
damaged. Verify with three dots before believing a diff that alarms you.

Compare against `origin/main`, not local `main`. Local `main` goes stale the
moment anything merges, and `new_pr.py` defaults `--base` to the local ref
(line 519, diff at line 282), which inflates the changed-file list the same way.
