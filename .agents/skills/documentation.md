# Documentation Skills

Category: Documentation Generation and Maintenance

## Skill-Doc-001: Code Block Language Identifiers

- **Statement**: Always specify language identifiers on fenced code blocks for syntax highlighting
- **Context**: Markdown documentation with code examples
- **Atomicity**: 95%
- **Evidence**: 2025-12-13 - 286 code blocks missing language identifiers fixed
- **Impact**: Enables proper syntax highlighting across GitHub, IDEs, and documentation tools
- **Tags**: helpful, standards

**Pattern**:

```markdown
<!-- Wrong -->
` ` `
public void Example() { }
` ` `

<!-- Correct -->
` ` `csharp
public void Example() { }
` ` `
```

---

## Skill-Doc-002: Blank Line Spacing Protocol

- **Statement**: Add blank lines before and after code blocks, lists, and headings
- **Context**: Markdown structure for consistent rendering
- **Atomicity**: 92%
- **Evidence**: 2025-12-13 - 350+ spacing violations auto-fixed with markdownlint
- **Impact**: Ensures consistent rendering across all markdown processors
- **Tags**: helpful, mechanical

**Rules**:

- MD022: Blank lines around headings
- MD031: Blank lines around fenced code blocks
- MD032: Blank lines around lists

---

## Skill-Doc-003: Agent Template Structure

- **Statement**: Maintain consistent structure across agent templates with frontmatter, tools, protocol, execution
- **Context**: Multi-agent codebase with parallel implementations
- **Atomicity**: 88%
- **Evidence**: 2025-12-13 - 59 agent files follow consistent section ordering
- **Impact**: Enables easy cross-reference and updates across platforms
- **Tags**: helpful, architecture

**Standard Sections**:

1. Frontmatter (platform-specific)
2. Core Identity / Claude Code Tools
3. Protocol / Mission
4. Memory Protocol
5. Execution / Best Practices
6. Handoff Protocol

---

## Skill-Doc-004: Platform Parity Documentation

- **Statement**: Keep parallel implementations across platforms (Claude, VS Code, Copilot CLI) synchronized
- **Context**: Multi-platform agent repository
- **Atomicity**: 85%
- **Evidence**: 2025-12-13 - identical fixes applied to 18 Claude, 17 VS Code, 17 Copilot CLI files
- **Impact**: Ensures consistent behavior and documentation across all platforms
- **Tags**: helpful, maintenance

**Approach**:

1. Make changes to one platform first (typically Claude as reference)
2. Apply identical changes to other platforms
3. Verify consistency across all three
4. Commit in batches by platform for easy review

---

## Skill-Doc-005: ADR Documentation Pattern

- **Statement**: Create ADR documents for significant technical decisions with status, context, decision, consequences
- **Context**: Architecture decision records for linting and configuration
- **Atomicity**: 90%
- **Evidence**: 2025-12-13 - ADR-001-markdown-linting.md created with full justification
- **Impact**: Preserves decision rationale for future reference
- **Tags**: helpful, governance

**Template**:

```markdown
# ADR-NNN: Title

## Status
[Proposed | Accepted | Deprecated | Superseded]

## Context
[Problem and constraints]

## Decision
[What we decided and why]

## Consequences
### Positive
- [Benefits]

### Negative
- [Drawbacks]

### Mitigations
- [How to address negatives]
```

---

## Skill-Doc-006: Requirements Document Structure

- **Statement**: Structure requirements documents with purpose, configuration, rules, examples, troubleshooting
- **Context**: Creating developer-facing requirements documentation
- **Atomicity**: 88%
- **Evidence**: 2025-12-13 - docs/markdown-linting.md provides complete self-service guidance
- **Impact**: Reduces support burden and enables contributor self-service
- **Tags**: helpful, usability

**Sections**:

1. **Purpose**: Why these requirements exist
2. **Configuration**: Where settings live and how to run tools
3. **Required Rules**: What must be followed with examples
4. **Disabled Rules**: What's intentionally disabled and why
5. **Common Patterns**: Reusable snippets for typical cases
6. **Troubleshooting**: Fixes for common errors
7. **References**: Links to external documentation

---

## Skill-Doc-007: Commit Message Scoping

- **Statement**: Use directory-based scopes in conventional commits for multi-directory fixes
- **Context**: Atomic commits across platform directories
- **Atomicity**: 90%
- **Evidence**: 2025-12-13 - fix(claude), fix(vs-code), fix(copilot-cli), fix(docs) scopes used
- **Impact**: Enables targeted review and selective rollback
- **Tags**: helpful, git-workflow

**Pattern**:

```text
fix(claude): resolve markdown lint violations
fix(vs-code): resolve markdown lint violations
fix(copilot-cli): resolve markdown lint violations
fix(docs): resolve markdown lint violations
```

---

## Skill-Doc-008: Violation Analysis Before Fixes

- **Statement**: Analyze and categorize all violations before starting fixes to prioritize and batch work
- **Context**: Large-scale documentation cleanup
- **Atomicity**: 87%
- **Evidence**: 2025-12-13 - analyst phase identified 1363 violations categorized by rule and severity
- **Impact**: Enables efficient fix ordering and effort estimation
- **Tags**: helpful, planning

**Analysis Output**:

