## Commands

```bash
uv run pytest tests/ -x
uv run python scripts/validation/git_hook_policy.py pytest
AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1 uv run python scripts/validation/git_hook_policy.py pytest
uv run python scripts/validation/pre_pr.py
uv run python scripts/validation/check_zero_collection_tests.py
uv run python scripts/validation/check_nested_tests.py
uv run python scripts/validation/check_colocated_skill_tests.py
grep -rno 'tests/[A-Za-z0-9_/]*\.py' .github/workflows/
cd packages/ai-agents-cli && bun test
```
