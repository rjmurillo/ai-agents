# session-end targets the main checkout, not the linked worktree

`.claude/skills/session-end/scripts/complete_session_log.py` cannot complete a
session log that lives in a linked git worktree. Observed 2026-07-31 while
shipping the issue #3978 fix from
`.claude/worktrees/wf_05a58069-a28-4`.

## What happens

`_get_repo_root` at `complete_session_log.py:76-90` resolves the root from
`git rev-parse --git-common-dir`:

```python
result = subprocess.run(
    ["git", "rev-parse", "--git-common-dir"],
    capture_output=True, text=True, timeout=10, check=False,
)
...
return str(git_common.parent)
```

In a linked worktree `--git-common-dir` points at the MAIN checkout's `.git`,
so `git_common.parent` is the main checkout. Two consequences:

1. **Auto-detect picks the wrong file and writes to it.** With no
   `--session-path`, the script found
   `<main>/.agents/sessions/2026-07-31-session-3878-fix-lint-suppression-policy.json`,
   a log belonging to a different branch, and mutated it in the main worktree.
   Recovered with `git checkout --` in the main checkout.
2. **`--session-path` is rejected.** The containment check refuses any path
   outside the resolved sessions dir:
   `[FAIL] Session path must be inside '<main>/.agents/sessions'.`
   So the correct log in the linked worktree can never be passed in.

## Workaround

Fill `protocolCompliance.sessionEnd` by hand in the worktree's log, then run the
canonical validator directly, which has no containment check:

```bash
uv run python scripts/validate_session_json.py .agents/sessions/<log>.json
```

## Second defect seen in the same run

The auto-detected run wrote
`sessionEnd.reworkWarning.Evidence` as a list and the schema rejected it:

`Schema: protocolCompliance.sessionEnd.reworkWarning: {'level': 'SHOULD',
'Complete': True, 'Evidence': ['rework-warning: none']} is not valid under any
of the given schemas`

`Evidence` must be a string. `complete_session_log.py:433` assigns the list
from `rework_evidence` without joining it.

## Fix direction

Anchor on `git rev-parse --show-toplevel` (the current worktree) rather than
`--git-common-dir`, per `.claude/rules/ci-scripts.md` MUST 7 and MUST 8, and
join `rework_evidence` into a string before assignment.
