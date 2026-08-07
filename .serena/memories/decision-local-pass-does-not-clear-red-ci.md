# A clean local pass does not clear a red CI check: check your dirty tree

## The trap

A validator that answers "does this path exist?" by reading the filesystem
gives a different answer on a developer machine than in CI, because the
developer machine has gitignored build output that CI never generates. The same
commit then produces different numbers in the two places.

Measured 2026-08-07: `Validate Vendor Portability` was red on `main`
(594e13be6) and on every open PR that merged it, reporting 25 findings against
a baseline of 24 for `ai-agents-architecture-contract/SKILL.md` and 22 against
21 for `ai-agents-generation-and-release/SKILL.md`, both mirrors each. The
identical command on the identical commit passed locally, repeatedly.

The extra finding was an existence miss for `build/audit/GENERATION-AUDIT.md`,
which `.gitignore:70` excludes (`/build/audit/`). My tree had it because I had
run a generator. CI never does. The ratchet baseline in PR #4715 was therefore
recorded one too low on four entries, and merging it turned `main` red.

## Why the obvious diagnosis is wrong

The natural reading of "CI says 25, baseline says 24" is that the branch added
a reference, so the fix is to bump the baseline. That is wrong twice over. The
branch did not touch either skill file or the baseline. And bumping to 25/22
goes green while leaving the measurement machine-dependent, so the next
contributor with a different set of local artifacts re-breaks `main`.

A ratchet whose measurement depends on the machine cannot hold a line. The
number is not the bug; the non-reproducibility is.

## Procedure when local passes and CI fails on the same commit

1. Confirm CI ran your SHA, and note that for a pull request it runs the
   **merge** commit, not your head. Fetch it explicitly:
   `git fetch origin +refs/pull/<N>/merge:refs/remotes/origin/pr<N>merge`
   and run the check in a worktree on that ref.
2. If that still passes, the difference is your tree, not the commit. The
   fastest discriminator is a fresh worktree, which has no untracked files:
   a check that fails there and passes in your main working copy is reading
   something git does not track.
3. Run the check against `origin/main` alone before assuming your branch is at
   fault. Here `main` itself was red, so every PR inherited it.

## The rule this yields

A validator that gates a shared branch must not consult the working tree for
existence. Resolve against `git ls-files` so every clone agrees. Fall back to
the filesystem only when there is genuinely no repository; degrade silently on
an operational git failure and you have restored the exact defect.

Watch for tracked symlinks when you make this change: this repo tracks
`memory_enhancement -> scripts/memory_enhancement`, and `git ls-files` lists
only the link, so every path beneath it becomes "missing" unless you resolve
through it. Both ends are tracked, so following it stays reproducible.

Fix: PR #4750, issue #4748.

## The converse trap: a green run that never ran

`Validate Vendor Portability` is gated on a "Check for Skill Script Changes"
job. A push that touches no skill path takes the `Skip Validation (No Skill
Changes)` branch, the validation job reports `skipped`, and the run rolls up as
`success`.

So `main` showed success at c1174b157 and ba62e8d1e while still failing the
check: running the unfixed checker against c1174b157 in a clean worktree
reproduced `22 marker-drift findings (baseline 21)`. The greens were vacuous.

Two consequences. A branch-level run history for a path-filtered workflow is not
evidence the check passes, so confirm the step actually executed
(`gh run view <id> --log | grep -c "<step name>"` returns 0 when it did not).
And a repository-wide breakage in a path-filtered check stays invisible on the
default branch while blocking exactly the PRs that touch the filtered paths,
which is why this looked like a per-PR problem for hours.
