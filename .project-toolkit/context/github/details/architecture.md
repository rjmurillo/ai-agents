## Architecture

- `generate_rules.py` renames `paths:` to `applyTo:`, drops `priority:`/`alwaysApply:`, skips all-internal rules from `src/copilot-cli/instructions/` (issue #4317) and writes them to `instructions/`.
- `prompts/pr-quality-gate-*.md`: one-way edge from `.claude/skills/review/references/`, outside `build_all.py --check`. Stale output blocks at lefthook `review-axis-drift` and the `Review-axes drift check` step.
