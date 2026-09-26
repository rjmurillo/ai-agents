## Commands

```bash
uv run python build/scripts/build_all.py                    # render all + binplace
uv run python build/scripts/build_all.py --check            # CI drift gate
uv run python build/scripts/agent_templates.py --validate
uv run python build/scripts/rule_templates.py --validate
uv run python build/scripts/hook_templates.py --validate
uv run python build/scripts/generate_skills.py --validate
uv run python build/scripts/validate_templates_schema.py
uv run python build/generate_agents.py --what-if
```
