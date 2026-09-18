## Entry points

- `uv run python scripts/validation/pre_pr.py` (`--quick`, `--markdown-lint-only`, `--summary-json PATH`).
- `uv run python scripts/validation/git_hook_policy.py <subcommand>` (argparse subparsers; `--help` lists them).
- `uv run python scripts/check_skill_exists.py --operation <op> --action <name>`, or `--list-available`.
- `uv run python scripts/new_validated_pr.py` wraps the `github` skill's `new_pr.py`.
- `uv run python scripts/sync_mcp_config.py --sync-all` writes `.factory/mcp.json` and `.vscode/mcp.json` (`--dry-run`, `--force`).
- `uv run python scripts/detect_scope_explosion.py`: advisory (ADR-100 item 3), 0 at every tier, 2 on error.
