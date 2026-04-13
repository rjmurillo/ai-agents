# Linting Skills

Category: Code Quality and Documentation Standards

## Skill-Lint-001: Autofix Before Manual Edits

- **Statement**: Run `markdownlint --fix` before manual edits to auto-resolve spacing violations
- **Context**: Large-scale markdown linting with 100+ files
- **Atomicity**: 95%
- **Evidence**: 2025-12-13 markdown linting - auto-fixed 800+ MD031/MD032/MD022 spacing errors instantly
- **Impact**: Reduced manual edit effort by 60%
- **Tags**: helpful, high-impact

**Rationale**: Spacing rules (blank lines around fences, lists, headings) are mechanically fixable. Running auto-fix first clears the noise, leaving only semantic issues requiring judgment.

**Application**:

```bash
npx markdownlint-cli2 --fix "**/*.md"
```

---

## Skill-Lint-002: Document False Positives in Configuration

- **Statement**: Document known false positives in linting config comments with file locations
- **Context**: Nested code blocks in template files create unfixable lint errors
- **Atomicity**: 90%
- **Evidence**: 2025-12-13 - retrospective.md, roadmap.md nested templates trigger MD040 incorrectly
- **Impact**: Prevents future confusion and wasted debugging time
- **Tags**: helpful, documentation

**Rationale**: Some valid markdown patterns (e.g., markdown templates containing mermaid diagrams inside code fences) confuse linters. Rather than disabling rules globally, document specific known false positives.

**Application**:

```yaml
# In .markdownlint-cli2.yaml
config:
  # Note: 3 known false positives in nested template files (retrospective.md, roadmap.md)
  # where closing fences of outer markdown blocks are misidentified as new blocks
  MD040: true
```

---

## Skill-Lint-003: Batch Fixes by Directory

- **Statement**: Fix lint violations in directory batches with atomic commits per batch
- **Context**: Multi-directory repositories with related file groups
- **Atomicity**: 88%
- **Evidence**: 2025-12-13 - fixed claude/ (18 files), vs-code-agents/ (17), copilot-cli/ (17) sequentially
- **Impact**: Enabled incremental verification and easy rollback per directory
- **Tags**: helpful, workflow

**Rationale**: Large codebases are easier to fix, review, and commit in logical batches. Each batch can be verified independently before moving to the next.

**Application**:

1. Fix claude/ -> verify -> commit
2. Fix vs-code-agents/ -> verify -> commit
3. Fix copilot-cli/ -> verify -> commit
4. Fix root docs/ -> verify -> commit

---

## Skill-Lint-004: Configuration Before Fixes

- **Statement**: Create linting configuration file first to establish baseline before any fixes
- **Context**: New linting implementation in existing codebase
- **Atomicity**: 92%
- **Evidence**: 2025-12-13 - .markdownlint-cli2.yaml created first, enabled consistent auto-fix behavior
- **Impact**: Ensures all subsequent fixes align with final configuration
- **Tags**: helpful, sequence

**Rationale**: Without configuration first, auto-fix may apply default rules that later conflict with desired settings. Configuration-first ensures consistency.

**Application**:

1. Create `.markdownlint-cli2.yaml` with all rule decisions
2. Disable rules inappropriate for context (MD013 for long tool lists)
3. Enable required rules (MD040 for syntax highlighting)
4. Run linting to establish baseline violation count
5. Begin fixes with consistent configuration

---

## Skill-Lint-005: Exclude Generated Directories

- **Statement**: Exclude generated artifact directories from linting using both globs and ignores
- **Context**: Agent-generated content that may not conform to standards
- **Atomicity**: 90%
- **Evidence**: 2025-12-13 - `.agents/` excluded as ADRs/plans have different formatting needs
- **Impact**: Reduces false noise from non-source content
- **Tags**: helpful, configuration

**Application**:

```yaml
globs:
  - "**/*.md"
  - "!node_modules/**"
  - "!.agents/**"

ignores:
  - "node_modules/**"
  - ".agents/**"
```

---

## Skill-Lint-006: Language Identifier Selection

- **Statement**: Use `text` for pseudo-code and tool invocations, specific languages for real code
- **Context**: MD040 code block language identifier selection
- **Atomicity**: 93%
- **Evidence**: 2025-12-13 - memory protocol calls use `text`, JSON payloads use `json`
- **Impact**: Enables accurate syntax highlighting without false parsing
- **Tags**: helpful, standards

**Language Reference**:

| Content | Identifier |
|---------|------------|
| Memory tool invocations | `text` |
| JSON payloads | `json` |
| C# code | `csharp` |
| Shell commands | `bash` |
| YAML config | `yaml` |
| Markdown templates | `markdown` |

---

## Skill-Lint-007: Escape Generic Types as Inline Code

- **Statement**: Wrap .NET generic types in backticks to prevent MD033 inline HTML violations
- **Context**: C# documentation with generic types like `ArrayPool<T>`
- **Atomicity**: 95%
- **Evidence**: 2025-12-13 - implementer.md fixed `ArrayPool<T>`, `Span<T>`, `Vector256`
- **Impact**: Prevents types being misinterpreted as HTML tags
- **Tags**: helpful, dotnet

**Pattern**:

```markdown
<!-- Wrong - triggers MD033 -->
Use ArrayPool<T> for buffer pooling.

<!-- Correct -->
Use `ArrayPool<T>` for buffer pooling.
```

---

## Skill-Lint-008: Disable Non-Critical Style Rules

- **Statement**: Disable style rules that conflict with readability in specific contexts
- **Context**: Agent templates with long tool lists and tables
- **Atomicity**: 88%
- **Evidence**: 2025-12-13 - MD013 (line length) disabled for long tool descriptions
- **Impact**: Reduces false positives while maintaining critical standards
- **Tags**: helpful, pragmatic

**Disabled Rules**:

| Rule | Reason |
|------|--------|
| MD013 | Agent templates have long tool lists |
| MD060 | Tables render correctly regardless of spacing |
| MD029 | Sequential numbering (1/2/3) more readable than all-1s |

---

## Skill-Lint-009: Requirements Document Structure

- **Statement**: Create requirements document covering purpose, rules, examples, and troubleshooting
- **Context**: New linting standards documentation
- **Atomicity**: 85%
- **Evidence**: 2025-12-13 - docs/markdown-linting.md with comprehensive guidance
- **Impact**: Enables contributor self-service for common issues
- **Tags**: helpful, documentation

**Required Sections**:

1. Purpose and rationale
2. Configuration location and usage
3. Required rules with examples
4. Disabled rules with justification
5. Common patterns (memory protocol, workflow diagrams)
6. Troubleshooting guide
7. References to external documentation

---

## Anti-Patterns

### Anti-Lint-001: Manual Editing Every File

- **Statement**: Avoid manually editing each file individually for mechanical fixes
- **Evidence**: 2025-12-13 - initial manual approach was 10x slower than auto-fix
- **Atomicity**: 85%
- **Tags**: harmful, inefficient

**Prevention**: Always run `--fix` first for mechanical rules, reserve manual edits for semantic decisions.

### Anti-Lint-002: Disabling Rules Without Documentation

- **Statement**: Never disable linting rules without documenting the reason
- **Atomicity**: 90%
- **Tags**: harmful, maintenance-debt

**Prevention**: Add inline comments explaining why each disabled rule is disabled.

---

## Metrics

| Metric | Value |
|--------|-------|
| Files Fixed | 59 |
| Initial Violations | 1363 |
| Final Violations | 3 (known false positives) |
| Reduction | 99.8% |
| Time to Complete | ~3 hours |
| Auto-fix Rate | ~60% of violations |
