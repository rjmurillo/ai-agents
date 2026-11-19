# janitor agent

The `janitor` agent removes tech debt from a codebase. It deletes unused code, simplifies complex patterns, and hands back a cleaned area with the debt removed counted in lines, files, or dependencies.

## When to use it

- You want unused functions, variables, imports, or dependencies deleted.
- You want dead code paths, duplicate logic, or commented-out code removed.
- You want nested conditionals flattened or single-use helpers inlined.
- You want obsolete, duplicate, or flaky tests cleaned up.
- You want stale comments and boilerplate removed, and stale references and links in docs updated.

## When not to use it

- You want to simplify code you just wrote while keeping all behavior: use [`code-simplifier`](code-simplifier.md) instead.
- You need to check a cleanup for regressions: use [`qa`](qa.md) instead.
- You need to audit packages for vulnerabilities and deprecations: use [`dependency-auditor`](dependency-auditor.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
janitor: remove unused helpers and dead imports under src/billing/
```

In GitHub Copilot CLI:

```bash
copilot --agent janitor --prompt "remove unused helpers and dead imports under src/billing/"
```

In VS Code or Visual Studio Copilot Chat:

```text
@janitor remove unused helpers and dead imports under src/billing/
```

## What you get

The agent reports the debt it removed as numbers: lines deleted, files cleaned, and dependencies removed. It uses the text status markers `[PASS]`, `[FAIL]`, `[WARNING]`, `[COMPLETE]`, and `[BLOCKED]`. It writes no fixed report file or layout.

## Advanced use

The agent follows five steps: measure what is used versus declared, delete safely, simplify one concept at a time, validate after each removal, and document nothing. Its analysis order is unused code first, then complexity, duplicate patterns, conditional logic, and last unnecessary dependencies.

It hands off to other agents:

| Target | When | Purpose |
| --- | --- | --- |
| `qa` | After cleanup | Verify no regressions |
| `analyst` | Complex debt discovered | Research impact |
| `architect` | Structural issues found | Design decisions |

A multi-step prompt:

```text
janitor: measure which exports in src/billing/ have no callers, delete them one module at a time, run the tests after each deletion, and report lines removed per module.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`code-simplifier`](code-simplifier.md): simplifies recently modified code and keeps behavior.
- [`qa`](qa.md): verifies the cleanup caused no regressions.
- [`analyst`](analyst.md): researches complex debt before you delete.
- [`architect`](architect.md): decides on structural issues the cleanup finds.
- Source template: [`janitor.shared.md`](../../templates/agents/janitor.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
