# Documentation Skills

Category: Documentation Generation and Maintenance
Source: `.agents/skills/documentation.md`
Migrated: 2025-12-13

## High-Impact Skills (90%+ Atomicity)

### Skill-Doc-001: Code Block Language Identifiers (95%)

- **Statement**: Always specify language identifiers on fenced code blocks for syntax highlighting
- **Evidence**: 2025-12-13 - 286 code blocks missing language identifiers fixed
- **Impact**: Enables proper syntax highlighting across GitHub, IDEs, and documentation tools

### Skill-Doc-002: Blank Line Spacing Protocol (92%)

- **Statement**: Add blank lines before and after code blocks, lists, and headings
- **Rules**: MD022 (headings), MD031 (code blocks), MD032 (lists)
- **Evidence**: 350+ spacing violations auto-fixed with markdownlint

### Skill-Doc-005: ADR Documentation Pattern (90%)

- **Statement**: Create ADR documents for significant technical decisions
- **Template Sections**: Status, Context, Decision, Consequences (Positive/Negative/Mitigations)
- **Evidence**: ADR-001-markdown-linting.md created with full justification

### Skill-Doc-007: Commit Message Scoping (90%)

- **Statement**: Use directory-based scopes in conventional commits for multi-directory fixes
- **Pattern**: `fix(claude):`, `fix(vs-code):`, `fix(copilot-cli):`, `fix(docs):`
- **Impact**: Enables targeted review and selective rollback

### Skill-Doc-011: Markdown Fence Closing Fix Pattern (92%)

- **Statement**: Detect and repair malformed code fence closings where closing fences have language identifiers
- **Problem**: ` ` `text ...` ` `text (wrong) vs ` ` `text ...` ` ` (correct)
- **Solution**: Use fix-fences.ps1 or fix_fences.py utility
- **Impact**: Prevents linting failures and token waste from repeated fixes

## Medium-Impact Skills (85-90% Atomicity)

### Skill-Doc-003: Agent Template Structure (88%)

- **Statement**: Maintain consistent structure across agent templates
- **Sections**: Frontmatter, Core Identity, Protocol, Memory Protocol, Execution, Handoff Protocol

### Skill-Doc-004: Platform Parity Documentation (85%)

- **Statement**: Keep parallel implementations across platforms synchronized
- **Approach**: Make changes to Claude first, apply to VS Code and Copilot CLI, verify consistency

### Skill-Doc-006: Requirements Document Structure (88%)

- **Sections**: Purpose, Configuration, Required Rules, Disabled Rules, Common Patterns, Troubleshooting, References

### Skill-Doc-008: Violation Analysis Before Fixes (87%)

- **Statement**: Analyze and categorize all violations before starting fixes
- **Output**: Rule, Description, Count, Severity, Auto-fixable table

### Skill-Doc-009: Pre-implementation Plan Validation (85%)

- **Statement**: Validate implementation plans with critic review before execution
- **Checklist**: Requirements addressed, Technical approach sound, Scope appropriate, Risks identified

### Skill-Doc-010: QA Verification Pattern (88%)

- **Statement**: Verify documentation changes with before/after metrics and explicit pass/fail status
- **Template**: Before count, After count, Reduction %, Test table with Status

## Documentation Maintenance Skills (Migration-Specific)

### Skill-Documentation-Maintenance-001: Pattern Migration Search Protocol (95%)

- **Statement**: Search entire codebase for pattern before migration to identify all references
- **Context**: When migrating documentation patterns or memory references
- **Evidence**: 2025-12-18 - Grep search for memory pattern identified 16 files; prevented missing references during Serena migration
- **Impact**: Ensures comprehensive migration without orphaned references
- **Validation**: 1 successful execution

### Skill-Documentation-Maintenance-002: Reference Categorization Before Migration (95%)

- **Statement**: Categorize references as instructive (update), informational (skip), or operational (skip) before migration
- **Context**: When migrating patterns that appear in different contexts
- **Evidence**: 2025-12-18 - Type distinction (instructive vs informational vs operational) prevented inappropriate updates during Serena migration
- **Impact**: Prevents over-updating content that shouldn't change
- **Validation**: 1 successful execution

### Skill-Documentation-Maintenance-003: Fallback Clause for Tool Migration (96%)

- **Statement**: Include fallback clause when migrating to tool calls for graceful degradation
- **Context**: When replacing text patterns with tool invocations in documentation
- **Evidence**: 2025-12-18 - Added 5 fallback clauses ("with Serena fallback") during migration; ensures clarity about alternative approaches
- **Impact**: Documents graceful degradation paths when tools are unavailable
- **Validation**: 1 successful execution

### Skill-Documentation-Maintenance-004: Consistent Migration Syntax (96%)

- **Statement**: Use identical syntax for all instances when migrating patterns to maintain consistency
- **Context**: When applying pattern replacements across multiple files
- **Evidence**: 2025-12-18 - Applied same format across 16 files during Serena migration; maintained documentation coherence
- **Impact**: Ensures predictable, maintainable documentation structure
- **Validation**: 1 successful execution

## Anti-Patterns

### Anti-Doc-001: Inconsistent Platform Updates

- Avoid updating one platform without updating parallel implementations
- **Prevention**: Always update Claude, VS Code, and Copilot CLI together

### Anti-Doc-002: Undocumented Rule Changes

- Never disable or modify linting rules without documenting rationale

## Metrics

- Agent Templates Updated: 52
- Documentation Files Created: 2
- ADRs Created: 1
- Platforms Synchronized: 3

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-agent-workflow-phase3](skills-agent-workflow-phase3.md)
- [skills-agent-workflows](skills-agent-workflows.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-analysis](skills-analysis.md)
