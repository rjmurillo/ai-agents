applyTo: "**/*.md"
excludeFrom: "src/claude/**/*.md,.agents/steering/**/*.md"

# Documentation Standards

Maintain consistent, clear documentation across all markdown files.

## Formatting

- Use proper heading hierarchy (# → ## → ###)
- Include front matter for structured documents (YAML)
- Use code blocks with language specifiers
- Include tables for structured data
- Use relative links for cross-references

## Structure

- **Title**: Clear, descriptive H1 heading
- **Overview**: Brief summary of purpose
- **Details**: Organized sections with clear headings
- **Examples**: Concrete examples where helpful
- **References**: Links to related documents

## Cross-References

Use relative paths from repository root:

```markdown
- [Agent System](.agents/AGENT-SYSTEM.md)
- [Naming Conventions](.agents/governance/naming-conventions.md)
```

## Code Examples

Always specify language for syntax highlighting:

````markdown
```csharp
public class Example { }
```
````

## Anti-Patterns to Avoid

- ❌ Broken links
- ❌ Missing metadata (for structured docs)
- ❌ Inconsistent heading levels
- ❌ Code blocks without language
- ❌ Absolute file paths

*Note: Full steering content to be implemented in Phase 4. See `.agents/steering/documentation.md` for placeholder.*
