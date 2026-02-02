# ADR-001: Markdown Linting Configuration

## Status

Accepted

## Context

The vs-code-agents repository contains 59 markdown files (agent templates, documentation, instruction files) with **1363 markdown lint violations** identified by markdownlint-cli2. These violations cause:

1. **Wasted tokens and time** during commits when pre-commit hooks fail
2. **Inconsistent documentation quality** across agent definitions
3. **Potential rendering issues** in GitHub/IDEs

### Violation Summary

| Rule | Description | Count | Severity |
|------|-------------|-------|----------|
| MD040 | Code blocks without language identifiers | 286+ | High |
| MD013 | Line length > 80 characters | 200+ | Medium |
| MD031 | Missing blank lines around code blocks | 150+ | Medium |
| MD032 | Missing blank lines around lists | 100+ | Medium |
| MD022 | Missing blank lines around headings | 100+ | Medium |
| MD033 | Inline HTML (generic types) | 3+ | High |
| MD060 | Table column style issues | 50+ | Low |

## Decision

### 1. Create markdownlint-cli2 Configuration

Create `.markdownlint-cli2.yaml` in the repository root with rules appropriate for agent templates:

```yaml
# Configuration rules:
# - Disable MD013 (line-length) - agent templates have long tool lists
# - Disable MD060 (table-column-style) - tables are readable as-is
# - Enable MD040 (fenced-code-language) - critical for syntax highlighting
# - Enable MD033 partial - allow some HTML but flag generic types
```

### 2. Create Markdown Linting Requirements Document

Create `docs/markdown-linting.md` documenting:
- Required rules and their rationale
- Common violations and fixes
- Code block language identifier reference
- Generic type escaping patterns

### 3. Fix All Violations

Priority order:
1. **MD040**: Add language identifiers to all code blocks
2. **MD033**: Wrap generic types in backticks (`ArrayPool<T>` -> `` `ArrayPool<T>` ``)
3. **MD031**: Add blank lines around code blocks
4. **MD032**: Add blank lines around lists
5. **MD022**: Add blank lines around headings

### 4. Add Pre-commit Hook (Optional)

Create `.pre-commit-config.yaml` for automated validation on commit.

## Consequences

### Positive

- Consistent markdown quality across all 59 files
- Reduced commit failures from linting errors
- Better syntax highlighting in code examples
- Clear documentation for future contributors

### Negative

- One-time effort to fix 1363 violations
- Line length rule disabled may allow very long lines

### Mitigations

- Fix violations in batches by directory (claude/, vs-code-agents/, copilot-cli/)
- Configure specific rules rather than blanket disabling
- Document exceptions in the linting requirements document

## Implementation Notes

### markdownlint-cli2.yaml Configuration

```yaml
config:
  # Line length - disabled for agent templates with long tool lists
  MD013: false

  # Table column style - disabled, tables are readable as-is
  MD060: false

  # Fenced code language - REQUIRED
  MD040: true

  # Inline HTML - warn but don't fail (some HTML may be intentional)
  MD033:
    allowed_elements:
      - br
      - kbd
      - sup
      - sub

  # Multiple H1 - allow in agent templates (frontmatter + title)
  MD025:
    front_matter_title: ""

  # Heading style - consistent ATX style
  MD003:
    style: "atx"

  # Code block style - consistent fenced style
  MD046:
    style: "fenced"

  # Code fence style - consistent backticks
  MD048:
    style: "backtick"
```

### Code Block Language Reference

| Content Type | Language Identifier |
|--------------|---------------------|
| C# code | `csharp` |
| PowerShell | `powershell` |
| Bash/Shell | `bash` |
| JSON | `json` |
| YAML | `yaml` |
| Markdown | `markdown` |
| Plain text | `text` |
| Generic/pseudo | `text` |

### Generic Type Escaping

```markdown
# Wrong - triggers MD033
Use ArrayPool<T> for buffer pooling.

# Correct - escaped in backticks
Use `ArrayPool<T>` for buffer pooling.
```

## References

- [markdownlint Rules](https://github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md)
- [markdownlint-cli2 Configuration](https://github.com/DavidAnson/markdownlint-cli2#configuration)
- [GitHub Issue #14](https://github.com/rjmurillo/vs-code-agents/issues/14)
