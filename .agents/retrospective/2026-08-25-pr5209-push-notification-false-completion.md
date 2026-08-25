# Retrospective: pr5209-push-notification-false-completion

## Session Info

- **Date**: 2026-08-25
- **Agent**: Claude Code (Claude Sonnet 5), continuing work on branch `claude/autoplan-goal-1ewz33`, driving the sibling PR #5209 branch `claude/adr-evaluation-tooling-6od8rd` toward mergeable via an external worktree, per the user's explicit "attempt to drive #5209 to mergeable" instruction (issue #5192, dangling ADR supersessions).
- **Task Type**: Resolve a merge conflict between `origin/main` and `claude/adr-evaluation-tooling-6od8rd` in `tests/ci/test_validate_vendor_provenance.py`, then push the merge commit so PR #5209's CI re-runs against a mergeable head.
- **Outcome**: Merge conflict resolved and committed locally (`59f7fa869`) in an earlier turn. Two separate push attempts for this commit were launched as backgrounded Bash tasks across a context-compaction boundary. Both task notifications reported "completed (exit code 0)". Neither push actually landed; `origin/claude/adr-evaluation-tooling-6od8rd` remained at the pre-merge commit (`dd20f49d3`) until a third, explicitly-verified push in this session.

## Phase 1: Insights Generated

### Finding 1: Background-task "exit code 0" reflects the wrapper shell's exit code, not the wrapped git command's

**What happened**: Two prior turns launched `flock ... git push origin <branch> > logfile 2>&1; echo "exit=$?"` as backgrounded Bash commands. Both returned task notifications reading `completed (exit code 0)`. Taken at face value, this reads as "the push succeeded." After the context-compaction boundary, a fresh `git fetch` + `git log` comparison against `origin/claude/autoplan-goal-1ewz33` and separately against `origin/claude/adr-evaluation-tooling-6od8rd` showed both branches were still behind their expected local HEADs by several commits. Reading the actual log file contents (not the notification summary) for one of the two prior attempts showed `exit=1` on its last line, and the fuller log showed the real failure: a lefthook pre-push job (`pre-pr-validation`'s `Skill Markdown Portability` check on the first branch; `retrospective-policy` on this one) had failed, so `git push` itself exited non-zero.

**Root cause**: The backgrounded command's structure is `flock ... git push ... > logfile 2>&1; echo "exit=$?"`. The tool-level "exit code" reported in the task notification is the exit status of the *entire backgrounded shell invocation*, and the invocation's last command is the `echo`, which always exits 0 regardless of what `git push` did. The real `git push` exit status was captured inside the log file as text (`exit=$?`), one line the notification summary does not surface. Trusting the notification instead of grepping the log for that line, or for `error:`, is the gap.

**Cost**: This session spent one push cycle per branch, plus a full context-compaction interruption, believing pushes had succeeded when they had not. The goal-tracking Stop hook correctly kept blocking session termination on "unpushed commits," which is what surfaced the discrepancy, but only after re-fetching and diffing SHAs directly rather than trusting either the notification or the prior turn's own stated belief.

**Classification**: FAILURE-MODES.md #4, False Completion Markers. "Success is reported in prose instead of verified against an artifact" matches exactly: the notification's prose summary ("completed (exit code 0)") was treated as the artifact, when the actual artifact (the log file's final `exit=` line, or a fresh `git log` comparison against the remote) told a different story both times.

## Phase 2: Remediation

1. **For any backgrounded push (or any command whose exit code matters), append the real exit code as the LAST line of the log file itself** (`echo "GIT_PUSH_REAL_EXIT=$?" >> "$LOGFILE"`), and grep that line specifically before treating the operation as done. This was adopted for the two pushes later in this same session and both were then verified accurately: one genuinely succeeded (`GIT_PUSH_REAL_EXIT=0`, confirmed by fetch+SHA comparison), the other genuinely failed (`GIT_PUSH_REAL_EXIT=1`, root-caused to this gate and fixed).
2. **Never treat a task-notification summary as proof of a git operation's outcome.** Re-fetch and compare `git log --oneline -1 origin/<branch>` against the intended local SHA after every push, regardless of what the notification claims.
3. **Filed as issue #5301.** A session-spanning worktree push, driven from a different git identity/branch than the one that produced the session's own retrospective file, has no automatic way to satisfy `_today_retrospective_exists` without a same-day retrospective file present on *that specific branch's working tree*. This is expected behavior given `retros.md`, not a bug, but it is easy to miss when the work is a mechanical merge-conflict resolution rather than a feature change. Issue #5301 owns clarifying the documentation and evaluating whether the gate itself should be widened.

## Evidence

- Local commit `59f7fa869` ("Merge remote-tracking branch 'origin/main' into claude/adr-evaluation-tooling-6od8rd") predates this retrospective by roughly two turns and one context-compaction boundary.
- First failed push attempt's log (`/tmp/push-5286-fix4.log`, for the sibling branch `claude/autoplan-goal-1ewz33`) ended with `exit=1` on the last line despite a `completed (exit code 0)` notification; the underlying lefthook failure was `[FAIL] Skill Markdown Portability`.
- Second failed push attempt for this branch (`claude/adr-evaluation-tooling-6od8rd`) failed at lefthook's `retrospective-policy` job with `ERROR: git push requires retrospective evidence for this session`, which this file exists to satisfy.
- `git merge-base --is-ancestor origin/claude/adr-evaluation-tooling-6od8rd HEAD` returned true (origin was a strict ancestor of local HEAD, confirming a clean fast-forward was pending, not a divergence) immediately before the corrected push.

## No Blame

This is a mechanism-level finding about how backgrounded Bash task notifications compose with `; echo "exit=$?"`-style status capture, not an individual failure. The fix (assert the wrapped command's real exit status as the last line of its own log, and verify via `git log`/`git fetch` rather than the notification) is a durable habit change applicable to any backgrounded shell command whose downstream success matters, not specific to this branch or this PR.
