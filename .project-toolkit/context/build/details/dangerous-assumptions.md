## Dangerous assumptions

- Older docs mention `scripts/sync_plugin_lib.py` as a first step. It is retired (issue #5790). `build_all.py` is the whole sequence; there is no order to get wrong.
- A red `--check` means the source changed, not that the output needs a hand-edit; exit 2 has five producers, only staleness clears by regenerating.
- Raising `--similarity-threshold` (default 80) to clear a red defeats the gate.
- `build/sync_slim_agents.py` is not a generator; `build_all.py` never calls it and `--write` copies rendered bodies backwards into `templates/agents/*.shared.md` and `.github/agents/`. Do not run it.
