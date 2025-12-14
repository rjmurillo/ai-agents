# Code Style and Conventions

## Markdown Standards

Configuration is in `.markdownlint-cli2.yaml`.

### Required Rules

| Rule | Description |
|------|-------------|
| MD040 | Fenced code blocks MUST have a language identifier |
| MD031 | Blank lines required around fenced code blocks |
| MD032 | Blank lines required around lists |
| MD022 | Blank lines required around headings |
| MD033 | Inline HTML restricted; wrap generic types in backticks |

### Disabled Rules

| Rule | Reason |
|------|--------|
| MD013 | Line length - agent templates have long descriptions |
| MD060 | Table column style - tables render correctly as-is |
| MD029 | Ordered list prefix - sequential numbering preferred |

### Code Block Languages

| Content Type | Language Identifier |
|--------------|---------------------|
| C# code | `csharp` |
| PowerShell | `powershell` |
| Bash/Shell | `bash` |
| JSON | `json` |
| YAML | `yaml` |
| Markdown | `markdown` |
| Plain text | `text` |
| Python | `python` |

### Generic Type Escaping

Always wrap .NET generic types in backticks:

- `ArrayPool<T>` not `ArrayPool<T>` (unescaped)
- `Dictionary<TKey, TValue>` not `Dictionary<TKey, TValue>` (unescaped)

## Heading Style

- Use ATX style (`#` prefix)
- Consistent heading hierarchy

## List Style

- Use dashes (`-`) for unordered lists
- Use consistent indentation

## Emphasis Style

- Use asterisks for *emphasis* and **strong**

## Code Fence Style

- Use backticks (```) not tildes
- Always include language identifier

## Commit Messages

Follow conventional commit format:

```text
<type>(<scope>): <description>

<optional body>
```

## Agent File Conventions

Agent files define:

- **description**: Purpose of the agent
- **tools**: Allowed tools
- **model**: AI model to use
- **Handoffs**: Which agents can be called next
- **Responsibilities**: What the agent should do
- **Constraints**: What the agent must NOT do
