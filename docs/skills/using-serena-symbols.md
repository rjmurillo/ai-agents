# using-serena-symbols

Shows how to use Serena's language-server tools to find symbols, trace references, and read file structure. It gives answers that text search cannot, because Serena understands code structure.

## When to use it

- You need to find a class or function definition, not every mention of its name.
- You need to trace references to a method, or see the call hierarchy.
- You need the structure of a new file before you read it.
- Text search would be imprecise.
- Trigger phrases: `how do I find a symbol`, `how do I explore a file's structure`, `how do I trace references`, `how do I search code patterns`, `what methods does this class have`.

## When not to use it

- You want guidance on memory: use [`memory`](memory.md).
- You are searching for string literals, comments, config files, YAML, or TODO markers. Use grep or plain text search.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:using-serena-symbols`. The agent loads it when your request matches, and [`context-hub-setup`](context-hub-setup.md) lists it as required once Serena is installed. To ask for it by name, say:

```text
Use the using-serena-symbols skill to find every caller of AuthService.validate_token in src/services/auth.py.
```

The agent starts with a file overview, finds the symbol, then lists the code that references it.

## What you get

Each tool returns structured code facts:

| Tool | Returns |
| --- | --- |
| `get_symbols_overview` | Classes, functions, and variables in a file, with kind and location. Start here for a new file. |
| `find_symbol` | A symbol found by name pattern, with its body and children when you ask. |
| `find_referencing_symbols` | Code snippets for each reference, with context. |
| `search_for_pattern` | Regex matches with smarter file filtering than grep. |

Tool names carry a host-specific prefix, so the form your host exposes may differ from the examples in the source.

## Advanced use

`find_symbol` takes a name path pattern:

- `UserService` finds any symbol with that name.
- `UserService/authenticate` finds a method in a class.
- `/UserService` is an exact match.
- `Service` with `substring_matching: true` matches `UserService`, `AuthService`, and so on.

Its other parameters: `include_body` (source code), `depth` (0 for the symbol alone, 1 to include children), `relative_path` (restrict to a file or directory), and `include_kinds` and `exclude_kinds` (LSP symbol kind numbers, such as 5 for Class, 6 for Method, 12 for Function).

Keep results small:

1. Scope searches with `relative_path`. It is much faster than the whole codebase.
2. Start with `include_body: false`. Read code only when you need it.
3. Start with `depth: 0`. Expand to children for specific classes.
4. Avoid depth above 1 on large modules.
5. Record important architectural findings in Serena memory.

Serena writes go to the checkout where the server started. Do not call its write tools from a linked worktree. Edit `.serena/memories/` in your own checkout, or hand the change to the parent session.

To explore an unfamiliar codebase, list the directory, get the overview of the entry file at depth 1, then trace key classes. To understand one class, find it with children, read the methods you need, then find who calls it. To trace dependencies, search for imports with a regex and follow references.

Serena works with any language that has a configured language server, such as Python (pyright or pylsp), TypeScript and JavaScript (tsserver), Rust (rust-analyzer), Go (gopls), and Java (jdtls). Available features depend on the server.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`context-hub-setup`](context-hub-setup.md): checks that the Serena plugin is installed.
- [`memory`](memory.md): the guidance for Serena memories.
- [`analyze`](analyze.md): broad codebase investigation.
- Source: [`SKILL.md`](../../src/claude/skills/using-serena-symbols/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
