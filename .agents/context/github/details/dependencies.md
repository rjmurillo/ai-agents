## Dependencies

- Agent render map: `templates/AGENTS.md`. Generator order, `OWNED_PREFIXES`, binplace, drift and parity semantics: `build/AGENTS.md`; `build_all.py --check` in `Validate Generated Files` is the stale-tree gate.
- `adr006_run_block_scanner.py` and `check_python3_entrypoints.py` run in neither `pre_pr.py` nor lefthook; a green `pre_pr.py` does not predict `Validate PR`.
- `instructions/` and `copilot-instructions.md` reach Copilot only; Claude Code reads `.claude/rules/`. Cloud Copilot loads only default-branch `hooks/*.json`.
