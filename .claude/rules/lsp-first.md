---
applyTo: "**"
priority: critical
---

# LSP-First Navigation

For code navigation, prefer a Language Server over text search. A symbol query
(where is X defined, who calls X, what type is X) returns one file:line answer;
a grep returns noisy matches and several wrong-file reads. The token difference
is large on a real codebase.

This rule is the steering layer. ADR-062 adds an enforcement layer (PreToolUse
guards) and the per-turn Serena re-assertion hook (issue #1993,
`invoke_serena_reassertion.py`) adds the nudge. This file states the preference;
it does not duplicate the hook.

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

## Recovery and escape

If Serena is configured but inactive (for example after context compaction),
re-activate it: `mcp__serena__activate_project` then
`mcp__serena__initial_instructions`. If a guard misfires, set
`SKIP_LSP_GATE=true` to bypass, or `LSP_GATE_MODE=warn` to downgrade the gate to
an advisory. The guards fail open: when no LSP is reachable they allow the raw
tool rather than block.

During a merge, rebase, cherry-pick, or revert the read gate is bypassed
automatically (issue #2454). Either of these conditions skips the gate for the
in-flight file: (a) `.git/MERGE_HEAD`, `.git/rebase-merge`, or
`.git/rebase-apply` exists at the repo root, or (b) the file's leading window
starts a line with a conflict marker (`<<<<<<<`, `=======`, `>>>>>>>`). Files
under dot-directories (`.claude/`, `.serena/`, etc.) were already bypassed, so
intentional fenced examples in skill documentation are unaffected.

## References

- ADR-062 (conditional LSP-first navigation enforcement): the hook layer.
- `.claude/hooks/UserPromptSubmit/invoke_serena_reassertion.py` (#1993): the
  per-turn nudge this rule sits above.
- AGENTS.md (Serena Init is BLOCKING): the session-start activation.
