# LSP-First Navigation Enforcement (ADR-062, #2168)

## What shipped

A conditional, availability-gated enforcement layer that pushes agents to Serena/LSP symbol navigation over Grep/Glob/full-file Read for code files. Adapted from the MIT `nesaminua/claude-code-lsp-enforcement-kit` (JS), ported to Python.

Components:
- 7 Python hooks under `.claude/hooks/`: grep / glob / bash-grep / read / pre-delegation (agent) guards, a PostToolUse usage tracker, a SessionStart reset.
- Shared lib: `lsp_provider`, `lsp_symbols`, `lsp_gate_state`.
- Steering rule: `.claude/rules/lsp-first.md`.
- Dual registration: `.claude/settings.json` + plugin `hooks.json`; generated Copilot CLI mirror.

## Design invariants

- **Conditional + fail-open**: the guards ALLOW the raw tool when no LSP is reachable, so they never deadlock. `detect_providers` is a config-only check, so a configured-but-down LSP needs `LSP_DOWN=true` to relax the gate (issue #2622); `SKIP_LSP_GATE=true` disables it entirely; `LSP_GATE_MODE=warn` downgrades to advisory.
- Merge/rebase and dot-directory files bypass the read gate (issues #2454, #2622).
- This is the ENFORCEMENT layer; the steering (AGENTS.md Serena-first) and the per-turn re-assertion hook (#1993) are the steering/nudge layers above it.

## Apply when

Touching LSP guards, adding a navigation tool that should route through Serena, or debugging a gate misfire (use the escape hatches above, not a hook edit). See ADR-062 (`.agents/architecture/ADR-062-conditional-lsp-first-enforcement.md`, ACCEPTED-WITH-DC) and `.claude/rules/lsp-first.md`.

Source: issue #2165 / PR #2168 (MERGED); ADR-062.
