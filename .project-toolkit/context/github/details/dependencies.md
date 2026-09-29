## Dependencies

- Agent render map: `templates/AGENTS.md`. Generator order, `OWNED_PREFIXES`, binplace, drift and parity semantics: `build/AGENTS.md`; `build_all.py --check` in `Validate Generated Files` is the stale-tree gate.
- `adr006_run_block_scanner.py` runs in neither `pre_pr.py` nor lefthook; a green `pre_pr.py` does not predict `Validate PR`. `tests/validation/test_pre_pr_covers_workflow_validators.py` fails when a pull-request workflow runs a `scripts/validation/` validator that no gate or exemption covers.
- `instructions/` and `copilot-instructions.md` reach Copilot only; Claude Code reads `.claude/rules/`. Cloud Copilot loads only default-branch `hooks/*.json`.
