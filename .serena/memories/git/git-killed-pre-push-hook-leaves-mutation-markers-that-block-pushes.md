# A killed pre-push hook leaves mutation markers that block the next push

## What happens

The mutation test harness writes a marker file under `.git/worktrees/<name>/mutation-active/` while it works. The directory name is `MARKER_DIRECTORY_NAME` in `scripts/testing/mutation_workspace_git.py` (line 17). If the hook is killed mid-run, the marker stays. The next push then fails with "incomplete mutation harness state; push blocked."

## Clear it

The failure text prints the fix (`scripts/testing/mutation_workspace.py`, line 408):

```bash
uv run --frozen python -m scripts.testing.mutation_workspace recover
```

Run it after the mutation process has stopped. It removes each leftover scratch worktree and marker.

## Two habits that hide the cause

- Send push output to a log file and read it whole. Piping through `tail` drops the lines that name which hook failed.
- Do not wrap `git push` in `timeout`. A timeout kill is how the stale marker is made.

## Sources

- `scripts/testing/mutation_workspace.py` lines 398 to 412 and 428 to 480 (`recover_marker`, `recover_markers`, the `recover` command).
- `scripts/testing/mutation_workspace_git.py` line 17.
- Observed during the 2026-10-11 parallel-agent sweep.
