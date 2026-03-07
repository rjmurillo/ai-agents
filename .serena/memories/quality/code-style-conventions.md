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

## Document Version Metadata

**DO NOT include version history sections in documentation.**

Git handles versioning; redundant metadata creates:
- Merge conflicts
- Stale information
- Maintenance burden

**Avoid these patterns:**
- `## Version History` / `## Revision History` / `## Change Log`
- `| Version | Date | Changes |` tables
- `*Template Version: 1.0*` footers

**Use instead:**
- Git log: `git log --oneline -10 -- <file>`
- Git blame: `git blame <file>`

Reference: Issue #280, Issue #272

## Canonical Source Principle

Documentation MUST follow the single source of truth pattern to prevent drift, duplication, and contradictions.

### What Makes a Document Canonical

A canonical document:

1. **Declares its status**: Contains `> **Status**: Canonical Source of Truth` header
2. **Owns its domain**: Is the single authoritative reference for a specific topic
3. **Is referenced, not copied**: Other documents MUST link to it rather than duplicate content
4. **Uses RFC 2119 language**: MAY/SHOULD/MUST keywords indicate requirement levels

### How to Reference Canonical Sources

| Do | Don't |
|----|-------|
| Link to canonical source: "See [SESSION-PROTOCOL.md]" | Copy content from canonical source |
| Reference specific sections: "Per SESSION-PROTOCOL.md §Session Start" | Paraphrase canonical content |
| Use "See: X" or "Reference: X" patterns | Create summaries that can drift |

**Exception**: CLAUDE.md and AGENTS.md MAY include minimal excerpts for quick reference, but MUST include links to full canonical source.

### Current Canonical Sources

Documents with formal `> **Status**: Canonical Source of Truth` marker:

| Document | Scope | Location |
|----------|-------|----------|
| SESSION-PROTOCOL.md | Session start/end requirements, validation | `.agents/SESSION-PROTOCOL.md` |
| PROJECT-CONSTRAINTS.md | Hard constraints, language restrictions | `.agents/governance/PROJECT-CONSTRAINTS.md` |

De-facto authoritative sources (scope-specific, widely referenced):

| Document | Scope | Location |
|----------|-------|----------|
| AGENT-SYSTEM.md | Agent catalog, routing heuristics | `.agents/AGENT-SYSTEM.md` |
| ADR-* | Architecture decisions for specific topics | `.agents/architecture/ADR-*.md` |
| usage-mandatory.md | Skill usage requirements | `.serena/memories/usage-mandatory.md` |

### Creating New Canonical Sources

Before creating a new canonical source:

1. Verify no existing canonical source covers the topic
2. Define clear scope boundaries
3. Add `> **Status**: Canonical Source of Truth` header
4. Update this list if the source is broadly applicable

Reference: Issue #675

## Agent File Conventions

Agent files define:

- **description**: Purpose of the agent
- **tools**: Allowed tools
- **model**: AI model to use
- **Handoffs**: Which agents can be called next
- **Responsibilities**: What the agent should do
- **Constraints**: What the agent must NOT do
