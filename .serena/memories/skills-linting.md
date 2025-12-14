# Linting Skills

Category: Code Quality and Documentation Standards
Source: `.agents/skills/linting.md`
Migrated: 2025-12-13

## High-Impact Skills (90%+ Atomicity)

### Skill-Lint-001: Autofix Before Manual Edits (95%)

- **Statement**: Run `markdownlint --fix` before manual edits to auto-resolve spacing violations
- **Context**: Large-scale markdown linting with 100+ files
- **Evidence**: 2025-12-13 - auto-fixed 800+ MD031/MD032/MD022 spacing errors instantly
- **Impact**: Reduced manual edit effort by 60%
- **Application**: `npx markdownlint-cli2 --fix "**/*.md"`

### Skill-Lint-004: Configuration Before Fixes (92%)

- **Statement**: Create linting configuration file first to establish baseline before any fixes
- **Context**: New linting implementation in existing codebase
- **Evidence**: 2025-12-13 - `.markdownlint-cli2.yaml` created first, enabled consistent auto-fix behavior

### Skill-Lint-006: Language Identifier Selection (93%)

- **Statement**: Use `text` for pseudo-code and tool invocations, specific languages for real code
- **Context**: MD040 code block language identifier selection
- **Reference Table**:
  - Memory tool invocations: `text`
  - JSON payloads: `json`
  - C# code: `csharp`
  - Shell commands: `bash`
  - YAML config: `yaml`
  - Markdown templates: `markdown`

### Skill-Lint-007: Escape Generic Types as Inline Code (95%)

- **Statement**: Wrap .NET generic types in backticks to prevent MD033 inline HTML violations
- **Context**: C# documentation with generic types
- **Pattern**: Use `ArrayPool<T>` not bare generic types

## Medium-Impact Skills (85-90% Atomicity)

### Skill-Lint-002: Document False Positives (90%)

- **Statement**: Document known false positives in linting config comments with file locations
- **Evidence**: retrospective.md, roadmap.md nested templates trigger MD040 incorrectly

### Skill-Lint-003: Batch Fixes by Directory (88%)

- **Statement**: Fix lint violations in directory batches with atomic commits per batch
- **Pattern**: Fix claude/ -> verify -> commit, then vs-code-agents/, then copilot-cli/

### Skill-Lint-005: Exclude Generated Directories (90%)

- **Statement**: Exclude generated artifact directories from linting using both globs and ignores
- **Example**: `.agents/` excluded as ADRs/plans have different formatting needs

### Skill-Lint-008: Disable Non-Critical Style Rules (88%)

- **Statement**: Disable style rules that conflict with readability in specific contexts
- **Disabled**: MD013 (line length), MD060 (table spacing), MD029 (list prefix)

### Skill-Lint-009: Requirements Document Structure (85%)

- **Statement**: Create requirements document covering purpose, rules, examples, and troubleshooting

## Anti-Patterns

### Anti-Lint-001: Manual Editing Every File

- Avoid manually editing each file individually for mechanical fixes
- **Prevention**: Always run `--fix` first

### Anti-Lint-002: Disabling Rules Without Documentation

- Never disable linting rules without documenting the reason
- **Prevention**: Add inline comments explaining why

## Metrics

- Files Fixed: 59
- Initial Violations: 1363
- Final Violations: 3 (known false positives)
- Reduction: 99.8%
- Auto-fix Rate: ~60% of violations
