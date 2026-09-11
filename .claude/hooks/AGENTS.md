# .claude/hooks/

Claude Code lifecycle hooks for this plugin root; consumed by the Claude Code harness at runtime and by the generator that mirrors a subset of this tree into the Copilot CLI plugin.

## Matters

- Only `SessionStart` uses the group dispatcher today: three of its four `.claude/settings.json` entries call `invoke_dispatch_claude.py --group <id>`, with membership in `dispatch_groups.json`. `UserPromptSubmit`, `SessionEnd`, and `PreCompact` each register their one script directly (no `--group`, no dispatcher). Every existing group currently holds exactly one shim; the design supports N shims sharing one process, but nothing here exercises N>1 yet.
- `hooks.json` (the plugin-shipped manifest, distinct from `.claude/settings.json`) currently declares `"hooks": {}`. Nothing here ships to a plugin consumer today; every live registration below is this repository's own dev-time convenience, wired through `.claude/settings.json` only.
- Zero tool-use hooks exist. `PreToolUse` and `PostToolUse` carry no Python hook script (only a shared bootstrap helper and a markdownlint config). Adding one is a deliberate, reviewed act, not a drop-in file; see Constraints.
- Every hook here is fail-open by design: an unhandled exception, a missing dependency, or a broken plugin install must degrade to allowing the session/turn, never block it. The dispatcher's `gate`/`gate_all` modes are the design's one fail-closed path, reserved for a future `PreToolUse`/`UserPromptSubmit` group; no group registered today uses them.
- `SessionStart`, `UserPromptSubmit`, `SessionEnd`, `PreCompact` are the only registered events. They fire once per session or turn, not once per tool call, so the cost/blast-radius bar in `tool-use-hook-bar.md` does not apply to them.
- Several hooks (`invoke_memory_recall.py`, `invoke_memory_reflection.py`) are thin invokers for a package that lives outside the plugin root and does not ship with it; on a consumer install they silently no-op.

## Entry points

- `.claude/settings.json` `hooks` block: the actual event wiring (timeouts, statusMessage, which group fires).
- `invoke_dispatch_claude.py --group <id>`: the process a grouped registration launches; reads `dispatch_groups.json` for that group's shim list and `mode`.
- `session-start.sh`: separate from the group dispatcher; gated on `$CLAUDE_CODE_REMOTE`, delegates to the container bootstrap script in the `rjmurillo/ai-agents` repository.
- A single `invoke_*.py` under an event directory can be run standalone for manual testing (it does not require the dispatcher).

## Where to look

| Path | Why |
|---|---|
| `.claude/settings.json` | Real event/timeout/group wiring; the source of truth for what fires and when |
| `dispatch_groups.json` | Group-to-shim membership; `mode` per group (all three registered groups are `observe` today; `gate`/`gate_all` are supported but unused here) |
| `hooks.json` | Plugin-shipped manifest; currently empty, read this before assuming a hook ships |
| `invoke_dispatch_claude.py` | Dispatcher entry point; self-hosting double-fire guard; exit-code contract |
| `.claude/lib/claude_hook_dispatch.py` | Group-runner semantics: gate/gate_all/observe modes, stdout merge rules |
| `.claude/lib/claude_hook_protocol.py` | Strict classification of a shim's stdout into context vs. blocking decision |
| `.claude/lib/hook_utilities/guards.py` | `skip_if_consumer_repo()`; git-origin-based project-vs-consumer repo detection |
| `.claude/lib/hook_utilities/path_safety.py` | CWE-22 traversal guard used by plugin-distributed scripts |
| `.claude/rules/tool-use-hook-bar.md` | The bar a new `PreToolUse`/`PostToolUse` registration must clear; states the current zero-hook baseline |
| `.claude/rules/generated-artifacts.md` | Runtime-contract rules for any customer-facing generated hook artifact |
| `SessionStart/plugin_hook_drift_*.py` | The installed-vs-source hook drift comparator (split model/report/safety/state) |

## Skip

- `__pycache__/` under any hook directory: gitignored bytecode, never a source.
- `.claude/hooks/CLAUDE.md` and the stubs under `PostToolUse/`, `PreCompact/`, `PreToolUse/`, and `SessionStart/`: claude-mem auto-context stubs with no authored content. `SessionEnd/` and `UserPromptSubmit/` carry no such stub.
- `PostToolUse/README.md`: a hook-authoring template for a hook class that currently ships zero scripts; useful only if you are adding the first one back.
- `PreToolUse/_bootstrap.py`: shared plugin-path bootstrap for a future tool-use guard; not imported by any hook that ships today. Dead until a new `PreToolUse`/`PostToolUse` hook is added.
- `PreToolUse/markdownlint-safe-config.yaml`: static config data, not a hook script.

## Constraints

