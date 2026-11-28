# ADR Debate Log: ADR-100 commit-limit citation pinned to its commit

## Summary

- **ADR**: ADR-100 (`.project-toolkit/architecture/ADR-100-retire-pr-size-ceilings.md`)
- **Rounds**: 2 of 10
- **Outcome**: Consensus, 2 of 2 Accept in round 2
- **Final Status**: unchanged (the edit changes no status or decision)
- **Panel**: reduced panel, architect and critic. The edit changes one citation in one
  sentence. It changes no enforcement logic and no rule that another gate reads.
- **Prior debate logs**: `.project-toolkit/critique/ADR-100-debate-log.md`,
  `ADR-100-amendment-2026-09-22-debate-log.md`, and
  `ADR-100-101-enforcement-planes-debate-log.md`, all closed. This log reopens none of them.

## Trigger

Branch `fix/semgrep-ptk-run-allow-path` (issue #7591) adds 116 lines to
`scripts/validation/git_hook_policy.py` above line 6123. The pre-push citation reverse
pass (`scripts/validation/citation_reverse_pass.py`, run by `pre_pr.py --compact` from
`lefthook.yml`) then flagged ADR-100 line 181, which cited `git_hook_policy.py:6123`.

## Change

Line 181 read "one absent `--no-merges` at `git_hook_policy.py:6123` between them". It
now reads "one absent `--no-merges` in `_check_commit_limit` (`git_hook_policy.py` at
`5b88ed23f4^`, 2026-08-21) between them". No other text in ADR-100 changes.

## Evidence

- `git show 5b88ed23f4^:scripts/validation/git_hook_policy.py`, line 6122:
  `def _check_commit_limit`. Line 6123: the `rev-list --count` call, with no `--no-merges`.
- `5b88ed23f4` (2026-08-21) is the commit that added ADR-100 (#5181). Its parent,
  `ce4860ea60`, is also dated 2026-08-21.
- On main `b2623d82a4` (2026-11-28), `git_hook_policy.py` has no match for
  `_check_commit_limit`, `--no-merges`, or `rev-list --count`. Line 6123 there is an
  unrelated comment about `log.showSignature`.
- Line 181 frames its numbers as "taken from the branch at that moment". It is a
  historical claim, so a pinned reference is the accurate form.

## Round 1 Summary: option A rejected

Option A changed only the number, from 6123 to 6239, to follow the line shift.

| Agent | Position |
|-------|----------|
| architect | Block. P1: line 6239 on the branch tip is the same unrelated comment as 6123 on main. The citation would point at code that has nothing to do with commit counting. |
| critic | Disagree-and-Commit. P1: same finding. The gate accepted 6123 only because its anchor is the plain word "main". A bump makes a false pointer look freshly checked. |

Option A was dropped. An ignore marker was also rejected, because it leaves a wrong
citation for readers.

## Round 2 Summary: pinned reference

| Agent | Position |
|-------|----------|
| architect | Accept. The claim is true at `5b88ed23f4^`. The hash and its ISO date sit on the same line (universal.md MUST 9). No validator or test reads the old citation. |
| critic | Accept. The reference resolves to `ce4860ea60`, and the code matches. The gate does not parse a citation with no `path:N` shape (docstring lines 42-44), and a pinned reference cannot go stale. |

### P2 Findings (documented, non-blocking)

- The rewrite drops the line number. `_check_commit_limit` is unique in that file, so the
  reference stays exact. Adding the number back would restore the `path:N` shape and the
  gate would flag it again.
- `5b88ed23f4` without the `^` holds the same code. The parent form names the branch state
  the sentence describes, so it stays.
- ADR-100 lines 31, 38, and 251 cite `git_hook_policy.py:3295`, `:6727`, and `:6856`. They
  were stale on main before this branch. The ADR-093 follow-up carries them.

## Verdict

Accepted by both seats in round 2. Round 1 dissent is recorded above. No open dissent.
