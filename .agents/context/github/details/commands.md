## Commands

```bash
uv run python scripts/ci/adr006_run_block_scanner.py --max 0
uv run python scripts/validate_workflows.py
uv run python build/scripts/generate_rules.py
uv run python build/scripts/generate_pr_quality_prompts.py --dry-run
uv run python build/scripts/build_all.py --check
uv run python scripts/validate_workspace_budget.py
uv run python -m scripts.validation.passive_context_budget --ci
uv run python -m scripts.validation.instruction_budget --ci
uv run python scripts/validation/pre_pr.py
```
