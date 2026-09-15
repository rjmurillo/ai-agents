# .claude/hooks/

Claude Code lifecycle hooks for this plugin root; consumed by the harness at runtime, partly mirrored into the Copilot CLI plugin.

## Matters

- Only `SessionStart` uses the group dispatcher (`invoke_dispatch_claude.py --group <id>`, membership in `dispatch_groups.json`); `UserPromptSubmit`, `SessionEnd`, `PreCompact` register directly.
- `hooks.json` (plugin manifest) declares `"hooks": {}`; these files ship inside the `project-toolkit` plugin root but register nothing there, so every live registration is `.claude/settings.json` only.
- `PreToolUse`/`PostToolUse` ship no Python hook script, only a bootstrap helper and a markdownlint config.
- `invoke_memory_recall.py`/`invoke_memory_reflection.py` call a package outside the plugin root; consumer installs get a silent no-op.

## Entry points

- `.claude/settings.json` `hooks` block: real event/timeout/group wiring.
- `invoke_dispatch_claude.py --group <id>`: reads `dispatch_groups.json` for that group's shims and `mode`.
- `session-start.sh`: gated on `$CLAUDE_CODE_REMOTE`; delegates to the container bootstrap script in the `rjmurillo/ai-agents` repository.

## Where to look

| Path | Why |
|---|---|
| `.claude/settings.json` | What fires: event, timeout, group |
| `dispatch_groups.json` | Shim membership, `mode` per group (`observe` today) |
| `hooks.json` | Plugin manifest; empty |
| `invoke_dispatch_claude.py` | Dispatcher entry; exit-code contract |
| `.claude/lib/claude_hook_dispatch.py` | Group-runner: modes, stdout merge |

## Skip

- `PostToolUse/CLAUDE.md`, `PreToolUse/CLAUDE.md`, `SessionStart/CLAUDE.md`: claude-mem stubs, no content. `CLAUDE.md` here is the same stub plus the `@AGENTS.md` line that loads this guide. `PreCompact/CLAUDE.md` differs; see Dangerous assumptions.
- `PostToolUse/README.md`: 269-line authoring template for a hook class with zero scripts, naming a hook ADR-097 retired; read it only when adding the first one back, after the bar in Constraints.
- `PreToolUse/_bootstrap.py`: unimported today. Not dead code; see Dangerous assumptions.

## Constraints

