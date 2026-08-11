---
applyTo: '**/*.py,**/*.cs,**/*.ts,**/*.tsx,**/*.js,**/*.jsx,**/*.go,**/*.rs,**/*.java,**/*.rb,**/*.c,**/*.h,**/*.cpp,**/*.ps1,**/*.psm1,**/*.psd1,**/*.sh,**/*.sql'
---

# LSP-First Navigation

For code navigation, prefer a Language Server over text search. A symbol query
(where is X defined, who calls X, what type is X) returns one file:line answer;
a grep returns noisy matches and several wrong-file reads. The token difference
is large on a real codebase.

This is the cross-harness source of truth. It states a preference; no runtime
gate blocks a raw search. ADR-062 paired it with PreToolUse guards that blocked
Read, Grep, and Glob until an LSP was tried; the 2026-07-17 amendment (issue
#3214) retired them and kept the steering.

Scope is code extensions, not `**`: Claude reads `paths`, Copilot mirrors read
`applyTo`. Markdown, logs, and plain text go back to grep, so do not widen it.

## The three tiers

For any navigation or search of a code file, prefer in this order:

1. **Serena MCP symbolic tools** when Serena is active:
   `find_symbol` (definition / search), `find_referencing_symbols` (references),
   `get_symbols_overview` (read a file's structure before reading its body),
   `find_implementations`, `get_diagnostics_for_file`.
2. **Native LSP** when Serena is not active: the Claude Code built-in `LSP` tool
   (`goToDefinition`, `findReferences`, `workspaceSymbol`, `hover`,
   `diagnostics`, `goToImplementation`) on the Claude harness; Copilot CLI uses
   its language servers automatically.
3. **grep / glob / sed** only when no LSP can navigate the file. This is the
   last resort, not a per-language exemption: if an LSP exists for the file
   type, use it.

## When it applies

- A symbol search (a camelCase / PascalCase / dotted / snake_case name) in a
  programming-language file: use `find_symbol` / `find_referencing_symbols`, not
  Grep or a symbol-shaped Glob.
- Reading a code file: call `get_symbols_overview` (or a navigation tool) first,
  then read the symbol you need, not the whole file. After a couple of
  navigation calls in a session, read freely.
- Delegating an implementation agent: subagents cannot reach MCP tools, so
  pre-resolve the symbols (file:line) into the delegation prompt.

## When grep is correct

- `git grep` for history search.
- Non-code targets: markdown prose, logs, plain text, data files where there is
  no symbol to navigate to.
- A pattern that is not a symbol (prose, a flag, a regex, a constant).
- No LSP is reachable for the file type.

## Recovery

If Serena is configured but inactive (for example after context compaction),
re-activate it: `mcp__serena__activate_project` then
`mcp__serena__initial_instructions`. Nothing needs bypassing: the preference is
advisory, so use grep or glob when no LSP is reachable.

## References

- ADR-062 (conditional LSP-first navigation enforcement).
- AGENTS.md (Serena Init is BLOCKING): the session-start activation.
