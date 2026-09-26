## Dangerous assumptions

- A green `detect_agent_drift.py` proves nothing about `src/vs-code-agents/` parity: its code default `--claude-path` is `src/claude`, not `src/claude/agents` (its `--help` claims otherwise), so it compares 0 of 31 agents. The `Agent Drift Detection` gate runs it bare. Pass `--claude-path src/claude/agents`.
- `git add` silences the `src/` staleness gate and proves nothing; commit.
