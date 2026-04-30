Confirmed bug. The original hook at `.claude/hooks/invoke_routing_gates.py` uses `parents[1]` correctly because its sibling lib lives at `.claude/lib/`. After the generator copies it to `src/copilot-cli/hooks/preToolUse/<name>.py` (one extra directory level deep), `parents[1]` = `src/copilot-cli/hooks/`, not `src/copilot-cli/`. The suggested `parents[2]` would compute the right path -- but `src/copilot-cli/lib/` is not generated either, so the hook would still fail.

Two-part fix needed (out of scope for current commits, both real bugs):
1. **Generator must rewrite path-resolution depth** when copying hooks to a deeper directory, OR generate a stable shim that resolves lib via the plugin manifest location (e.g., walk upward looking for `.claude-plugin/plugin.json`).
2. **Generator must ship `lib/`** to `src/copilot-cli/lib/` for the runtime to find `hook_utilities.guards`. Today only the `hooks/` and `agents/` subtrees are emitted.

Without (2), even fixing (1) produces hooks that fail at first import. Both should land before the marketplace flip is real-world usable. Tracking as M7 follow-up. Leaving unresolved.
