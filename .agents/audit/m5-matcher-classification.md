# M5-T0: Pre-flight matcher classification

Date: 2026-04-28
Source: `.claude/settings.json` (HEAD: a1ad941b)
Spec: REQ-003-007 step 5 disambiguation rules
Purpose: prove every live matcher pattern classifies cleanly under the
locked disambiguation rules before implementing the shim injector
(M5-T2). Block M5 design if more than 2 patterns are ambiguous.

## Disambiguation rules (locked)

1. Pattern starts with `^` AND ends with `$` -> **regex** (`re.fullmatch`)
2. Pattern matches `^[A-Za-z_][A-Za-z0-9_]*\(.*\)$` (e.g.
   `Bash(git commit*)`) -> **tool-glob** (`toolName` exact +
   `fnmatch.fnmatchcase(normalizedToolArgs, argsGlob)`)
3. Otherwise -> **bare tool name** (exact `toolName`, no args check)

## Classification table

| # | Event | Matcher | Class | Notes |
|---|-------|---------|-------|-------|
| 1 | PreToolUse | `Bash` | bare | exact tool name; no parens |
| 2 | PreToolUse | `Bash(git commit*)` | tool-glob | `toolName=Bash`, `argsGlob=git commit*` |
| 3 | PreToolUse | `Bash(gh pr create*)` | tool-glob | `toolName=Bash`, `argsGlob=gh pr create*` |
| 4 | PreToolUse | `^(Write\|Edit)$` | regex | anchors present; alternation |
| 5 | PreToolUse | `Bash(git push*)` | tool-glob | `toolName=Bash`, `argsGlob=git push*` |
| 6 | PreToolUse | `^(Edit\|Write)$` | regex | anchors present; alternation (order swap of #4) |
| 7 | SessionStart | `null` | none | no matcher; shim not injected |
| 8 | UserPromptSubmit | `null` | none | no matcher; shim not injected |
| 9 | PostToolUse | `^(Write\|Edit)$` | regex | dedupe of #4 |
| 10 | PostToolUse | `Bash` | bare | dedupe of #1 |
| 11 | PostToolUse | `mcp__serena__write_memory` | bare | matches `[A-Za-z_]\w*$`, no parens |
| 12 | Stop | `null` | none | no matcher |
| 13 | SubagentStop | `null` | none | event-dropped; no shim |
| 14 | PermissionRequest | `Bash(pwsh*Invoke-Pester*\|npm test*\|...)` | tool-glob | event-dropped; no shim |

## Counts by classification

- **regex**: 3 entries (3 unique: `^(Write|Edit)$`, `^(Edit|Write)$`)
- **tool-glob**: 4 entries (4 unique: `Bash(git commit*)`, `Bash(gh pr create*)`, `Bash(git push*)`, `Bash(pwsh*...)`)
- **bare**: 3 entries (2 unique: `Bash`, `mcp__serena__write_memory`)
- **none** (no `matcher` field): 4 entries (no shim needed)
- **ambiguous**: 0

## Live-corpus checks

- Unicode in `mcp__serena__write_memory`: ASCII only; safe for
  `[A-Za-z_]\w*` rule.
- Regex anchors: every regex form uses `^...$` exactly; no internal anchors.
- Tool-glob form: every paren'd matcher prefix is a valid Python identifier
  (`Bash`); no tool name with hyphens or dots in the live corpus.
- Multi-pipe glob: `Bash(pwsh*Invoke-Pester*|npm test*|...)` is a single
  argsGlob string. `fnmatch` does not natively support `|`; the shim must
  split on `|` outside any glob metacharacters and try each branch.
  Reference implementation: split on top-level `|` and OR-fold the
  results. (PermissionRequest is dropped, but the same shape may appear
  in PreToolUse / PostToolUse later, so the shim must handle it
  generally.)

## Decision

All 14 live entries classify deterministically. Zero ambiguous; M5-T2
design proceeds.

## Tool-glob argsGlob multi-branch handling (locked)

`fnmatchcase` treats `|` as a literal. The shim shall:

1. Split `argsGlob` on un-escaped `|` at the top level.
2. Match the normalized `toolArgs` against each branch with
   `fnmatch.fnmatchcase`.
3. Return True on the first hit; False if none match.

This preserves the Claude semantics where each `|` branch is a separate
glob alternation.

## Whitespace normalization (locked)

Normalization applies to the `toolArgs` value extracted from JSON, not to
the pattern. Authors write patterns assuming single spaces; runtime
collapses runs of `\s+` to a single space before `fnmatchcase`.

```python
import re
normalized = re.sub(r"\s+", " ", tool_args).strip()
```

## Crash policy (locked)

Any exception inside the shim itself (regex compilation error, JSON
decode failure, missing `toolName`) prints to stderr and exits 2 (config
error). The shim never silently allows when its own logic fails.
