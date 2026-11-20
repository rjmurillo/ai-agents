## Commands

```bash
uv run python build/scripts/build_all.py
uv run python build/scripts/build_all.py --check
# Agents only: --validate, --what-if.
uv run python build/generate_agents.py
uv run python build/scripts/detect_agent_drift.py
uv run python scripts/validation/pre_pr.py
```
