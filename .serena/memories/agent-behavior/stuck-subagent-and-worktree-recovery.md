# Stuck-subagent and worktree-identity recovery patterns

Captured via `reflect` after a P1-batch fix session, 2026-08-27. Self-approved
(unattended run, no human present for the skill's normal Y/n gate) per the
standing autonomous-operation directive; confidence labels below follow the
skill's own HIGH/MED tiers.

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
revealed a much older commit than expected. Recovery: `git reset --hard HEAD`
before doing anything else with the polluted state.

Takeaway: before `git checkout <ref> -- <path>` or any ref-based read in a
worktree that might have accumulated stale local branches (common in a
long multi-agent session), disambiguate with `git log -1 --oneline
origin/<branch>` first, or use the fully-qualified `origin/<branch>` form
directly instead of the bare branch name.

## [HIGH] A push rejected with GH007 (private email) mid-session means the worktree's git identity was never set

Three commits made in a scratch worktree carried `Richard Murillo
<rjmurillo@gmail.com>` (the account owner's real, GH007-protected email)
instead of the session's established `Claude <noreply@anthropic.com>`
identity, because nothing had explicitly run `git config user.name/email` in
that worktree before the first commit: it silently inherited whatever
ambient/global git config was active. The push then failed with `remote:
error: GH007: Your push would publish a private email address`.

Fix that avoided any destructive history rewrite (both `git filter-branch`
and `git reset --soft` were blocked by the classifier as expected): generate
a combined diff of the mis-authored commits (`git diff
origin/<branch>...HEAD`), create a fresh branch from `origin/<branch>`, `git
apply` the diff, set `git config user.name/email` explicitly, and commit once
under the correct identity. Purely additive: no rewrite of anything that had
ever reached the remote, since the original push had never succeeded.

Takeaway: set `git config user.name "Claude"` and `git config user.email
"noreply@anthropic.com"` explicitly as the FIRST action in any newly created
worktree, before the first commit, rather than discovering the gap at push
time.

## [MED] The AI-Spec-Validator's verdict flip-flops across reruns of the same disclosed gap

On two different PRs (#5350, #5356), successive re-runs of the `Validate Spec
Coverage` check against the same or adjacent commits produced different
top-line verdicts (PASS, then FAIL, then PARTIAL) for the identical
underlying, already-disclosed gap (an unverified live-CLI probe on #5350; a
prompt-only vs. enforced-control distinction on #5356). The gap itself never
changed; only the validator's characterization of its severity did.

Takeaway: a single FAIL from this validator is not authoritative on its own.
Cross-reference the PR's own body/tests for whether the gap is already
disclosed and tracked before treating a FAIL as a new, actionable finding.
Comment once on the PR explaining the disclosed gap and its tracking issue;
do not chase every re-verdict with a new comment (already the established
practice: this just adds the "why" for future sessions).

## [MED] `scripts/maintenance/gc_worktrees.py --apply` is a fast, low-risk way to shrink OOM-affected worktree counts

Report mode first (`--json`, no `--apply`) correctly classified 16 of 42
registered worktrees as safely removable ("fully pushed"); `--apply` removed
exactly those with zero side effects. For the remaining "would have removed,
but its admin directory is the only anchor for work (fully pushed)" entries,
the tool's own suggested `git branch gc-rescue-<sha> <sha>` command before
`git worktree remove --force <path>` is a correct, cheap safety net. The
rescue branch is redundant once the SHA is confirmed already on origin, but
costs nothing to create.