| Rule | Description | Count | Severity | Auto-fixable |
|------|-------------|-------|----------|--------------|
| MD040 | Code language | 286 | High | No (manual) |
| MD013 | Line length | 200+ | Medium | Disable |
| MD031 | Fence spacing | 150+ | Medium | Yes |
| MD032 | List spacing | 100+ | Medium | Yes |

---

## Skill-Doc-009: Pre-implementation Plan Validation

- **Statement**: Validate implementation plans with critic review before execution
- **Context**: Complex multi-file changes
- **Atomicity**: 85%
- **Evidence**: 2025-12-13 - critic approved plan, identified 3 minor improvements
- **Impact**: Catches issues before costly implementation
- **Tags**: helpful, workflow

**Validation Checklist**:

- [ ] All requirements addressed
- [ ] Technical approach is sound
- [ ] Scope is appropriate
- [ ] Timeline is realistic
- [ ] Risks identified with mitigations
- [ ] Acceptance criteria defined

---

## Skill-Doc-010: QA Verification Pattern

- **Statement**: Verify documentation changes with before/after metrics and explicit pass/fail status
- **Context**: Validating documentation quality improvements
- **Atomicity**: 88%
- **Evidence**: 2025-12-13 - QA report showed 1363 -> 3 violations (99.8% reduction)
- **Impact**: Provides objective evidence of success
- **Tags**: helpful, quality

**Verification Template**:

```markdown
## Test Results

**Before**: [count] violations
**After**: [count] violations (known exceptions)
**Reduction**: [percentage]%

| Test | Status | Notes |
|------|--------|-------|
| Config exists | PASS | |
| Syntax valid | PASS | |
| Exclusions work | PASS | |
```

---

## Anti-Patterns

### Anti-Doc-001: Inconsistent Platform Updates

- **Statement**: Avoid updating one platform without updating parallel implementations
- **Atomicity**: 85%
- **Tags**: harmful, drift

**Prevention**: Always update Claude, VS Code, and Copilot CLI together for agent changes.

### Anti-Doc-002: Undocumented Rule Changes

- **Statement**: Never disable or modify linting rules without documenting rationale
- **Atomicity**: 90%
- **Tags**: harmful, maintenance-debt

**Prevention**: Add inline comments for every disabled rule explaining the business reason.

---

---

## Skill-Doc-011: Markdown Fence Closing Fix Pattern

- **Statement**: Detect and repair malformed code fence closings where closing fences have language identifiers (e.g., ` ` `text) instead of plain closing fences (` ` `)
- **Context**: Markdown documents where agents incorrectly add language identifiers to closing fences
- **Atomicity**: 92%
- **Evidence**: 2025-12-13 - fix-fences.ps1 script developed by multiple agents independently, solving common closing fence issue
- **Impact**: Prevents linting failures and avoids token waste from repeated fixes
- **Tags**: helpful, automation, markdown

**Problem**:

Code fences should have language identifiers on opening fences only:

```markdown
<!-- Wrong -->
` ` `text
code
` ` `text

<!-- Correct -->
` ` `text
code
` ` `
```

**Solution** (PowerShell):

```powershell
# Fix malformed code fence closings in markdown files
# The issue: closing fences have language identifiers (` ` `text) instead of just (` ` `)

$directories = @('vs-code-agents', 'copilot-cli')

foreach ($dir in $directories) {
    Get-ChildItem -Path $dir -Filter '*.md' -Recurse | ForEach-Object {
        $file = $_.FullName
        $content = Get-Content $file -Raw

        # Split into lines
        $lines = $content -split "`r?`n"
        $result = @()
        $inCodeBlock = $false
        $codeBlockIndent = ""

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i]

            # Check if this line starts a code block
            if ($line -match '^(\s*)```(\w+)') {
                if ($inCodeBlock) {
                    # This is supposed to be a closing fence but has a language - fix it
                    $result += $codeBlockIndent + '```'
                    # Now this line is actually starting a new code block
                    $result += $line
                    $codeBlockIndent = $Matches[1]
                    $inCodeBlock = $true
                } else {
                    # Starting a new code block
                    $result += $line
                    $codeBlockIndent = $Matches[1]
                    $inCodeBlock = $true
                }
            }
            elseif ($line -match '^(\s*)```\s*$') {
                # Plain closing fence
                $result += $line
                $inCodeBlock = $false
                $codeBlockIndent = ""
            }
            else {
                $result += $line
            }
        }

        # Handle case where file ends inside a code block
        if ($inCodeBlock) {
            $result += $codeBlockIndent + '```'
        }

        # Write back
        $newContent = $result -join "`n"
        Set-Content -Path $file -Value $newContent -NoNewline
        Write-Host "Fixed: $file"
    }
}
```

**Usage**:

1. Place script in repository root as `fix-fences.ps1`
2. Run: `pwsh ./fix-fences.ps1` (PowerShell 7+) or `powershell ./fix-fences.ps1` (Windows PowerShell)
3. Verify changes with: `git diff`
4. Commit fixes

**Key Algorithm**:

- Tracks whether currently inside a code block
- Detects opening fences with language identifiers (` ` `text)
- Detects closing fences (` ` ` alone on line)
- When opening fence is found while inside block, closes current block first
- Handles indented code blocks (preserves indentation)
- Handles files ending inside code blocks

---

## Metrics

| Metric | Value |
|--------|-------|
| Agent Templates Updated | 52 |
| Documentation Files Created | 2 |
| ADRs Created | 1 |
| Platforms Synchronized | 3 |
| Automation Skills (fix-fences) | 1 |
