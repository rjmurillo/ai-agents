# LSP-first navigation enforcement (ADR-062): conditional, fail-open hooks

The repo mandates Serena-first / LSP-first navigation via steering, but steering
drifts. ADR-062 adds the enforcement layer: hooks that nudge agents off
grep/glob/full-file-read toward symbol tools, designed conditional and fail-open
so they never deadlock.

## Three-tier preference

1. Serena MCP symbolic tools (find_symbol, find_referencing_symbols,
   get_symbols_overview, find_implementations).
2. Native LSP (Claude `LSP` tool; Copilot auto-LSP).
3. grep / glob / sed as the last resort.

## The load-bearing property: conditioning

Each guard is a no-op (exit 0) UNLESS the target file's language has a reachable
LSP that offers the relevant capability. This is what keeps the layer safe:

- Symbol-grep guards (Grep / Bash-grep / Glob) key on
  go-to-definition / find-references capability: programming languages only.
  They never fire on markdown / json / yaml / toml.
- The Read gate is graduated (warmup, 2 free reads, warn, block-until-nav,
  surgical) and keys on `get_symbols_overview`, which Serena provides for all
  configured languages.
- Fail-open on EVERY uncertainty: no provider, tty / empty / malformed input, or
  any exception all resolve to allow. The gate never blocks when it cannot
  prove an LSP is available.

## Components

- Hooks (`.claude/hooks/`): `PreToolUse/invoke_lsp_grep_guard.py`,
  `invoke_lsp_glob_guard.py`, `invoke_lsp_bash_grep_guard.py`,
  `invoke_lsp_read_guard.py`, `invoke_lsp_pre_delegation_guard.py`; a PostToolUse
  usage tracker (`invoke_lsp_usage_tracker.py` / `invoke_lsp_read_tracker.py`);
  a SessionStart reset (`invoke_lsp_session_reset.py`).
- Shared lib (`scripts/hook_utilities/`, mirrored to `.claude/lib/`):
  `lsp_provider.py`, `lsp_symbols.py`, `lsp_gate_state.py`, `lsp_health.py`.
- Steering rule: `.claude/rules/lsp-first.md`.
- Dual registration: `settings.json` + plugin `hooks.json`, plus the generated
  Copilot CLI mirror.

## Escape hatches (know these when a guard misfires)

- `SKIP_LSP_GATE=true`: disables the gate entirely (kill switch).
- `LSP_GATE_MODE=warn`: downgrades block to advisory.
- `LSP_DOWN=true`: LSP configured but runtime down; guards ALLOW native tools and
  warn once instead of hard-blocking (graceful degradation, not a kill switch).
- Merge / rebase in progress, or a conflict marker in the file window, bypasses
  the read gate automatically.

## Provenance

Adapted from the MIT `nesaminua/claude-code-lsp-enforcement-kit` (JS), ported to
Python. Sits ABOVE the per-turn Serena re-assertion hook (#1993) and BELOW the
steering rule: rule states the preference, ADR-062 hooks enforce it.

## Evidence

- PR #2168 (merge 96aafb4fa707), closes #2165. Architect-reviewed
  ACCEPTED-WITH-DC.
- ADR: `.agents/architecture/ADR-062-conditional-lsp-first-enforcement.md`;
  debate: `.agents/critique/ADR-062-debate-log.md` (6-agent review).
- Steering: `.claude/rules/lsp-first.md`.
