## Entry points

- `uv run python scripts/validation/pre_pr.py` (`--quick`, `--markdown-lint-only`, `--summary-json PATH`).
- `uv run python scripts/validation/git_hook_policy.py <subcommand>` (argparse subparsers; `--help` lists them).
- `uv run python scripts/check_skill_exists.py --operation <op> --action <name>`, or `--list-available`.
- `uv run python scripts/new_validated_pr.py` wraps the `github` skill's `new_pr.py`.
- `uv run python scripts/run_with_receipt.py run -- CMD ARGS` contains large command output behind a bounded receipt; `read ARTIFACT --offset N --length N` pages the saved file. Opt-in only; no tool-use hook may do this (ADR-097).
- `uv run python scripts/sync_mcp_config.py --sync-all` writes `.factory/mcp.json` and `.vscode/mcp.json` (`--dry-run`, `--force`).
