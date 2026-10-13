# LSP-First Navigation Enforcement (ADR-062, #2168)

> Historical. The runtime gate and its escape hatches (`SKIP_LSP_GATE`, `LSP_GATE_MODE`, `LSP_DOWN`) were retired in 2026-07. See "Status update" at the bottom before acting on anything below.

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

Touching LSP guards, adding a navigation tool that should route through Serena, or debugging a gate misfire (historical: the gate and its escape hatches are retired, see Status update). See ADR-062 (`.project-toolkit/architecture/ADR-062-conditional-lsp-first-enforcement.md`, ACCEPTED-WITH-DC) and `.claude/rules/lsp-first.md`.

Source: issue #2165 / PR #2168 (MERGED); ADR-062.

## Status update (2026-10-13): the escape hatches are retired

The enforcement layer above no longer exists at runtime. The 2026-07-17 ADR-062
amendment (issue #3214) retired the PreToolUse guards, and #3216 retired
`SKIP_LSP_GATE`, `LSP_GATE_MODE`, and `LSP_DOWN`. Only static steering remains
(`.claude/rules/lsp-first.md` plus the AGENTS.md Serena Init line), and it is advisory.

Consequence for pushes: `LSP_DOWN=true` in the shell does not fail `git push`
on current `main`. A search of `lefthook.yml`, `scripts/`, `build/`,
`.claude/hooks/`, and `.claude/settings.json` found no reader of `LSP_DOWN`, and
`.claude/hooks/` holds no LSP guard. The `env -u LSP_DOWN git push` workaround
from an older Hindsight note (REF badf8a18) does not apply. If a push fails, read
the pre-push output for the real cause.

Verification: grep over `origin/main` at ec57f45d4 on 2026-10-13 found no runtime
reader of `LSP_DOWN` in the searched paths. The skills `ai-agents-build-and-env`
and `ai-agents-config-catalog` carry the intended current retirement notes. Other
hits are not runtime readers: ADR-062 historical Decision text, skill templates,
session and handoff artifacts, and sibling memories
(`architecture/architecture-lsp-first-enforcement.md`, `lsp/lsp-first-enforcement.md`)
that may still describe the hatches as live. Treat those as stale.
