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

Touching LSP guards, adding a navigation tool that should route through Serena, or debugging a gate misfire (use the escape hatches above, not a hook edit). See ADR-062 (`.project-toolkit/architecture/ADR-062-conditional-lsp-first-enforcement.md`, ACCEPTED-WITH-DC) and `.claude/rules/lsp-first.md`.

Source: issue #2165 / PR #2168 (MERGED); ADR-062.

## Status update (2026-10-13): the escape hatches are retired

The enforcement layer above no longer exists at runtime. The 2026-07-17 ADR-062
amendment (issue #3214) retired the PreToolUse guards, and #3216 retired
`SKIP_LSP_GATE`, `LSP_GATE_MODE`, and `LSP_DOWN`. Only the steering rule
`.claude/rules/lsp-first.md` remains, and it is advisory.

Consequence for pushes: `LSP_DOWN=true` in the shell does not fail `git push`
on current `main`. A search of `lefthook.yml`, `scripts/`, `build/`,
`.claude/hooks/`, and `.claude/settings.json` found no reader of `LSP_DOWN`, and
`.claude/hooks/` holds no LSP guard. The `env -u LSP_DOWN git push` workaround
from an older Hindsight note (REF badf8a18) does not apply. If a push fails, read
the pre-push output for the real cause.

Verification: grep over `origin/main` at ec57f45d4 on 2026-10-13. The only
remaining mentions are the retirement notes in the `ai-agents-build-and-env` and
`ai-agents-config-catalog` skills. The older design text above is history.

