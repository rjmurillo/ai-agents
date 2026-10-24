# A stray identity in the shared clone config reaches main through agent commits

## Statement

Every linked worktree reads the shared clone's `.git/config`. A `[user]` block written there changes the author of every commit made in every worktree. Nothing in the merge path checks the author, so the identity can land on main.

Rules:

- An agent MUST NOT run git or tests with `GIT_DIR` pointed at the shared clone.
- Before merging an agent PR, run `git log --format='%an <%ae>' origin/main..HEAD` in the PR worktree. Every line must be the real owner identity or a bot.
- Pass `--commit-body` to `set_pr_auto_merge.py` to set the squash message. That omits a bad `Co-authored-by` trailer that commit subjects would otherwise carry.
- A merged squash body cannot be fixed without rewriting main. AGENTS.md forbids that, so the trailer stays.

## Evidence

- OBSERVED 2026-10-23 about 21:51 to 22:11 PDT: two agent commits carry the author `T <t@example.com>`. They are `88e5131ec8` (branch `fix/6892-split-pool-collect-once`) and `692d424cd0` (branch `fix/implementer-authorized-guards`). Both were pushed.
- OBSERVED 2026-10-24: PR #6898 squash-merged as `31218cf53c`. Its body ends with `Co-authored-by: T <t@example.com>`, found with `git log -1 --format=%B 31218cf53c`.
- OBSERVED: `scripts/github_core/placeholder_identity.py:24-28` leaves `*@example.com` off the placeholder denylist on purpose, so the existing trailer filter in `set_pr_auto_merge.py` did not strip this one.
- OBSERVED: PR #6900 had auto-merge armed on the bad head. The orchestrator disabled it. Replacement PR #6901 merged clean as `4f83487d89`.
- INFERRED: the first guess blamed `GIT_DIR` in a test run for issue #6889. PR #6902 refuted it. The `/tmp/.git` writer was the Codex `workspace-write` sandbox. The source of the `[user]` block was never confirmed.

Retro: `.project-toolkit/retrospective/2026-10-24-shared-clone-identity-leak.md`
