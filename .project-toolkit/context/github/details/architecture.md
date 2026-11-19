## Architecture

- `generate_rules.py` renames `paths:` to `applyTo:`, drops `priority:`/`alwaysApply:`, skips all-internal rules from `src/copilot-cli/instructions/` (issue #4317) and writes them to `instructions/`.
