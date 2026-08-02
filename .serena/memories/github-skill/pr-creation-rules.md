# PR Creation Rules

**Last Updated**: 2026-08-02
**Sessions Analyzed**: 2

## Constraints (HIGH confidence)

- Use `new_pr.py` for PR creation, not raw `gh pr create`. The skill-first rule
  remains a MUST in `AGENTS.md`; PR #3293 retired its runtime blocking hook.
  (Session 2, 2026-04-10; retirement 2026-07-21)
  - Historical evidence: the retired hook blocked `gh pr create` and redirected
    to `.claude/skills/github/scripts/pr/new_pr.py`.
  - Script: `python3 .claude/skills/github/scripts/pr/new_pr.py --title "..." --body "..."`

## A two-dot branch diff can look like a rebase accident (HIGH confidence)

Canonical guidance already exists and is more precise than this note. Follow it
first:

- `.claude/skills/review/SKILL.md` step 1 prescribes
  `git diff "origin/$BASE_BRANCH"...HEAD` and explains why the remote-tracking
  ref is used rather than the local branch.
- `.claude/hooks/PreToolUse/push_guard_base.py` documents a four-step ladder for
  resolving the base: the PR's `baseRefName` via `gh pr view`, then the
  branch's configured upstream, then `refs/remotes/origin/HEAD`, then
  `origin/main` as a last-resort literal. Its own comment notes that hardcoding
  `origin/main` "would pull in the parent branch's history."

This note records only the diagnostic, which is not written down anywhere else.

`git diff <base>..HEAD` compares the two tips, so every file the base gained
since you branched appears as a deletion in your branch. Measured on
`d039aa732d`, a one-commit docs branch whose merge base is `c02f61ddd2`:

| Command | Result |
|---|---|
| `git diff --shortstat ede9fd1fef..d039aa732d` (two dots, current main) | 253 files, 838 insertions, 5205 deletions |
| `git diff --shortstat ede9fd1fef...d039aa732d` (three dots) | 3 files, 3 insertions |
| `git diff --shortstat c02f61ddd2 d039aa732d` (explicit merge base) | 3 files, 3 insertions |

The commit touches three lines in three files. The two-dot form against current
main reports it as deleting 5205 lines, including whole test files it never
touched. The magnitude tracks how far the base has moved, so the same branch
reported 804, 515, and 5205 deletions against three different main snapshots on
the same day.

The number is arithmetically correct and answers a different question than the
one asked. A two-tip diff can resemble a rebase accident, so verify the
merge-base range before acting on a diff that alarms you.

Two dots is right when a tip-to-tip comparison is what you want.
`push_guard_base.py` uses `git diff @{push}..HEAD` deliberately to ask what is
committed but not yet pushed, and warns that substituting a merge-base range
there would reintroduce branch history.

`new_pr.py` already uses three dots (line 282, both the `.claude/` and
`src/copilot-cli/` copies, byte-identical). Its exposure is different: `--base`
defaults to the string `main` (line 519), which resolves locally to a stale
`main` for the diff and is separately passed to `gh pr create` as the remote
base name. Pass an explicit base rather than relying on the default.
