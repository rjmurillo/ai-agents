# Claude.md Anthropic Best Practices Integration

## Summary

Research from Anthropic's official guidance on CLAUDE.md files (2025-01-04).

## Key Recommendations from Anthropic

### File Size

Claude Code docs say to target under 200 lines per CLAUDE.md file. It is a target, not a limit. The "200 lines or 25KB" figure is the auto memory MEMORY.md load cap, not a CLAUDE.md limit. Source: https://code.claude.com/docs/en/memory (checked 2026-09-23). CLAUDE.md loads every session, so length costs tokens and adherence.

### @imports Pattern

```markdown
@path/to/additional-context.md
```

- Recursive imports (max depth 5)
- Import critical subset, keep details on-demand
- Can import from home directory

### .claude/rules/ Directory

For larger projects, use `.claude/rules/` for modular rule files.

### Hierarchical CLAUDE.md

- Root: Team conventions
- Subdirectories: Module-specific guidance (loaded on-demand)
- Home: Personal preferences

### Anti-Patterns

1. Don't use LLM for linting (use actual linters)
2. Don't add excessive content without iteration
3. Use /clear between distinct tasks
4. Avoid monolithic files

## ai-agents Project Status

| Aspect | Status |
|--------|--------|
| File size (66 lines) | ALIGNED |
| @imports | NOT USED - opportunity |
| .claude/rules/ | NOT USED |
| Hierarchical files | NOT USED |
| Custom commands | ALIGNED (40+ commands) |
| Linting delegation | ALIGNED (markdownlint-cli2) |

## Implementation Opportunities

1. Create CRITICAL-CONTEXT.md (~50 lines) with blocking gates
2. Add @import to CLAUDE.md for auto-loading
3. Add subdirectory CLAUDE.md files
4. Document /init and /clear commands

## Token Impact

- @import critical context: +400 tokens/session (auto)
- Eliminates tool calls for basic constraints
- Net positive for quick tasks

## Related

- Analysis: `.project-toolkit/analysis/claude-md-best-practices-anthropic.md`
- Memory: [memory-token-efficiency](../memory/memory-token-efficiency.md)
- ADR: ADR-007 (Memory First)
- [claude-code-hooks-opportunity-analysis](claude-code-hooks-opportunity-analysis.md)
- [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md)
- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
- [claude-code-slash-commands](claude-code-slash-commands.md)
- [claude-flow-research-2025-12-20](claude-flow-research-2025-12-20.md)

## Source

https://www.claude.com/blog/using-claude-md-files

## Related

- [claude-code-hooks-opportunity-analysis](claude-code-hooks-opportunity-analysis.md)
- [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md)
- [claude-code-skills-official-guidance](claude-code-skills-official-guidance.md)
- [claude-code-slash-commands](claude-code-slash-commands.md)
- [claude-flow-research-2025-12-20](claude-flow-research-2025-12-20.md)
