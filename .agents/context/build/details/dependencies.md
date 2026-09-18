## Dependencies

- `generate_pr_quality_prompts.py`: `.claude/skills/review/references/<role>.md` -> `.github/prompts/pr-quality-gate-<role>.md`; `--dry-run` is the drift form (`run_drift_check_ci.py`); `binplace.yaml`'s `prompts` row only documents it.
- Lefthook regen jobs glob only `templates/agents/*.shared.md` and `templates/platforms/**`; a `.tmpl` or `partials/*.mustache` edit auto-regenerates nothing.
