## Dangerous assumptions

- "`instructions/` mirrors `.claude/rules/`": since ADR-109 B2 the generator source is `src/claude/rules/`; the canonical edit is `templates/rules/<name>.md`.
- "`binplace.yaml` has a `prompts` row, so `build_all.py` writes `prompts/`": that row's `plugin_tree` is null, so binplace skips it.
- "`instruction-budget.yml` caps root `AGENTS.md`/`CLAUDE.md`": it gates the always-on rule corpus. Root doc cap is `passive-context-budget.yml`.
- Green `validate-generated-agents.yml` or `agent-drift-detection.yml` on a PR touching no agent file proves nothing: both skip behind a paths filter, and the latter on `[skip-drift-check]` in any commit message.
