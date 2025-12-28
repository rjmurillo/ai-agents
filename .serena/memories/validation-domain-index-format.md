# Skill-Validation-001: Domain Index Table-Only Format

**Statement**: Domain index files must contain ONLY activation vocabulary table - no headers, prose, or extra content.

**Context**: Creating or editing skills-*-index.md files

**Evidence**: CI validation failure when `skills-git-index.md` contained `# Git Skills Index` header. Validation script expects pure table format.

**Atomicity**: 92% | **Impact**: 8/10

## Pattern

Domain index files (skills-*-index.md) must follow this exact format:

```markdown
| Keywords | File |
|----------|------|
| keyword1 keyword2 keyword3 | memory-file-name |
| keyword4 keyword5 keyword6 | another-memory-file |
```

**Rules**:
- NO markdown headers (# Title)
- NO prose or explanatory text
- NO blank lines except at file end
- ONLY the activation vocabulary table

## Anti-Pattern

```markdown
# Git Skills Index

This index contains git-related skills.

| Keywords | File |
|----------|------|
| ... | ... |
```

**Why It Fails**: Validation scripts (pwsh scripts/Validate-MemoryIndex.ps1) expect pure table format for parsing.

## Related

- **BLOCKS**: Domain index creation
- **ENABLES**: CI validation success

**Tag**: critical
**Category**: Memory Structure
**Validated**: 1 (skills-git-index.md header removal fixed CI)
