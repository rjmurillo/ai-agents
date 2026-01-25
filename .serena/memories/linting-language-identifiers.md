# Skill-Lint-006: Language Identifier Selection

**Statement**: Use `text` for pseudo-code and tool invocations, specific languages for real code

**Context**: MD040 code block language identifier selection

**Atomicity**: 93%

**Impact**: 8/10

## Reference Table

| Content Type | Identifier |
|--------------|------------|
| Memory tool invocations | `text` |
| JSON payloads | `json` |
| C# code | `csharp` |
| Shell commands | `bash` |
| YAML config | `yaml` |
| Markdown templates | `markdown` |
| PowerShell | `powershell` |
| Python | `python` |
| Pseudo-code | `text` |

## Anti-Pattern

- Leaving code blocks without language identifier (MD040 violation)
- Using wrong language identifier causing syntax highlighting errors

## Related

- [linting-autofix](linting-autofix.md)
- [linting-config](linting-config.md)
- [linting-exclusions](linting-exclusions.md)
- [linting-generic-types](linting-generic-types.md)
