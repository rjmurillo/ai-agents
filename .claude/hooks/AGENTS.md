# .claude/hooks/

Claude Code lifecycle hooks: generated output, run by the harness, mirrored in part into Copilot CLI.

<!-- vendor-portability: upstream template, generator, generated-output, and sibling-guide paths named on purpose -->

## Matters

- Generated from `templates/hooks/`; edit the template, not this tree. Render map: `templates/AGENTS.md`.
- Hand-maintained exceptions: `AGENTS.md`, five `CLAUDE.md`, `PostToolUse/README.md`.
- Group dispatcher only on `SessionStart`; `UserPromptSubmit`, `SessionEnd`, `PreCompact` register directly.
- `hooks.json` declares `"hooks": {}`: this tree ships in the `project-toolkit` plugin root and registers nothing there. Every live registration is `.claude/settings.json`.
- `PreToolUse`/`PostToolUse` ship no Python hook, only a bootstrap helper and a markdownlint config.
- `invoke_memory_recall.py`/`invoke_memory_reflection.py` call a package outside the plugin root; consumer installs no-op silently.

## Entry points

- `invoke_dispatch_claude.py --group <id>`: reads that group's shims and `mode` from `dispatch_groups.json`.
- `session-start.sh`: `$CLAUDE_CODE_REMOTE`-gated container bootstrap.

## Where to look

| Path | Why |
|---|---|
| `.claude/settings.json` | What fires: event, timeout, group |
| `dispatch_groups.json` | Shim membership, `mode` per group (`observe` today) |

## Skip

- `PostToolUse/README.md`: authoring template for a class with zero scripts; its hook is ADR-097-retired.
- Four `CLAUDE.md`: claude-mem stubs, no real content; only `PreCompact/CLAUDE.md` has content (stale, see below).

## Constraints

- A hand edit here is overwritten by the next build and fails the pre-PR row `Generated Artifact Staleness` (`build_all.py --check`); `Hook Template Drift` covers `src/claude/hooks/` and `.claude/settings.json` only.
- New `PreToolUse`, `PostToolUse`, `PermissionRequest`, `PostToolUseFailure` registration: clear every MUST in `tool-use-hook-bar.md`.
- `validate_group()` pins mode by event, never chosen: `PreToolUse` `gate`, stops at the first block; `UserPromptSubmit`/`Stop`/`SubagentStop` `gate_all`, runs all, exits first block else first non-zero; `PostToolUse`/`SessionStart`/`PreCompact` `observe`, runs all, exits 0, suppresses blocks. Any other event, `SessionEnd` included, exits 2 on every fire.
- `invoke_dispatch_claude.py` exits 0 on a `.claude/lib` import failure, and in non-gate modes when the installed plugin runs inside this checkout (double-fire guard); bad manifest or dispatch exception exits 2, fail-closed.
- A `dispatch_groups.json` shim path must be a `.py` file strictly inside this directory: no `..`, absolute path, or backslash.
- `timeout` 1 to 300s, checked per shim, never enforced at runtime. A shim on a blocking event (`PreToolUse`, `PermissionRequest`, `Stop`, `SubagentStop`, `UserPromptSubmit`) must carry `exit code` or `block` in its first 30 lines. `session-start.sh` escapes both at 900s because the hook-contract check parses Python commands only.
- Only a strictly validated per-event stdout shape blocks (`claude_hook_protocol.py`); other decision-shaped JSON is suppressed in `observe`, denies in the gate modes.

## Dangerous assumptions

- `PreToolUse/_bootstrap.py` looks dead. The Copilot dispatcher generator copies this exact path into every generated event directory and reads its bytes as the clean-safe signature; deleting it fails two test modules.
- `PreCompact/CLAUDE.md` reads as a claude-mem stub. Hand-authored and stale: it describes an on-disk checkpoint write `invoke_compact_checkpoint.py` no longer makes (ADR-082, issue #3217). Sole output is a resume-context string on stdout.
- "Fail-open means uninstrumented": false for 2 of 6 invokers. `invoke_context_loader.py`/`invoke_checkout_freshness_check.py` append a best-effort audit line under `.agents/.hook-state/` even when degraded. The 4 importing `hook_utilities` call `skip_if_consumer_repo()` first, which reads the git origin remote, not `.agents/` presence.

## Dependencies

- Copilot mirror `src/copilot-cli/hooks/` renders from `src/claude/hooks.json` + `src/claude/hooks/`, not from settings, then binplaces to `.github/hooks/`, of which only `*.json` reaches Copilot CLI cloud. Both hold only an empty `hooks.json` and one config file; a settings-template registration reaches neither. `build/AGENTS.md` owns generator order (lib renders before hooks).
- `.claude/lib/` sibling: `hook_utilities/` there is a synced copy, never edited there (`.claude/AGENTS.md` owns that split). Only `invoke_dispatch_claude.py` imports `claude_hook_dispatch.py`, which pulls `claude_hook_protocol.py`. `hook_utilities`: 4 of 6 invokers; `UserPromptSubmit`/`SessionEnd` import neither.
- Gates upstream: a PR-only hook-contract check on `dispatch_groups.json` and exit codes; an installed-plugin hook guard, CI-only and never local, materializing the Copilot mirror, not this tree; pre-push, only lefthook's `hook-anchoring-e2e` globs here. `python-type-check` excludes this tree; the unglobbed pre-PR job still type-checks every changed `.py`.

## Architecture

- One protocol-valid stdout document per group: context parts join on a blank line as plain text, except `PreToolUse`/`PostToolUse`, wrapped in one `hookSpecificOutput.additionalContext` object.

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
