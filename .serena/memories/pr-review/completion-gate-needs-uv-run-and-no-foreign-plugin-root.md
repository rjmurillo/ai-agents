# run_completion_gate.py fails three ways that look like a bad PR

## What happens

`run_completion_gate.py` reports a failed gate for causes that have nothing to do with the PR. Each one reads as a real verdict unless you check the reason string.

1. **Bare `python3` has no PyYAML.** The script exits 2 and prints `PyYAML is required to parse the completion-gate config`. Run it as `uv run --frozen python .claude/skills/github/scripts/pr/run_completion_gate.py --pull-request N`. A sweep child claimed bare `python3` exits 0 on this error. That was wrong. Re-tested 2026-11-11: exit 2 with the message above.
2. **A foreign `CLAUDE_PLUGIN_ROOT` redirects the gate's own commands.** `_expand_plugin_root` takes the first non-empty `COPILOT_PLUGIN_ROOT` or `CLAUDE_PLUGIN_ROOT` and does not check that the root holds the script. The context-mode plugin exports its own root inside `ctx_execute`. The criteria then fail with `can't open file '<root>/skills/github/scripts/pr/...'`.
3. **"config not trusted (diverged)" means the config bytes differ from the trusted ref.** When the PR branch is only behind `origin/main` and `main` changed verifier files, merging `origin/main` into the branch clears it. When the PR itself edits the gate config, merging does not clear it. That needs a human to inspect the diff and re-run with `--approve-untrusted-config` (ADR-101). Agents must not pass that flag.

## Practice

Run the gate in plain Bash with the foreign root removed:

```bash
env -u CLAUDE_PLUGIN_ROOT uv run --frozen python .claude/skills/github/scripts/pr/run_completion_gate.py --pull-request N --json
```

Read the `reason` of each failed criterion before deciding the PR is not ready.

## Evidence

- OBSERVED 2026-11-11 on PR 7316, same checkout, same command. With `CLAUDE_PLUGIN_ROOT=/nonexistent/plugin` the thread criterion failed with `can't open file '/nonexistent/plugin/skills/github/scripts/pr/get_unresolved_review_threads.py'`. With the variable removed, the same criterion passed.
- `run_completion_gate.py` lines 1605 to 1630 (`_PLUGIN_ROOT_FORMS`, `_expand_plugin_root`) and lines 95 to 135 (trust outcomes and `--approve-untrusted-config`).
- Issue 7281 tracks the foreign-root flaw. PR 7318 is the open fix at 2026-11-11. When it merges, item 2 no longer applies.
- `CLAUDE_PLUGIN_DATA` is not read by the gate. The sweep log suggested unsetting it too. No code path in the gate uses it, so it is not needed.

## Relations

- **related_to**: [github-skill/new-issue-agent-source-needs-blocked-by-and-signal](../github-skill/new-issue-agent-source-needs-blocked-by-and-signal.md)
