# Eval billing matrix (harness x billing)

`scripts/eval/_billing_matrix.py` is the 3x2 table the eval transport layer dispatches through: harness (`claude`, `codex`, `copilot`) crossed with billing (`api` = a metered vendor account, `subscription` = a seat reached by shelling out to that vendor's CLI). It is pure data plus lookup and imports nothing else in the harness, which is what lets `_providers` dispatch and `_eval_common.cost_basis` classify from one table.

## The six cells

| Harness | Billing | Provider name | Credential | Basis |
|---|---|---|---|---|
| claude | api | `anthropic` (urllib default), `anthropic-sdk` | `ANTHROPIC_API_KEY` | usd |
| claude | subscription | `claude-cli` | `CLAUDE_CODE_OAUTH_TOKEN` | requests |
| codex | api | `openai`, `codex` | `OPENAI_API_KEY` | usd |
| codex | subscription | `codex-cli` | `codex login` under `CODEX_HOME`, or `CODEX_ACCESS_TOKEN` | requests |
| copilot | api | `copilot-api` | `COPILOT_API_KEY` plus a required `COPILOT_API_BASE_URL` | requests |
| copilot | subscription | `copilot-cli` | CLI login | requests |

## Apply when

Adding a transport, choosing what a run costs, or wondering why a provider name means what it means. Legacy names keep their old meanings exactly, so no archived command changes what it runs.

## Load-bearing decisions

- **A subscription cell strips the metered credentials from the child process.** Claude Code's documented precedence puts `ANTHROPIC_API_KEY` above `CLAUDE_CODE_OAUTH_TOKEN` and its docs say the key is always used in `--print` mode when present; Codex reads `CODEX_API_KEY` and can reach `OPENAI_API_KEY` through a provider config. Without stripping, an operator with a key exported gets an API-billed run out of the subscription column and nothing in the report says so.
- **claude/api is not a registry row.** `claude-api` is an alias in `DEFAULT_ANTHROPIC_NAMES`, so it stays byte-for-byte on the urllib path and no checked-in baseline moves.
- **copilot/api has no default endpoint and refuses to run without one.** GitHub documents no public inference API billed apart from a Copilot seat; `api.githubcopilot.com/chat/completions` is live but undocumented for third parties and its headers are community-observed. GitHub Models, which used to fill this cell, returned HTTP 410 when re-probed 2026-09-16. `COPILOT_API_BASE_URL` and optional `COPILOT_API_HEADERS` (a JSON object) are the seam.
- **`registry_classification_gaps()` fails a test, not an import**, when a `_REGISTRY` row has no cell. That is the guard against the defect where `copilot-cli` was absent from the quota set and a subscription CLI quoted a Claude Sonnet token rate.
- **Model attribution differs per cell.** `copilot-cli` reads its session transcript, `claude-cli` reads `modelUsage` from `--output-format json` (measured 2026-09-16 on CLI 2.1.273: an alias yields two keys, the alias and the resolved dated id, so every key must belong to the requested family rather than there being exactly one), `codex-cli` has none and refuses until `EVAL_CODEX_ALLOW_UNVERIFIED_MODEL=1`.
- **Status is evidence, not intent.** Only claude/api and copilot/subscription are `VERIFIED`. The rest are implemented and covered offline; no live run through them is recorded.

## Preflight

`uv run python scripts/eval/eval_billing_matrix.py` prints the table plus per-cell readiness, `--json` for machines, `--require-ready` exits 3. It reads variables and PATH only, so `UNKNOWN` is the answer for a cell whose credential can come from a CLI login on disk.

Evidence: branch `claude/eval-harness-billing-matrix-gf0sqv`, files `scripts/eval/_billing_matrix.py`, `_cli_transport.py`, `_claude_cli.py`, `_codex_cli.py`, `_http_providers.py`, `eval_billing_matrix.py`; tests `tests/eval/test_billing_matrix.py`, `test_cli_transport_helpers.py`, `test_claude_cli_provider.py`, `test_codex_cli_provider.py`, `test_eval_billing_matrix_cli.py`.
