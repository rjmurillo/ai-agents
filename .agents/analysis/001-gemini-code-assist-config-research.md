# Analysis: Google Gemini Code Assist Configuration Research

## Value Statement

Complete understanding of Gemini Code Assist configuration options enables proper setup for automated code review while excluding agent artifacts and memory files from review scope.

## Business Objectives

- Enable automated code review on all pull requests
- Exclude agent-generated files (`.agents/**`, `.serena/memories/**`) from review
- Disable PR summaries to reduce noise
- Support draft PR reviews for early feedback
- Establish project-specific coding standards via style guide

## Context

The ai-agents repository uses a multi-agent system that generates artifacts in `.agents/` and stores memories in `.serena/memories/`. These files should not be reviewed by Gemini Code Assist as they are agent-managed. The project needs proper configuration to enable code review on actual source code while excluding these paths.

## Methodology

1. Fetched official Google documentation from https://developers.google.com/gemini-code-assist/docs/customize-gemini-behavior-github
2. Extracted complete JSON schema for `config.yaml`
3. Researched path exclusion pattern syntax (VS Code glob patterns)
4. Documented style guide format requirements
5. Identified all code review configuration options
6. Created comprehensive skill file at `.serena/memories/skills-gemini-code-assist.md`

## Findings

### Facts (Verified)

#### Configuration File Structure

**Location**: `.gemini/config.yaml` at repository root

**Complete Schema** (all fields optional with defaults):

```yaml
have_fun: boolean (default: false)
  # Enables fun features like poems in PR summaries

memory_config:
  disabled: boolean (default: false)
    # Disable persistent memory for this repository

code_review:
  disable: boolean (default: false)
    # Completely disables Gemini on PRs

  comment_severity_threshold: enum (default: MEDIUM)
    # Values: LOW, MEDIUM, HIGH, CRITICAL

  max_review_comments: integer (default: -1)
    # -1 = unlimited comments

  pull_request_opened:
    help: boolean (default: false)
      # Post help message on PR open

    summary: boolean (default: true)
      # Post PR summary on open

    code_review: boolean (default: true)
      # Post code review on open

    include_drafts: boolean (default: true)
      # Enable on draft PRs

ignore_patterns: array of strings (default: [])
  # Glob patterns for files to skip
```

#### Path Exclusion Patterns

**Field**: `ignore_patterns`
**Syntax**: [VS Code glob patterns](https://code.visualstudio.com/docs/editor/glob-patterns)

**Key Patterns**:
- `**/*.ext` - All files with extension recursively
- `**/folder/**` - Entire directory tree
- `folder/*` - Direct children only
- `!pattern` - Negation (include exception)

**Required for ai-agents**:
```yaml
ignore_patterns:
  - ".agents/**"           # Agent artifacts
  - ".serena/memories/**"  # Memory storage
```

#### Style Guide Format

**Location**: `.gemini/styleguide.md` at repository root

**Format**:
- Natural language Markdown (no strict schema)
- Extends standard review categories
- Combined with group-level guides (not replaced)

**Standard Review Categories** (when no custom guide):
1. Correctness - Logic, edge cases, API usage
2. Efficiency - Performance, memory, optimization
3. Maintainability - Readability, naming, documentation
4. Security - Vulnerabilities, input validation
5. Miscellaneous - Testing, scalability, monitoring

#### Recommended Configuration for ai-agents

**`.gemini/config.yaml`**:
```yaml
code_review:
  disable: false
  pull_request_opened:
    code_review: true      # Enable reviews
    summary: false         # Disable summaries (reduce noise)
    include_drafts: true   # Review drafts
    help: false
  comment_severity_threshold: MEDIUM
  max_review_comments: -1  # Unlimited

ignore_patterns:
  - ".agents/**"
  - ".serena/memories/**"
  - "**/*.generated.*"
  - "**/bin/**"
  - "**/obj/**"

have_fun: false
memory_config:
  disabled: false
```

**`.gemini/styleguide.md`** should include:
- PowerShell scripting standards (PascalCase, approved verbs)
- Markdown linting (markdownlint-cli2 compliance)
- Agent protocol patterns (handoff format, memory usage)
- Security requirements (input validation, injection prevention)
- Git commit conventions (conventional commits)
- Documentation standards (ADR format, RFC 2119 keywords)

#### Configuration Precedence

**Enterprise Version**:
- Repository `config.yaml` **overrides** group settings
- Exception: "Improve response quality" can only be disabled, not enabled
- Repository `styleguide.md` **combines** with group guide

**Consumer Version**:
- Per-account toggle via Code review page

### Hypotheses (Unverified)

1. **Glob Pattern Performance**: Unknown if complex patterns impact review speed
2. **Style Guide Length Limits**: No documented maximum length for styleguide.md
3. **Path Exclusion Scope**: Unclear if exclusions apply to summary generation or only review comments
4. **Draft PR Behavior**: Unknown if `include_drafts: false` prevents all Gemini activity or just reviews

## Recommendations

### Immediate Actions (for Implementer Agent)

1. **Create `.gemini/config.yaml`** with:
   - Code review enabled
   - Summaries disabled (`summary: false`)
   - Draft PRs included (`include_drafts: true`)
   - Agent paths excluded (`.agents/**`, `.serena/memories/**`)

2. **Create `.gemini/styleguide.md`** with:
   - PowerShell scripting standards
   - Markdown linting rules
   - Security requirements
   - Conventional commit format
   - Agent protocol patterns

3. **Test Configuration**:
   - Create test PR to verify path exclusions work
   - Confirm reviews appear but summaries don't
   - Validate style guide rules are applied

### Best Practices

**Path Exclusions**:
- Include build outputs (`**/bin/**`, `**/obj/**`)
- Include generated files (`**/*.generated.*`)
- Exclude agent artifacts (`.agents/**`)
- Exclude memory stores (`.serena/memories/**`)

**Code Review Settings**:
- Disable summaries if PR titles/descriptions are sufficient
- Use MEDIUM threshold to avoid noise
- Keep `max_review_comments: -1` for comprehensive feedback

**Style Guide Content**:
- Be specific and actionable
- Include code examples
- Link to external standards rather than copy-pasting
- Keep concise (avoid walls of text)

## Open Questions

1. **Path Exclusion Verification**: How to confirm patterns are working? (Test with PR)
2. **Style Guide Effectiveness**: How long before custom rules appear in reviews? (Immediate or cached?)
3. **Memory Persistence**: What does `memory_config.disabled` actually disable? (Not documented)
4. **Comment Threading**: Can Gemini respond to review comments or only post initial reviews?

## Next Steps

**Recommended Route**: `analyst` -> `implementer`

**For Implementer**:
1. Read skill file using `mcp__serena__read_memory` with `memory_file_name="skills-gemini-code-assist"`
2. Create `.gemini/config.yaml` with recommended settings
3. Create `.gemini/styleguide.md` with project-specific standards
4. Commit changes
5. Create test PR to validate configuration

**Validation Criteria**:
- Path exclusions verified (`.agents/**` files not reviewed)
- Summaries disabled (no summary comment on PR)
- Code review appears
- Style guide rules applied

## Evidence Sources

- **Official Documentation**: https://developers.google.com/gemini-code-assist/docs/customize-gemini-behavior-github
- **Complete JSON Schema**: Extracted from documentation
- **Glob Pattern Reference**: https://code.visualstudio.com/docs/editor/glob-patterns
- **Skill File**: Use `mcp__serena__read_memory` with `memory_file_name="skills-gemini-code-assist"`
