## Architecture

- `generate_rules.py` writes both mirrors in one run, renaming `paths:` to `applyTo:` and dropping `priority:`/`alwaysApply:`: `instructions/` keeps every rule (28), `src/copilot-cli/instructions/` drops rules whose globs are all internal-only (22, issue #4317). Counts are not meant to match.
- `prompts/pr-quality-gate-*.md`: one-way edge from `.claude/skills/review/references/`, outside `build_all.py --check`. Stale output blocks at lefthook `review-axis-drift` and the `Review-axes drift check` step.
