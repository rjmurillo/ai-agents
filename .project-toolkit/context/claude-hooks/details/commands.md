## Commands

Run only in the `rjmurillo/ai-agents` checkout, not a consumer install.

```bash
# Regenerate, then drift-check.
uv run python build/scripts/build_all.py
uv run python build/scripts/hook_templates.py --validate

echo '{}' | uv run python -u .claude/hooks/invoke_dispatch_claude.py --group sessionstart-1-context_loader

# --ci exits nonzero on a violation.
uv run --frozen python scripts/validation/hook_contracts.py --ci
uv run --frozen python scripts/validation/pre_pr.py
```
