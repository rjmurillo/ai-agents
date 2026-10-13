# Skill: uv cache cleanup breaks or hangs with uvx MCP servers running (90%)

## Statement

`uv cache clean` waits forever on `~/.cache/uv/.lock` while long-lived uvx MCP servers run. Serena and pyright-langserver hold that lock for their whole lifetime.

`uv cache prune --force` is not safe either. On 2026-10-13 it removed 33.2GiB, including the ephemeral uvx environments the running Serena servers loaded from (`archive-v0/<hash>/lib/python3.14/site-packages`). The servers kept running, but lazy imports failed (`ModuleNotFoundError: serena.repl.api.lsp_api`). That broke Serena symbol tools in three sessions.

## Safe order

1. Stop the uvx MCP servers, or plan to reconnect them afterwards.
2. Run `uv cache clean` (or prune).
3. Re-warm with `uvx --from git+https://github.com/oraios/serena python -c "import serena"`.
4. Reconnect the MCP servers with `/mcp`.

Find a running server's environment with `grep site-packages /proc/<child-pid>/maps`.

## Source

2026-10-13 issue sweep, disk exhaustion recovery.