- New `PreToolUse`, `PostToolUse`, `PermissionRequest`, or `PostToolUseFailure` registration: clear every MUST in `tool-use-hook-bar.md` (auto-loads for this tree).
- Modes are pinned per event by `validate_group()`, never chosen: `PreToolUse`=`gate` (fail-closed, stops at first block), `UserPromptSubmit`/`Stop`/`SubagentStop`=`gate_all` (all shims run; returns the first block seen, else the first non-zero exit), `PostToolUse`/`SessionStart`/`PreCompact`=`observe` (all run, always allows; every group today). Any other event, `SessionEnd` included, has no reviewed mode and exits 2 on every fire. Missing shim/dispatch exception: deny in gate/gate_all, log-and-continue in observe. The hook-contract check never reads `mode`; `test_dispatch_groups_parity.py` is the only gate that does.
- `invoke_dispatch_claude.py` fails open (exit 0) on a `.claude/lib` import failure (#4672), and bails to 0 in non-gate modes when the installed plugin runs inside this checkout (double-fire guard); a bad manifest or dispatch exception exits 2, fail-closed.
- A `dispatch_groups.json` shim path must be a `.py` file strictly inside this hooks directory (no `..`, absolute path, or backslash); `validate_group()` rejects anything else.
- A registration's `timeout` must be 1 to 300s, and a shim on a blocking event (`PreToolUse`, `PermissionRequest`, `Stop`, `SubagentStop`, `UserPromptSubmit`) must carry `exit code` or `block` in its first 30 lines, or the hook-contract check reports a violation. `session-start.sh` escapes both at 900s only because that validator parses Python commands.
- Only a strictly validated per-event shape on a shim's stdout counts as a blocking decision (`claude_hook_protocol.py`); malformed or unsupported decision-shaped JSON is suppressed in `observe` and denies in `gate`/`gate_all`. A valid blocking decision is suppressed in `observe` too, which is every group today.

## Dangerous assumptions

- "A hook in `.claude/settings.json` ships to consumers" is false; `hooks.json` is the shipped manifest and is empty.
- "This tree mirrors 1:1 into the Copilot plugin" is false; the mirror carries only an empty `hooks.json` and one config file.
- `PreToolUse/_bootstrap.py` looks like dead scaffolding; it is not: a generator in the `rjmurillo/ai-agents` repository copies it into every generated dispatcher event directory and reads its bytes as the signature that marks such a directory safe to clean. Deleting it breaks both and fails the two test modules that read that exact path.
- `PreCompact/CLAUDE.md` looks like a claude-mem stub; it is not: hand-authored but stale, describing an on-disk checkpoint write `invoke_compact_checkpoint.py` no longer makes (ADR-082, issue #3217, removed, unread). Its only output is a resume-context string to stdout; failures print a stderr `[WARNING]` and still exit 0.
- "Fail-open means uninstrumented" is false for 2 of 6 invokers: `invoke_context_loader.py`/`invoke_checkout_freshness_check.py` append a best-effort audit line under `.agents/.hook-state/` (present only in the `rjmurillo/ai-agents` checkout), creating it, even when degraded; the other 4 write none. The 4 that import `hook_utilities` call `skip_if_consumer_repo()` before any work, deciding from the git origin remote, not `.agents/` presence (#2610); their in-file `ImportError` fallback is the old presence check. The memory pair never calls it and no-ops on the missing package instead.

## Dependencies

- Feeds a generated Copilot CLI mirror at `src/copilot-cli/hooks/` from `hooks.json`, not from `.claude/settings.json`: a registration added to `settings.json` alone never reaches that mirror. The generator and its regeneration order live outside this directory, in the `rjmurillo/ai-agents` repository.
- `.claude/lib/` is a sibling dependency; its `hook_utilities/` package is a synced copy, never edited there (`.claude/AGENTS.md` owns that). Only `invoke_dispatch_claude.py` imports `claude_hook_dispatch.py` (which pulls in `claude_hook_protocol.py`; no invoker touches either). `hook_utilities` is imported by 4 of 6 invokers (`SessionStart/invoke_*.py`, `PreCompact/invoke_compact_checkpoint.py`); `UserPromptSubmit`/`SessionEnd` import neither.
- Reads outside this plugin root, resolving only in the `rjmurillo/ai-agents` checkout: `invoke_context_loader.py` reads `.agents/retrospective/`; `invoke_memory_recall.py` delegates to `memory_enhancement.hooks.user_prompt_submit_memory` under `scripts/`, which reads `.serena/memories/`.
- CI in that repository: a PR-only hook-contract check validates `dispatch_groups.json`/exit codes. An installed-plugin hook guard (not path-filtered, PR and push-to-main only, never local) materializes the generated Copilot mirror, not this tree, in a non-repo dir across platforms, Python-less included.
- Pre-push in the `rjmurillo/ai-agents` checkout: the only job glob-scoped to this tree is lefthook's `hook-anchoring-e2e` (`.claude/hooks/**`); the plugin-manifest job beside it is skills-scoped. `.claude/hooks/**` sits in `python-type-check`'s exclude list, but the unglobbed pre-PR job type-checks every changed `.py` through the mypy ratchet, this tree included.

## Architecture

- Two dispatchers live under `.claude/lib/`: `claude_hook_dispatch.py` (used here) and `hook_dispatch.py` (Copilot CLI). Both run shims in-process via `runpy`; only the Copilot one runs a timeout-bearing shim in a child process, and only in `gate` mode (its `observe` path drops the timeout on purpose, #4706); this one never enforces per-shim timeouts at all. The former imports four exit-code/stdin helpers from the latter and mirrors its gate-mode semantics, plus a stdout-capture helper both take from `output_capture.py`; sharing exceeds the one helper it looks like.
- The group runner must emit exactly one protocol-valid stdout document per group: context parts join with a blank line, print as plain text for `UserPromptSubmit`/`SessionStart`/`Stop`/`SubagentStop`/`PreCompact`, and wrap in one `hookSpecificOutput.additionalContext` object for `PreToolUse`/`PostToolUse`. Two shims each printing their own JSON is the hazard grouping exists to prevent.
- The plugin-hook-drift check (`SessionStart/plugin_hook_drift_*.py`: model, report, safety, state) expands this checkout's and any installed copy's registrations to real shim membership before diffing, so a stale install on the same group id is not mistaken for a match.

## Commands

Runs only in the `rjmurillo/ai-agents` checkout, not a consumer install.

```bash
# Run one group by hand.
echo '{}' | uv run python -u .claude/hooks/invoke_dispatch_claude.py --group sessionstart-1-context_loader

# Run one invoker directly, bypassing the dispatcher.
echo '{}' | uv run python .claude/hooks/SessionStart/invoke_checkout_freshness_check.py

# Validate contracts; --ci exits nonzero on a violation (else always 0).
uv run --frozen python scripts/validation/hook_contracts.py --ci

# Full pre-PR gate chain.
uv run --frozen python scripts/validation/pre_pr.py
```