- Adding a `PreToolUse`, `PostToolUse`, `PermissionRequest`, or `PostToolUseFailure` registration must clear every MUST in `tool-use-hook-bar.md` and is pinned closed by a re-accretion ratchet in the `rjmurillo/ai-agents` repository's runtime-contract test suite; that test also asserts `hooks.json` here and the generated Copilot mirror both stay at zero.
- The group runner supports three modes even though every group registered today is `observe`: `gate` (`PreToolUse`) is fail-closed and stops at the first shim that emits a validated block, `gate_all` (`UserPromptSubmit`, `Stop`, `SubagentStop`) runs every shim but returns the first blocking exit seen, `observe` (`SessionStart`, `PostToolUse`, `PreCompact`) always runs every shim and always returns allow. A registered shim missing on disk or an unexpected dispatch exception denies in `gate`/`gate_all`, logs and continues in `observe`.
- A shim's whole stdout is treated as a blocking decision only for a strictly validated shape per event (`claude_hook_protocol.py`); anything else, including malformed JSON that looks like a decision, is either suppressed (`observe`) or fails closed (`gate`/`gate_all`).
- `invoke_dispatch_claude.py` exits 0, not the block code, on an infrastructure load failure (missing/broken `.claude/lib/claude_hook_dispatch.py`): a load failure is not a policy decision, and denying every tool call on a broken install is what got this plugin uninstalled repeatedly before (#4672).
- Inside a checkout of the repository that publishes this plugin, the dispatcher exits immediately when `CLAUDE_PLUGIN_ROOT` names this same plugin, to avoid double-firing every hook body against both the project's own `.claude/settings.json` and the installed plugin's `hooks.json`.
- A shim path registered in `dispatch_groups.json` must resolve to a `.py` file strictly inside this hooks directory (no `..`, no absolute path, no backslash); `validate_group()` rejects anything else before it runs.
- `session-start.sh` only runs its bootstrap body when `$CLAUDE_CODE_REMOTE=true`; a local developer session exits 0 immediately.

## Dangerous assumptions

- "A hook registered in `.claude/settings.json` ships to plugin consumers" is false. `hooks.json` is the shipped manifest and is empty; every event wired here today is this repository's own dev convenience.
- "This tree mirrors 1:1 into the Copilot plugin" is false. The Copilot mirror carries only an empty `hooks.json` and one config file; none of the `SessionStart`/`UserPromptSubmit`/`SessionEnd`/`PreCompact` scripts here are generated into it.
- "`_bootstrap.py` being present under `PreToolUse/` means a tool-use hook is registered" is false; it is unused scaffolding until the first new tool-use hook lands.
- "Editing a per-directory `CLAUDE.md` documents the hook" is false; those files are claude-mem stubs, not authored docs. This `AGENTS.md` is the doc surface.
- "Fail-open means uninstrumented" is false for 2 of the 6 registered invokers, and true for the other 4. `invoke_context_loader.py` and `invoke_checkout_freshness_check.py` each write a best-effort audit log line under `.agents/.hook-state/` (in a checkout that has one) even when they degrade; `invoke_plugin_hook_drift_check.py`, `invoke_memory_recall.py`, `invoke_memory_reflection.py`, and `invoke_compact_checkpoint.py` write none and degrade silently.

## Dependencies

- Feeds a generated Copilot CLI mirror under `src/copilot-cli/hooks/` via a hook generator in the `rjmurillo/ai-agents` repository's `build/` tree; regeneration order matters (a shared lib mirror must sync before hooks regenerate) and is owned outside this directory.
- `.claude/lib/` is a sibling dependency, not vendored here: `claude_hook_dispatch.py`, `claude_hook_protocol.py`, and `hook_utilities/` are imported by every `invoke_*.py` and by `invoke_dispatch_claude.py` itself.
- CI gates this tree from two directions, both re-run by a pre-push job in the `rjmurillo/ai-agents` repository whenever this directory, the Copilot mirror, or the generator changes: a hook-contract check validates every registered group's shims exist and expose valid exit-code semantics, and an installed-plugin hook guard materializes the shipped Copilot plugin as a consumer would install it and loads its hooks from a non-repo directory on Linux, macOS, and Windows, including a Python-less "vanilla" environment, to prove a broken or empty install degrades rather than wedging.
- `.agents/retrospective/` (outside this plugin root) is read by `invoke_context_loader.py`, which prints the consumer-repo skip line and exits 0 when absent. `.serena/memories/` is read instead by `UserPromptSubmit/invoke_memory_recall.py`, whose docstring names `memory_enhancement.hooks.user_prompt_submit_memory` under `scripts/`.

## Architecture

- Two dispatcher implementations exist side by side under `.claude/lib/`: `claude_hook_dispatch.py` (used by everything in this directory, one process per Claude Code group, `runpy`-based) and `hook_dispatch.py` (the Copilot CLI dispatcher, same design lineage, timeout-capable child-process execution for timed shims). They share `output_capture.py` but not much else; do not assume a fix in one applies to the other.
- The group runner (`claude_hook_dispatch.py`) must emit exactly one protocol-valid stdout document per group even when several shims each produce context: it concatenates context parts and, for events the host treats as plain-text context, prints plain text; for `PreToolUse`/`PostToolUse` it wraps the merge in one `hookSpecificOutput.additionalContext` JSON document.
- The plugin-hook-drift check (`SessionStart/plugin_hook_drift_*.py`, four files split by concern: model, report, safety, state) expands both this checkout's registrations and any installed plugin copy's registrations down to their real shim membership before diffing, specifically so a stale install that still routes through the same dispatcher group id is not mistaken for a match.

## Commands

These commands run only in the `rjmurillo/ai-agents` repository checkout, not in a consumer plugin install.

```bash
# Run one dispatch group by hand, feeding a JSON payload on stdin.
echo '{}' | python3 -u .claude/hooks/invoke_dispatch_claude.py --group sessionstart-1-context_loader

# Run a single invoker directly (bypasses the dispatcher).
echo '{}' | python3 .claude/hooks/SessionStart/invoke_checkout_freshness_check.py

# Validate dispatch_groups.json and hook exit-code contracts (CI form: hook-contract-check.yml).
uv run --frozen python scripts/validation/hook_contracts.py

# Full pre-PR gate chain before pushing any change under this directory.
uv run --frozen python scripts/validation/pre_pr.py
```
