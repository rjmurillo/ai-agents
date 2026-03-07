---
name: Documentation Standards
applyTo: "**/*.md"
excludeFrom: "src/claude/**/*.md,.agents/steering/**"
priority: 5
version: 1.0.0
status: active
---

# Documentation Standards Steering

## Scope

**Applies to**:

- `**/*.md` - All markdown files in the repository

**Excludes**:

- `src/claude/**/*.md` - Agent prompts (see agent-prompts.md)
- `.agents/steering/**` - Steering files (self-referential)

## Guidelines

### Markdown Flavor

Use GitHub-Flavored Markdown (GFM). All markdown renders on GitHub. Do not use features that require external renderers.

### Heading Hierarchy

- One H1 per document, as the first line (MD041 enforced).
- Start body content at H2.
- Do not skip heading levels (H2 to H4 without H3).
- YAML front matter with a `title` field does not count as H1 (MD025 configured with `front_matter_title: ""`).

### Code Blocks

- Use fenced code blocks with triple backticks (MD046: `fenced`).
- Every fenced code block MUST have a language identifier (MD040 enforced).
- Common identifiers: `bash`, `python`, `powershell`, `yaml`, `json`, `markdown`, `text`.
- Use `text` for plain output with no syntax highlighting.

### Lists

- Use dashes (`-`) for unordered lists (MD004: `dash`).
- Use sequential numbering (`1.`, `2.`, `3.`) for ordered lists. Sequential numbers are more readable than all-`1.` prefixes.
- Indent nested lists by 2 spaces.

### Tables

- Use GFM pipe tables for structured data.
- Align columns for readability in source, but exact alignment is not enforced (MD060 disabled).
- Include a header row with separator.

### Inline HTML

Allowed elements: `br`, `code`, `kbd`, `sup`, `sub`, `details`, `summary`, `strong`, `example`. All other inline HTML triggers MD033.

### Alerts

Use GitHub alert syntax for callouts:

```markdown
> [!NOTE]
> Informational context that supplements the main content.

> [!WARNING]
> Potential issues or gotchas that need attention.

> [!IMPORTANT]
> Critical information users must know.

> [!TIP]
> Helpful suggestions for better outcomes.

> [!CAUTION]
> Actions that could cause data loss or irreversible consequences.
```

### Line Length

No line length limit is enforced (MD013 disabled). Prettier compatibility takes precedence. Keep sentences short for readability.

### Links and Cross-References

- Use relative paths for internal links: `[Session Protocol](.agents/SESSION-PROTOCOL.md)`.
- Use `@filename` syntax in CLAUDE.md and AGENTS.md to reference included files.
- Verify links exist before committing. Broken links degrade navigation.
- For ADR references, use the format: `ADR-NNN: description`.

## Document Structure

### YAML Front Matter

Steering files and agent prompts use YAML front matter. General documentation files do not require front matter unless they belong to a schema-defined category.

**Steering file schema:**

```yaml
---
name: Human-readable name
applyTo: "glob pattern"
excludeFrom: "optional glob pattern"
priority: 1-10
version: 1.0.0
status: placeholder | draft | active
---
```

**Memory file schema:**

```yaml
---
id: memory-identifier
subject: Short description
links:
  - link_type: RELATED
    target_id: other-memory-id
tags:
  - tag1
confidence: 0.0-1.0
---
```

### Section Organization

Order sections consistently within each document type:

1. Title (H1)
2. Status or summary (if applicable)
3. Context or scope
4. Main content sections (H2)
5. Examples (H2)
6. References (H2)
7. Footer with metadata

### Footer Pattern

Use a horizontal rule followed by italicized metadata:

```markdown
---

*Created: 2026-01-15*
*GitHub Issue: #573*
```

## Patterns

### ADR Structure

ADRs follow the template at `.agents/architecture/ADR-TEMPLATE.md`. Required sections:

| Section | Purpose |
|---------|---------|
| Status | Proposed, Accepted, Deprecated, or Superseded |
| Date | YYYY-MM-DD format |
| Context | Problem statement and forces |
| Decision | Clear, unambiguous decision |
| Rationale | Alternatives considered with trade-off table |
| Consequences | Positive, Negative, Neutral subsections |
| Implementation Notes | Optional technical details |
| Related Decisions | Links to related ADRs |
| References | External sources |

### README Patterns

Repository and directory READMEs follow this structure:

1. H1 title
2. One-paragraph purpose statement
3. Key sections relevant to the directory's content
4. Links to related documentation

### Changelog Format

Follow Keep a Changelog conventions:

```markdown
## [Unreleased]

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security
```

### Status Indicators

Use text status indicators for clear signaling:

| Indicator | Meaning |
|-----------|---------|
| `[PASS]` | Requirement met |
| `[FAIL]` | Requirement not met |
| `[WARNING]` | Concern noted, does not block |
| `[COMPLETE]` | Task finished |
| `[BLOCKED]` | Cannot proceed |
| `[SKIP]` | Intentionally omitted |

## Anti-Patterns

### Broken Links

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Absolute GitHub URLs for internal files | Break on forks and branch changes | Use relative paths |
| Links to deleted files | 404 errors degrade trust | Remove or update links when deleting files |
| Anchor links to renamed headings | Silent navigation failure | Search for references before renaming headings |

### Missing Metadata

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Steering file without front matter | Tooling cannot parse scope or priority | Add required YAML fields |
| ADR without Status or Date | Readers cannot assess currency | Follow ADR-TEMPLATE.md |
| Code block without language identifier | No syntax highlighting, MD040 violation | Add language identifier |

### Formatting Violations

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Asterisks for list markers | Inconsistent with project standard | Use dashes (MD004) |
| Indented code blocks | Inconsistent with fenced style | Use fenced blocks (MD046) |
| Skipped heading levels | Broken document outline | Maintain sequential hierarchy |
| Em dashes or en dashes | Project style prohibits them | Use commas, periods, or restructure |

## Examples

### Well-Structured Document

```markdown
# Component Name

Brief description of what this component does.

## Overview

Context and purpose.

## Usage

How to use this component.

## Configuration

Available options with a table:

| Option | Default | Description |
|--------|---------|-------------|
| `timeout` | `30s` | Request timeout |

## References

- [Related doc](./related.md)
- ADR-001: Architecture overview
```

### Effective Cross-Referencing

```markdown
See [Session Protocol](.agents/SESSION-PROTOCOL.md) for full requirements.

This follows the pattern defined in ADR-043: Scoped Tool Execution.

Related memory: `engineering-knowledge-index`
```

## References

- Markdownlint config: `.markdownlint-cli2.yaml`
- ADR-043: Scoped tool execution for markdown linting
- ADR template: `.agents/architecture/ADR-TEMPLATE.md`
- Agent prompts steering: `.agents/steering/agent-prompts.md`

---

*Last updated: 2026-02-22 | Source: Issue #573*
