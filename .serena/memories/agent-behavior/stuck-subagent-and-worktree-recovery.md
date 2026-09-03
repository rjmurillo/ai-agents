# Stuck-subagent and worktree-identity recovery patterns

Captured via `reflect` after a P1-batch fix session, 2026-08-27. Self-approved
in an unattended run with no human present for the skill's normal Y/n gate,
under the Autonomy Guardrail in `AGENTS.md` ("Internal+reversible: act"), and
ratified by the repository owner when this memory was opened for review.
Confidence labels below follow the skill's own HIGH/MED tiers.

## [HIGH] A SendMessage nudge does not unstick a subagent with no pending tool call

A dispatched agent hit the auto-mode classifier's block on `git filter-branch`
and `git reset --soft` (both flagged as destructive history-rewrite commands),
reasoned about a next step ("re-create the commits instead"), then went
completely silent for over an hour with no new transcript activity, while
`ListAgents` still reported it `running`. Sending it a `SendMessage` with a
concrete alternative plan did not resume it: the transcript never advanced
past the pre-nudge state. `SendMessage`'s own docs say a message "resumes it
at its next tool round" -- if the agent's last turn ended with nothing queued
and no tool call in flight, there may be no next round to deliver into.

Recovery that worked: `TaskStop` the agent, then take over its worktree
directly (it was an external worktree, not `.claude/worktrees/`, so this was
safe) and finish the fix by hand. Do not wait indefinitely on a nudge to a
silently-stalled agent; if a transcript has had zero new lines for well past
the task's expected duration, stop it and verify/finish the work directly
rather than re-nudging.

## [HIGH] `git checkout <branch> -- .` can silently pull stale content from a same-named LOCAL branch

While investigating a validator finding by hand, `git checkout
claude/fix-4981-select-axes-by-risk -- .` was run inside a worktree whose
current branch was `pr5361-clean` (tracking `origin/claude/fix-4981-...`).
Unknown at the time: a stale LOCAL branch with that exact name also existed in
the same worktree, left over from an earlier stuck agent's work, several
commits behind origin. `git checkout <ref> -- .` resolves `<ref>` to whatever
matches first in the local ref namespace, so this silently overlaid old file
content into the working tree with no warning, and left a staged diff that
looked like real, unexplained changes.

Caught only because `git status --porcelain` after the checkout showed
unexpected modified files, prompting a `git log -1 --oneline <ref>` check that
revealed a much older commit than expected.

Recovery, with a precondition that is not optional: read `git status
--porcelain` first and confirm every listed path is overlay pollution. `git
reset --hard HEAD` discards all tracked index and working-tree changes, not
only the overlay, so reach for it only when the status output is pure
pollution. When it also lists work you want, restore just the polluted paths
with `git checkout HEAD -- <path>...` and leave the rest alone.

That is still whole-file. `git checkout HEAD -- <path>` replaces the file in
both the index and the working tree, so a file that holds overlay pollution and
your own edits together loses the edits. For those, pick hunks with `git
checkout -p HEAD -- <path>` and accept only the pollution, or read your own
hunks out of `git diff HEAD -- <path>` first and reapply them after.

Do not stash here. This repository runs many worktrees off one `.git`, so
`refs/stash` is shared: a `git stash pop` can restore a sibling worktree's
entry. That is recorded in
`.agents/sessions/handoffs/2026-09-01-5404-handoff.md`, where a session hit it
and resolved with a targeted reset instead.

Takeaway: before `git checkout <ref> -- <path>` or any ref-based read in a
worktree that might have accumulated stale local branches (common in a
long multi-agent session), disambiguate with `git log -1 --oneline
origin/<branch>` first, or use the fully-qualified `origin/<branch>` form
directly instead of the bare branch name.

## [HIGH] A push rejected with GH007 (private email) mid-session means the worktree's git identity was never set

Three commits made in a scratch worktree carried the account owner's real
personal address as the author email, the one GH007 protects, instead of the
`users.noreply.github.com` address that account pushes under. Nothing had
explicitly run `git config user.name/email` in that worktree before the first
commit, so it silently inherited whatever ambient/global git config was
active. The push then failed with `remote:
error: GH007: Your push would publish a private email address`.

Fix that avoided any destructive history rewrite (both `git filter-branch`
and `git reset --soft` were blocked by the classifier as expected): generate
a combined diff of the mis-authored commits (`git diff --binary
origin/<branch>...HEAD`, and `--binary` is not optional: this repository tracks
PNG assets, and without it `git apply` fails on any commit that touched one),
create a fresh branch from `origin/<branch>`, `git apply` the diff, set the
worktree's identity explicitly, and commit once under it. Purely additive: no rewrite of anything that had
ever reached the remote, since the original push had never succeeded.

Takeaway: read `git config user.name` and `git config user.email` as the FIRST
action in any newly created worktree, before the first commit, rather than
discovering the gap at push time. They must resolve to the identity that owns
the push, using the address GitHub accepts for that account, which is the
`users.noreply.github.com` form when the account keeps its email private. Do
not hard-code an agent identity as the commit author: `.claude/rules/universal.md`
asks only for a `Co-Authored-By:` trailer for agent attribution, and its
MUST list states that git identity cannot prove a human acted.

Scope the write. Plain `git config user.email <addr>` writes `.git/config`,
which every linked worktree shares, so setting it in one worktree changes the
author identity under all the others mid-session. Use `git config --worktree`,
which needs `extensions.worktreeConfig` enabled on the clone and otherwise
exits 128 with `--worktree cannot be used with multiple working trees unless
the config extension worktreeConfig is enabled`. Enable it once with `git
config extensions.worktreeConfig true`. `scripts/validation/check_repo_health.py`
documents the same per-scope distinction for `core.bare`.

## Split out of this file

Two observations from the same session were moved to their own memories, so
index recall can reach them and so a correction to either does not touch this
file:

- [ci/ai-spec-validator-verdicts-flip-flop-across-reruns](../ci/ai-spec-validator-verdicts-flip-flop-across-reruns.md)
- [workspace/gc-worktrees-report-then-apply](../workspace/gc-worktrees-report-then-apply.md)
