# Session 4041: session-end auto-detect resolved outside the worktree

Branch: `fix/merge-resolver-base-ref`. Issue: #4058.

## What happened

I ran `uv run python .claude/skills/session-end/scripts/complete_session_log.py`
from inside the linked worktree at
`.claude/worktrees/wf_bf35d506-d78-5`. The script printed:

```text
Auto-detected session log: /home/richard/src/GitHub/rjmurillo/ai-agents2/.agents/sessions/2026-07-31-session-3878-fix-lint-suppression-policy.json
```

That path is in the main checkout, not the worktree. The script then rewrote
that file: it flipped `sessionEnd.validationPassed` from `true` to `false`,
replaced four evidence strings, turned `reworkWarning.Evidence` from a string
into a list, and stripped the trailing newline. The log it damaged belongs to a
different branch and a different session. `git restore` put it back.

## Why it matters

The write happened before the script validated anything, and the only signal
that it had picked the wrong file was one line of stdout that reads like normal
progress output. An agent that skims that line ships a corrupted session log on
someone else's branch, and the corruption looks like a legitimate edit in
`git diff`.

## Root cause

The auto-detect walks a sessions directory resolved from the script location or
a repository root that is not the current worktree. `.claude/rules/ci-scripts.md`
MUST 7 already states the rule this violates: a script that resolves a
repository root and then writes to it must confirm the current directory is
inside the resolved root before the first write. The session-end script writes
first and checks nothing.

## What to do instead

Pass `--session-path` explicitly when running `complete_session_log.py` from a
linked worktree. Do not trust the auto-detect line.

## Follow-up

Worth an upstream issue against the session-end skill: make the auto-detect
anchor on `git rev-parse --show-toplevel` for the invoking worktree, and fail
closed when the resolved log sits outside it.

## Learnings captured

- A progress line that names a path is a claim, not a confirmation. Read it.
- A skill that writes before it validates turns a wrong-target bug into data
  loss on an unrelated branch.
