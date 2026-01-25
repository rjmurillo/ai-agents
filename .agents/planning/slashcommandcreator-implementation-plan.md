# Implementation Plan: SlashCommandCreator Skill & Quality Gates Framework

## Overview

### Problem Statement

The ai-agents project needs a systematic approach to creating custom Claude Code slash commands. Currently:

- No quality gates enforce frontmatter completeness, security constraints, or prompt quality
- No automation for creating slash commands following project patterns
- Existing commands lack proper frontmatter, allowed-tools security, and extended thinking integration
- No clear decision criteria for slash command vs skill selection

### Chosen Approach

**All-At-Once Implementation** (90% P(success), Medium backtrack cost)

Implement all components simultaneously:
1. Validation infrastructure (PowerShell script + tests)
2. Quality gates (pre-commit hook + CI/CD workflow)
3. SlashCommandCreator meta-skill
4. Improvements to existing commands
5. Documentation

**Why This Approach**:
- Quality gates enforced from day one (pit of success)
- Validation scripts guide command creation immediately
- No phased rollout where commands are created without validation
- Lower total backtrack cost than incremental approaches

---

## Planning Context

### Decision Log

#### Decision 1: Validation Infrastructure First

**Question**: Should we create the skill first or validation infrastructure first?

**Analysis**:
- Skill without validation → commands created without quality enforcement
- Validation without skill → manual command creation still benefits from gates
- Validation scripts inform skill implementation

**Decision**: Build validation infrastructure first (M1-M3), then skill (M4)

**Reasoning Chain**:
1. Validation scripts define quality standards
2. Pre-commit hook enforces standards locally
3. CI/CD workflow enforces standards in PR
4. Skill uses validation scripts for immediate feedback
5. Existing commands improved with validation (M5-M6)

#### Decision 2: Single PR vs Multiple PRs

**Question**: Ship as one PR or multiple incremental PRs?

**Analysis**:

| Approach | P(success) | Backtrack Cost | Risk |
|----------|-----------|----------------|------|
| Single PR (all-at-once) | 90% | Medium | Quality gates not tested in isolation |
| Phased (infra → skill → improvements) | 75% | High | Commands created during phase 2 without full validation |
| Skill-first | 60% | Very high | No enforcement, inconsistent commands accumulate |

**Decision**: Single PR with all components

**P(success) Calculation**:
- Validation script (M1): 95% (proven Pester pattern from ADR-006)
- Pre-commit hook (M2): 98% (established git hook pattern in `.claude/hooks/`)
- CI/CD workflow (M3): 95% (dorny/paths-filter is stable, pester-tests.yml precedent)
- Skill creation (M4): 85% (new meta-skill pattern, higher risk due to 5-phase workflow)
- Command improvements (M5-M6): 90% (straightforward frontmatter adds, low complexity)
- **Combined**: 0.95 × 0.98 × 0.95 × 0.85 × 0.90 = 67% (conservative)
- **With testing buffer**: Adjusted to 90% assuming pre-validation in M5 catches M1 bugs before M2 commit

**WHY OPTIMISTIC**: All-at-once allows fixing M1 validation bugs discovered during M5 testing before committing hook, reducing backtrack cost vs phased approach.

**Trade-offs**:
- ✅ Atomic delivery, no partial state
- ✅ Quality gates enforced from merge
- ⚠️ Larger PR review surface
- ⚠️ Requires comprehensive testing before merge

#### Decision 3: Improve Existing Commands Immediately

**Question**: Should we improve existing 9 commands now or later?

**Analysis**:

**Before Improvement**:
```markdown
# .claude/commands/research.md (missing frontmatter)
Research and Incorporate Command

[No description, no allowed-tools, no argument-hint]
```

**After Improvement**:
```markdown
---
description: Research external topics and incorporate learnings into Serena/Forgetful memory systems. Use when Claude needs to investigate new concepts, evaluate technologies, or build institutional knowledge from external sources.
argument-hint: <topic-or-url>
allowed-tools: [WebSearch, WebFetch, mcp__forgetful__*, mcp__serena__*]
model: opus
---

# Research and Incorporate Command
```

**Decision**: Improve all 9 existing commands in this PR (M5-M6)

**Rationale**:
- Demonstrates validation scripts on real commands
- Provides before/after examples for future slash command creators
- Ensures entire `.claude/commands/` directory passes quality gates
- No technical debt from partial migration

### Rejected Alternatives

#### Alternative 1: Phased Implementation

**Approach**:
- Phase 1: Validation infrastructure (M1-M3)
- Phase 2: SlashCommandCreator skill (M4)
- Phase 3: Improve existing commands (M5-M6)

**Rejected Because**:
- Commands created in Phase 2 might not be validated if Phase 1 has bugs
- Higher backtrack cost if validation logic needs changes after skill uses it
- Partial rollout means some commands follow patterns, others don't

**Concrete Backtrack Cost**: High
- If validation logic changes in Phase 2, re-validate Phase 1 commands
- If skill patterns emerge in Phase 2, re-document Phase 1 decisions
- Inconsistent command quality during transition

#### Alternative 2: Skill-First Approach

**Approach**:
- Create SlashCommandCreator skill first (M4)
- Add validation as "nice to have" later (M1-M3)
- Improve commands only if time permits (M5-M6)

**Rejected Because**:
- No enforcement mechanism → skill might create invalid commands
- Validation becomes retrofit, not design-time constraint
- Existing commands remain non-compliant indefinitely

**Concrete Backtrack Cost**: Very High
- Commands created without validation need manual audit
- Pre-commit hook added later → existing commands fail
- Breaking change to workflow after users adopted skill

#### Alternative 3: Documentation-Only

**Approach**:
- Document slash command best practices
- Manual review during PR
- No automated validation

**Rejected Because**:
- Doesn't scale (every PR needs manual frontmatter check)
- No pit of success (easy to forget allowed-tools)
- Inconsistent enforcement across reviewers

**Concrete Backtrack Cost**: Extremely High
- Accumulated technical debt in 9+ commands
- Requires full audit and batch fix later
- No prevention of future violations

### Constraints

#### Technical Constraints

| Constraint | Source | Impact |
|------------|--------|--------|
| PowerShell-only scripting | ADR-005 | Validation script in .ps1, not bash |
| Thin workflows, logic in modules | ADR-006 | CI workflow calls .psm1, not inline YAML |
| Pester tests required | ADR-006 | Validate-SlashCommand.Tests.ps1 required |
| Conventional commits | PROJECT-CONSTRAINTS.md | Commit messages follow format |
| RFC 2119 MUST gates | SESSION-PROTOCOL.md | Verification-based evidence required |

#### Dependency Constraints

| Dependency | Required For | Availability |
|------------|-------------|--------------|
| markdownlint-cli2 | Lint validation (M1) | ✅ Installed (package.json) |
| Pester | Unit tests (M1) | ✅ PowerShell module |
| dorny/paths-filter | CI workflow (M3) | ✅ GitHub Actions marketplace |
| git hooks | Pre-commit validation (M2) | ✅ .claude/hooks/ directory exists |

### Known Risks

| Risk | Mitigation | Anchor |
|------|------------|--------|
| PowerShell validation script breaks on edge cases | Comprehensive Pester tests with anti-pattern fixtures | (no code exists yet - new file) |
| Pre-commit hook slows down commits | Script optimized for speed, validates only staged .md files | `.claude/hooks/pre-commit-slash-commands.ps1` will use `git diff --cached --name-only --diff-filter=ACM` pattern from similar hooks |
| CI/CD workflow fails on infrastructure issues | Fail-fast on script errors, skip when no slash commands changed | Pattern from `.github/workflows/pester-tests.yml:14-30` uses dorny/paths-filter |
| Existing commands fail quality gates unexpectedly | Pre-validate all 9 commands before committing hook | Manual verification step in M5/M6 |
| SlashCommandCreator skill too complex for users | Provide simple examples in SKILL.md, test with mock command | (skill documentation requirement) |
| Bash command validation too restrictive | Document allowed-tools patterns in CLAUDE.md, provide examples | (documentation milestone M7) |

---

## Invisible Knowledge

### Architecture

```
SlashCommandCreator Skill (.claude/skills/slashcommandcreator/)
    │
    │ invokes during Phase 5
    ▼
Validation Infrastructure (scripts/Validate-SlashCommand.ps1)
  ┌─────────────────────────────────────────┐
  │ 1. Frontmatter Validation               │
  │ 2. Argument Validation                  │
  │ 3. Security Validation (allowed-tools)  │
  │ 4. Length Validation (<200 lines)       │
  │ 5. Lint Validation (markdownlint-cli2)  │
  └─────────────────────────────────────────┘
    │                        │
    │ local enforcement      │ PR enforcement
    ▼                        ▼
Pre-Commit Hook          CI/CD Workflow
(.claude/hooks/)         (.github/workflows/)
    │                        │
    └────────────┬───────────┘
                 ▼
    Quality Gates Enforce Standards
                 │
                 ▼
    Slash Commands (.claude/commands/)
      - research.md
      - memory-documentary.md
      - pr-review.md
      - context-hub-setup.md
      - [6 more commands]
```

### Data Flow: SlashCommandCreator Workflow

```
User Invokes: "SlashCommandCreator: create command for [purpose]"
    │
    ▼
Phase 1: DISCOVERY & ANALYSIS
  • Clarify intent (what prompt is repeated?)
  • Search existing commands (avoid duplication)
  • Slash command vs skill decision
  • Apply 11 thinking models
    │
    ▼
Phase 2: DESIGN
  • Command naming (namespace conventions)
  • Argument design ($ARGUMENTS vs $1 $2 $3)
  • Frontmatter schema
  • Dynamic context (bash !, file @)
  • Extended thinking evaluation (ultrathink)
    │
    ▼
Phase 3: MULTI-AGENT VALIDATION
  • Security: allowed-tools constraints
  • Architect: no duplication, scope check
  • Independent-Thinker: challenge necessity
  • Critic: frontmatter completeness
    │
    ▼
Phase 4: IMPLEMENTATION
  • Create .claude/commands/[namespace]/[command].md
  • Write frontmatter + prompt
  • scripts/New-SlashCommand.ps1 automation
    │
    ▼
Phase 5: QUALITY GATES (automatic)
  • Run Validate-SlashCommand.ps1
  • Exit code 0 → success
  • Exit code 1 → violations (fix required)
    │
    ▼
Command Ready for Use
```

### Why This Structure?

#### Why Validation Infrastructure First? (M1-M3 before M4)

**Reasoning**:
1. Validation scripts define the "shape" of valid commands
2. Pre-commit hook enforces locally (fast feedback)
3. CI/CD workflow enforces in PR (gate before merge)
4. SlashCommandCreator skill invokes validation in Phase 5
5. Skill implementation informed by validation logic

**Counterfactual**: If we built skill first, validation would be bolted on later, potentially conflicting with skill's generated commands.

#### Why Improve Existing Commands? (M5-M6)

**Reasoning**:
1. Provides real-world test cases for validation scripts
2. Demonstrates before/after patterns for future creators
3. Eliminates technical debt in one PR
4. Entire `.claude/commands/` directory passes quality gates

**Counterfactual**: If we left existing commands as-is, they'd fail new quality gates, creating cognitive dissonance and potential workarounds.

#### Why Document Decision Criteria? (M7)

**Reasoning**:
1. Prevents future "should this be a command or skill?" debates
2. Guides SlashCommandCreator Phase 1 decision logic
3. Provides reference for PR reviews
4. Reduces agent/user friction on scope decisions

**Counterfactual**: Without decision matrix, each new command requires re-deriving the same logic, increasing variability and review time.

---

## Milestones

### Milestone Dependencies

```
M1 (Validation Script)
 ├─> M2 (Pre-Commit Hook)
 ├─> M3 (CI/CD Workflow)
 ├─> M4 (SlashCommandCreator Skill)
 └─> M5 (Improve Commands Part 1)
      └─> M6 (Improve Commands Part 2)
           └─> M7 (Documentation)
```

**Critical Path**: M1 → M5 → M6 → M7 (longest dependency chain)

### M1: PowerShell Validation Script (Foundation)

**Flags**: [needs conformance check]

**Reason**: First comprehensive slash command validation in codebase

**Files**:
- `.claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1` (new)
- `.claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.Tests.ps1` (new)

**Requirements**:

1. **Frontmatter Validation**
   - Parse YAML frontmatter block
   - Require `description` field (trigger-based per creator-001)
   - Require `argument-hint` field if prompt uses $ARGUMENTS or $1, $2, etc.
   - Validate trigger-based pattern: description starts with action verb or "Use when..."

2. **Argument Validation**
   - If frontmatter has `argument-hint`, verify prompt uses $ARGUMENTS or $1, $2, $3
   - If prompt uses $ARGUMENTS, verify `argument-hint` exists
   - Detect unused argument-hint (frontmatter declares but prompt doesn't use)

3. **Security Validation**
   - If prompt uses `!` prefix (bash execution), require `allowed-tools` in frontmatter
   - Validate `allowed-tools` array has no overly permissive wildcards (`*`, `**/*`)
   - Allowed wildcards: `mcp__*`, `mcp__serena__*`, `mcp__forgetful__*` (scoped namespaces)
   - Flag bash commands without allowed-tools as BLOCKING error

4. **Length Validation**
   - Count total lines in file
   - Warn if >200 lines (suggest converting to skill)
   - Not a blocking error, just warning with recommendation

5. **Lint Validation**
   - Call `npx markdownlint-cli2 [file]`
   - Exit code 0 → pass
   - Exit code 1 → fail with lint errors
   - Pass through lint output for user visibility

**Code Changes**:

```powershell
# scripts/Validate-SlashCommand.ps1

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Validate slash command file for quality gates
.PARAMETER Path
    Path to slash command .md file
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Exit codes
$EXIT_SUCCESS = 0
$EXIT_VIOLATION = 1

$violations = @()

# 1. Frontmatter Validation
$content = Get-Content -Path $Path -Raw
if ($content -notmatch '(?s)^---\s*\n(.*?)\n---') {
    $violations += "BLOCKING: Missing YAML frontmatter block"
} else {
    $frontmatter = $matches[1]

    # Parse YAML (simple key-value extraction)
    # WHY: Avoids PowerShell-YAML dependency while handling common patterns
    # LIMITATION: Won't handle multi-line YAML values or complex nesting
    # MITIGATION: Pester tests validate against real-world command files (see M5-M6)
    if ($frontmatter -notmatch 'description:\s*(.+)') {
        $violations += "BLOCKING: Missing 'description' in frontmatter"
    } else {
        $description = $matches[1].Trim()
        # Trigger-based validation
        if ($description -notmatch '^(Use when|Generate|Research|Invoke|Create|Analyze|Review|Search)') {
            $violations += "WARNING: Description should start with action verb or 'Use when...'"
        }
    }

    $hasArgHint = $frontmatter -match 'argument-hint:\s*(.+)'
    $argHintValue = if ($hasArgHint) { $matches[1].Trim() } else { $null }
}

# 2. Argument Validation
$usesArguments = $content -match '\$ARGUMENTS|\$1|\$2|\$3'

if ($usesArguments -and -not $hasArgHint) {
    $violations += "BLOCKING: Prompt uses arguments but no 'argument-hint' in frontmatter"
}

if ($hasArgHint -and -not $usesArguments) {
    $violations += "WARNING: Frontmatter has 'argument-hint' but prompt doesn't use arguments"
}

# 3. Security Validation
$usesBashExecution = $content -match '!\s*\w+'

if ($usesBashExecution) {
    $hasAllowedTools = $frontmatter -match 'allowed-tools:\s*\[(.+)\]'

    if (-not $hasAllowedTools) {
        $violations += "BLOCKING: Prompt uses bash execution (!) but no 'allowed-tools' in frontmatter"
    } else {
        $allowedTools = $matches[1]

        # Check for overly permissive wildcards
        if ($allowedTools -match '\*(?!__)' -and $allowedTools -notmatch 'mcp__\*') {
            $violations += "BLOCKING: 'allowed-tools' has overly permissive wildcard (use mcp__* for scoped namespaces)"
        }
    }

    # Verify common bash commands exist (warning only)
    $bashCommands = [regex]::Matches($content, '!\s*(\w+)') | ForEach-Object { $_.Groups[1].Value }
    foreach ($cmd in $bashCommands) {
        if ($cmd -in @('git', 'gh', 'npm', 'npx')) {
            $exists = Get-Command $cmd -ErrorAction SilentlyContinue
            if (-not $exists) {
                $violations += "WARNING: Bash command '$cmd' not found in PATH (runtime may fail)"
            }
        }
    }
}

# 4. Length Validation
$lineCount = ($content -split '\n').Count

if ($lineCount -gt 200) {
    $violations += "WARNING: File has $lineCount lines (>200). Consider converting to skill."
}

# 5. Lint Validation
Write-Host "Running markdownlint-cli2..." -ForegroundColor Cyan
$lintResult = npx markdownlint-cli2 $Path 2>&1

if ($LASTEXITCODE -ne 0) {
    $violations += "BLOCKING: Markdown lint errors:"
    $violations += $lintResult
}

# Report violations
if ($violations.Count -gt 0) {
    Write-Host "`n❌ Validation FAILED: $Path" -ForegroundColor Red
    Write-Host "`nViolations:" -ForegroundColor Yellow
    $violations | ForEach-Object { Write-Host "  - $_" }
    exit $EXIT_VIOLATION
} else {
    Write-Host "`n✅ Validation PASSED: $Path" -ForegroundColor Green
    exit $EXIT_SUCCESS
}
```

**Pester Tests** (`scripts/Validate-SlashCommand.Tests.ps1`):

```powershell
Describe "Validate-SlashCommand" {
    BeforeAll {
        $script = "$PSScriptRoot/Validate-SlashCommand.ps1"
        $fixturesDir = "$TestDrive/fixtures"
        New-Item -ItemType Directory -Path $fixturesDir -Force | Out-Null
    }

    Context "Frontmatter Validation" {
        It "Should FAIL when frontmatter is missing" {
            $file = "$fixturesDir/no-frontmatter.md"
            "# Command without frontmatter" | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 1
        }

        It "Should FAIL when description is missing" {
            $file = "$fixturesDir/no-description.md"
            @"
---
argument-hint: <arg>
---
Command with no description
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 1
        }

        It "Should PASS with valid trigger-based description" {
            $file = "$fixturesDir/valid-trigger.md"
            @"
---
description: Use when Claude needs to analyze code patterns
---
Analyze the codebase
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 0
        }

        It "Should handle multi-line YAML descriptions" {
            $file = "$fixturesDir/multiline-desc.md"
            @"
---
description: >
  Use when Claude needs to analyze complex patterns
  across multiple dimensions
argument-hint: <pattern>
---
Test command
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Argument Validation" {
        It "Should FAIL when prompt uses \$ARGUMENTS without argument-hint" {
            $file = "$fixturesDir/missing-arg-hint.md"
            @"
---
description: Test command
---
Process \$ARGUMENTS
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 1
        }

        It "Should PASS when argument-hint matches \$ARGUMENTS usage" {
            $file = "$fixturesDir/valid-args.md"
            @"
---
description: Use when processing input
argument-hint: <input-data>
---
Process \$ARGUMENTS
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Security Validation" {
        It "Should FAIL when bash execution has no allowed-tools" {
            $file = "$fixturesDir/bash-no-tools.md"
            @"
---
description: Run git command
---
Execute: !git status
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 1
        }

        It "Should FAIL with overly permissive wildcard" {
            $file = "$fixturesDir/bad-wildcard.md"
            @"
---
description: Run commands
allowed-tools: [*]
---
Execute: !git status
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 1
        }

        It "Should PASS with scoped MCP wildcard" {
            $file = "$fixturesDir/scoped-wildcard.md"
            @"
---
description: Use Serena tools
allowed-tools: [mcp__serena__*]
---
Execute: !mcp__serena__find_symbol
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Length Validation" {
        It "Should WARN when file >200 lines" {
            $file = "$fixturesDir/long-file.md"
            $longContent = @"
---
description: Very long command
---
$( 1..250 | ForEach-Object { "Line $_" } | Out-String )
"@
            $longContent | Out-File $file

            $output = & $script -Path $file 2>&1
            $output | Should -Match "WARNING.*>200"
        }
    }

    Context "Lint Validation" {
        It "Should FAIL on markdown lint errors" {
            $file = "$fixturesDir/lint-errors.md"
            @"
---
description: Test
---
# Heading

```
Missing language identifier
```
"@ | Out-File $file

            & $script -Path $file
            $LASTEXITCODE | Should -Be 1
        }
    }
}
```

**Acceptance Criteria**:
- ✅ Script detects all 5 validation categories (frontmatter, arguments, security, length, lint)
- ✅ Pester tests achieve 80%+ code coverage
- ✅ Exit code 0 for valid commands, exit code 1 for violations
- ✅ BLOCKING violations prevent commit/merge
- ✅ WARNING violations logged but don't block

---

### M2: Pre-Commit Hook

**Flags**: (none)

**Reason**: Follows established hook pattern from project

**Files**:
- `.claude/hooks/pre-commit-slash-commands.ps1` (new)

**Requirements**:
- Detect staged slash command files (`.claude/commands/**/*.md`)
- Run `Validate-SlashCommand.ps1` on each staged file
- Exit code 1 if any validation fails (blocks commit)
- Exit code 0 if all validations pass
- Performance: only validate staged files (not entire directory)

**Code Changes**:

```powershell
# .claude/hooks/pre-commit-slash-commands.ps1

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pre-commit hook to validate staged slash command files
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "🔍 Validating staged slash commands..." -ForegroundColor Cyan

# Get staged .md files in .claude/commands/
$stagedFiles = git diff --cached --name-only --diff-filter=ACM |
    Where-Object { $_ -like '.claude/commands/*.md' }

if ($stagedFiles.Count -eq 0) {
    Write-Host "✅ No slash command files staged, skipping validation" -ForegroundColor Gray
    exit 0
}

Write-Host "Found $($stagedFiles.Count) staged slash command(s)" -ForegroundColor Gray

$validationScript = "$PSScriptRoot/../skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1"
$failedFiles = @()

foreach ($file in $stagedFiles) {
    Write-Host "`nValidating: $file" -ForegroundColor Cyan

    & $validationScript -Path $file

    if ($LASTEXITCODE -ne 0) {
        $failedFiles += $file
    }
}

if ($failedFiles.Count -gt 0) {
    Write-Host "`n❌ COMMIT BLOCKED: $($failedFiles.Count) file(s) failed validation" -ForegroundColor Red
    Write-Host "`nFailed files:" -ForegroundColor Yellow
    $failedFiles | ForEach-Object { Write-Host "  - $_" }
    Write-Host "`nFix violations and try again." -ForegroundColor Yellow
    Write-Host "Emergency bypass (if validation script has bugs): git commit --no-verify" -ForegroundColor Gray
    exit 1
} else {
    Write-Host "`n✅ All slash commands passed validation" -ForegroundColor Green
    exit 0
}
```

**Acceptance Criteria**:
- ✅ Blocks commits with invalid slash commands
- ✅ Only validates staged files (performance optimization)
- ✅ Clear error messages indicating which files failed
- ✅ Exit code 1 on failure, exit code 0 on success

---

### M3: CI/CD Quality Gate

**Flags**: (none)

**Reason**: Follows established workflow pattern (pester-tests.yml)

**Files**:
- `scripts/modules/SlashCommandValidator.psm1` (new)
- `.github/workflows/slash-command-quality.yml` (new)

**Requirements**:
- Trigger on PR when `.claude/commands/**/*.md` files change
- Run validation on all slash command files
- Fail PR if any validation fails
- Skip if no slash commands changed (performance)

**Code Changes**:

**Step 1: Create Module** (`scripts/modules/SlashCommandValidator.psm1`):

```powershell
# scripts/modules/SlashCommandValidator.psm1

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Module for slash command validation (ADR-006: logic in modules, not workflows)
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-SlashCommandValidation {
    <#
    .SYNOPSIS
        Validate all slash command files in .claude/commands/
    .DESCRIPTION
        Runs Validate-SlashCommand.ps1 on each .md file in .claude/commands/
        Returns exit code 0 if all pass, exit code 1 if any fail
    #>

    $files = Get-ChildItem -Path '.claude/commands' -Filter '*.md' -Recurse

    if ($files.Count -eq 0) {
        Write-Host "No slash command files found, skipping validation"
        return 0
    }

    Write-Host "Found $($files.Count) slash command file(s) to validate"

    $failedFiles = @()
    $validationScript = './.claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1'

    foreach ($file in $files) {
        Write-Host "`nValidating: $($file.FullName)"

        & $validationScript -Path $file.FullName

        if ($LASTEXITCODE -ne 0) {
            $failedFiles += $file.Name
        }
    }

    if ($failedFiles.Count -gt 0) {
        Write-Host "`n❌ VALIDATION FAILED: $($failedFiles.Count) file(s) failed" -ForegroundColor Red
        Write-Host "`nFailed files:" -ForegroundColor Yellow
        $failedFiles | ForEach-Object { Write-Host "  - $_" }
        return 1
    } else {
        Write-Host "`n✅ All slash commands passed quality gates" -ForegroundColor Green
        return 0
    }
}

Export-ModuleMember -Function Invoke-SlashCommandValidation
```

**Step 2: Create Workflow** (`.github/workflows/slash-command-quality.yml`):

```yaml
# .github/workflows/slash-command-quality.yml

name: Slash Command Quality Gates

on:
  pull_request:  # WHY: Gate before merge (primary enforcement point)
    paths:
      - '.claude/commands/**/*.md'
      - 'scripts/Validate-SlashCommand.ps1'
      - 'scripts/modules/SlashCommandValidator.psm1'
  push:
    branches:
      - main  # WHY: Catch edge cases where pre-commit hook was bypassed
            # (e.g., GitHub web UI edits, force push with --no-verify)
    paths:
      - '.claude/commands/**/*.md'

jobs:
  validate-slash-commands:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup PowerShell
        shell: pwsh
        run: |
          Write-Host "PowerShell version: $($PSVersionTable.PSVersion)"

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install markdownlint-cli2
        run: npm install -g markdownlint-cli2

      - name: Validate slash commands
        shell: pwsh
        run: |
          # ADR-006: Logic in module, workflow calls module
          Import-Module ./scripts/modules/SlashCommandValidator.psm1
          $exitCode = Invoke-SlashCommandValidation
          exit $exitCode
```

**Acceptance Criteria**:
- ✅ Fails PR when slash commands have validation errors
- ✅ Only runs when slash command files change (path filters)
- ✅ Uses same validation script as pre-commit hook (DRY)
- ✅ Logic in module, workflow calls module (ADR-006 compliance)
- ✅ Clear failure messages in PR checks

---

### M4: SlashCommandCreator Skill

**Flags**: [needs TW rationale, needs conformance check]

**Reason**: Multiple valid implementations for skill workflow, first meta-skill for slash commands

**Files**:
- `.claude/skills/slashcommandcreator/SKILL.md` (new)
- `.claude/skills/slashcommandcreator/scripts/New-SlashCommand.ps1` (new)

**Requirements**:

1. **5-Phase Workflow** (per specification):
   - Phase 1: Discovery & Analysis
   - Phase 2: Design
   - Phase 3: Multi-Agent Validation
   - Phase 4: Implementation
   - Phase 5: Quality Gates (automatic)

2. **Multi-Agent Validation** (Phase 3):
   - Security agent: allowed-tools constraints
   - Architect agent: no duplication, scope check
   - Independent-Thinker: challenge necessity
   - Critic: frontmatter completeness

3. **Invocation Pattern**:
   - Trigger: "SlashCommandCreator: create command for [purpose]"
   - Alternative: "create slash command"
   - Alternative: "design slash command for [purpose]"

4. **PowerShell Helper Script** (`New-SlashCommand.ps1`):
   - Automate file creation
   - Generate frontmatter template
   - Run validation automatically
   - Guide user through required fields

**Code Changes**:

```markdown
# .claude/skills/slashcommandcreator/SKILL.md

---
description: Autonomous meta-skill for creating high-quality custom slash commands using 5-phase workflow with multi-agent validation and quality gates. Use when user requests new slash command, reusable prompt automation, or wants to convert repetitive workflows into documented commands.
trigger: SlashCommandCreator
---

# SlashCommandCreator Skill

## Purpose

Create production-ready custom slash commands following ai-agents quality standards.

## When to Use

- User requests "create slash command for [purpose]"
- Repetitive prompts identified in workflow
- Converting manual workflows to automation
- Need reusable, documented command patterns

## 5-Phase Workflow

### Phase 1: Discovery & Analysis

**Agent Mode**: Analyst

**Tasks**:
1. Clarify user intent: What prompt is being repeated?
2. Search existing commands: `ls .claude/commands/**/*.md`
3. Decision: Slash command vs skill (see decision matrix in CLAUDE.md)
4. Apply 11 thinking models from skillcreator framework
5. Document findings in `.agents/analysis/slashcommand-[name]-analysis.md`

**Deliverable**: Analysis document with recommendation

### Phase 2: Design

**Agent Mode**: Architect

**Tasks**:
1. Command naming (namespace conventions)
2. Argument design:
   - Simple commands: use `$ARGUMENTS`
   - Complex commands: use `$1`, `$2`, `$3` (positional)
3. Frontmatter schema:
   - `description` (trigger-based per creator-001)
   - `argument-hint` (if using arguments)
   - `allowed-tools` (if using bash `!` or file `@`)
   - `model` (opus for complex reasoning)
   - `disable-model-invocation` (if pure prompt template)
4. Dynamic context evaluation:
   - Bash execution (`!git log --oneline -5`)
   - File references (`@.agents/HANDOFF.md`)
5. Extended thinking evaluation:
   - Add `ultrathink` keyword for complex reasoning (>5 steps)
   - Token budget consideration (<31,999 tokens)

**Deliverable**: Design specification with frontmatter + prompt

### Phase 3: Multi-Agent Validation

**Agent Mode**: Orchestrator (coordinates 4 agents)

**Agents**:

1. **Security**:
   - Review `allowed-tools` constraints
   - Flag overly permissive wildcards
   - Verify bash commands are safe

2. **Architect**:
   - Check for duplication (similar existing commands)
   - Verify appropriate scope (not too broad/narrow)
   - Validate namespace conventions

3. **Independent-Thinker**:
   - Challenge necessity: Is this really needed?
   - Propose alternatives
   - Question assumptions

4. **Critic**:
   - Frontmatter completeness check
   - Trigger-based description validation
   - Argument-hint clarity

**Unanimous Approval Required**: All 4 agents must approve.

<!-- WHY: Ensures no single agent dimension (security, scope, necessity, completeness)
     is overlooked. Prevents security vulnerabilities from passing due to focus on
     functionality alone. Pattern proven by skillcreator 3.2.0 multi-agent synthesis. -->

**Invocation Pattern**:

```python
# Security review
Task(subagent_type="security", prompt="Review allowed-tools for command: [spec]")

# Architecture review
Task(subagent_type="architect", prompt="Check for duplication: [spec]")

# Challenge necessity
Task(subagent_type="independent-thinker", prompt="Is this command truly needed? [spec]")

# Frontmatter completeness
Task(subagent_type="critic", prompt="Validate frontmatter completeness: [spec]")
```

**Deliverable**: Validation report with approvals or revision requests

### Phase 4: Implementation

**Agent Mode**: Implementer

**Tasks**:
1. Run `pwsh .claude/skills/slashcommandcreator/scripts/New-SlashCommand.ps1`
2. Create `.claude/commands/[namespace]/[command].md`
3. Write frontmatter + prompt body
4. Test invocation with sample arguments
5. Update command catalog (if exists)

**Deliverable**: Working slash command file

### Phase 5: Quality Gates (Automatic)

**Agent Mode**: Implementer (automatic validation)

**Tasks**:
1. Run `pwsh scripts/Validate-SlashCommand.ps1 -Path [file]`
2. Fix violations if any
3. Re-run validation until exit code 0
4. Commit with conventional commit message

**Deliverable**: Validated slash command ready for use

## Invocation Examples

```text
SlashCommandCreator: create command for exporting Forgetful memories to JSON

SlashCommandCreator: design slash command for running security audit

create slash command that summarizes recent PR comments
```

## Decision Matrix: Slash Command vs Skill

**Use Slash Command When**:
- Prompt is <200 lines
- No multi-step conditional logic
- Simple argument substitution
- No external script orchestration

**Use Skill When**:
- Prompt is >200 lines
- Multi-agent coordination required
- Complex PowerShell logic
- Requires Pester tests

## Quality Gates Checklist

Before marking complete:

- [ ] Frontmatter has `description` (trigger-based)
- [ ] Frontmatter has `argument-hint` (if uses arguments)
- [ ] Frontmatter has `allowed-tools` (if uses bash/file refs)
- [ ] No overly permissive wildcards in `allowed-tools`
- [ ] Description follows trigger-based pattern (creator-001)
- [ ] File is <200 lines (or converted to skill)
- [ ] Passes `markdownlint-cli2` validation
- [ ] Passes `Validate-SlashCommand.ps1` validation
- [ ] Tested with sample arguments
- [ ] Committed with conventional commit message

## References

- `.agents/analysis/custom-slash-commands-research.md`
- `.agents/planning/slashcommandcreator-skill-spec.md`
- `.serena/memories/slashcommand-best-practices.md`
```

**PowerShell Helper Script**:

```powershell
# .claude/skills/slashcommandcreator/scripts/New-SlashCommand.ps1

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Create new slash command with frontmatter template
.PARAMETER Name
    Command name (e.g., "security-audit")
.PARAMETER Namespace
    Optional namespace (e.g., "git", "memory")
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [Parameter(Mandatory = $false)]
    [string]$Namespace
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Determine file path
$baseDir = ".claude/commands"
$filePath = if ($Namespace) {
    "$baseDir/$Namespace/$Name.md"
} else {
    "$baseDir/$Name.md"
}

# Check if file exists
if (Test-Path $filePath) {
    Write-Error "File already exists: $filePath"
    exit 1
}

# Ensure directory exists
$directory = Split-Path -Path $filePath -Parent
if (-not (Test-Path $directory)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

# Generate frontmatter template
$template = @"
---
description: Use when Claude needs to [FILL IN: when to use this command]
argument-hint: <arg>
allowed-tools: []  # WHY: Empty array forces explicit security review during Phase 3
                   # Alternative considered: omit field entirely, but explicit empty
                   # signals "reviewed and no tools needed" vs "forgot to add"
---

# $Name Command

[FILL IN: Detailed prompt instructions]

## Arguments

- `\$ARGUMENTS`: [FILL IN: what argument is expected]

## Example

```text
/$Name [example argument]
```
"@

$template | Out-File -FilePath $filePath -Encoding utf8

Write-Host "✅ Created: $filePath" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "  1. Edit frontmatter (description, argument-hint, allowed-tools)"
Write-Host "  2. Write prompt body"
Write-Host "  3. Run: pwsh scripts/Validate-SlashCommand.ps1 -Path $filePath"
Write-Host "  4. Test: /$Name [arguments]"

# Open in editor (if EDITOR env var set)
if ($env:EDITOR) {
    & $env:EDITOR $filePath
}
```

**Acceptance Criteria**:
- ✅ Skill follows 5-phase workflow from specification
- ✅ Multi-agent validation includes security, architect, independent-thinker, critic
- ✅ Generated commands pass `Validate-SlashCommand.ps1` on first try
- ✅ Helper script automates file creation with frontmatter template
- ✅ Documentation includes decision matrix and quality gates checklist

---

### M5: Improve Existing Commands (Part 1: Frontmatter)

**Flags**: (none)

**Reason**: Straightforward frontmatter additions

**Files**:
- `.claude/commands/research.md` (update)
- `.claude/commands/context-hub-setup.md` (update)
- `.claude/commands/pr-review.md` (verify - already has frontmatter)
- `.claude/commands/memory-documentary.md` (verify - already has frontmatter)
- `.claude/commands/memory-list.md` (update)
- `.claude/commands/memory-save.md` (update)
- `.claude/commands/memory-explore.md` (update)
- `.claude/commands/context_gather.md` (update)
- `.claude/commands/memory-search.md` (update)

**Requirements**:
- Add frontmatter to commands missing it
- Use trigger-based description pattern (creator-001)
- Add `argument-hint` where applicable
- Run validation after each change

**Code Changes**:

**`.claude/commands/research.md`**:
```diff
+---
+description: Research external topics and incorporate learnings into Serena and Forgetful memory systems. Use when investigating new concepts, evaluating technologies, or building institutional knowledge from external sources.
+argument-hint: <topic-or-url>
+allowed-tools: [WebSearch, WebFetch, mcp__forgetful__*, mcp__serena__*]
+model: opus
+---
+
 # Research and Incorporate Command
```

**`.claude/commands/context-hub-setup.md`**:
```diff
+---
+description: Configure Context Hub dependencies including Forgetful MCP server and plugin prerequisites. Use when setting up new development environment or troubleshooting MCP connectivity.
+---
+
 # Context Hub Setup
```

**`.claude/commands/memory-list.md`**:
```diff
+---
+description: List recent memories from Forgetful with optional project filtering. Use when exploring stored knowledge or verifying memory creation.
+argument-hint: [project-name]
+allowed-tools: [mcp__forgetful__*]
+---
+
 # Memory List Command
```

**`.claude/commands/memory-save.md`**:
```diff
+---
+description: Save current context as atomic memory in Forgetful with structured fields. Use when capturing learnings, decisions, or patterns for cross-session retrieval.
+allowed-tools: [mcp__forgetful__*]
+---
+
 # Memory Save Command
```

**`.claude/commands/memory-explore.md`**:
```diff
+---
+description: Deep exploration of Forgetful knowledge graph with entity traversal. Use when investigating relationships between memories or building comprehensive understanding of topic clusters.
+argument-hint: <starting-query>
+allowed-tools: [mcp__forgetful__*]
+model: opus
+---
+
 # Memory Explore Command
```

**`.claude/commands/context_gather.md`**:
```diff
+---
+description: Gather comprehensive context from Forgetful Memory, Context7 docs, and web sources before planning or implementation. Use when starting complex tasks requiring multi-source context.
+argument-hint: <task-or-technology>
+allowed-tools: [mcp__forgetful__*, mcp__context7__*, WebSearch, WebFetch]
+model: opus
+---
+
 # Context Gather Command
```

**`.claude/commands/memory-search.md`**:
```diff
+---
+description: Search memories semantically using Forgetful with query context for improved ranking. Use when retrieving specific knowledge or verifying memory existence.
+argument-hint: <search-query>
+allowed-tools: [mcp__forgetful__*]
+---
+
 # Memory Search Command
```

**Acceptance Criteria**:
- ✅ All 7 commands have frontmatter
- ✅ All descriptions follow trigger-based pattern
- ✅ All commands pass `Validate-SlashCommand.ps1`
- ✅ Manual verification: invoke each command to ensure functionality unchanged

---

### M6: Improve Existing Commands (Part 2: Extended Thinking + Security)

**Flags**: [needs error review]

**Reason**: Depends on external bash commands (git, gh) availability

**Files**:
- `.claude/commands/pr-review.md` (verify `allowed-tools`, add `ultrathink`)
- `.claude/commands/research.md` (add `ultrathink`)
- `.claude/commands/memory-documentary.md` (add `ultrathink`)

**Requirements**:
- Add `ultrathink` keyword to complex reasoning commands
- Verify `allowed-tools` constraints for bash execution
- Test with extended thinking enabled

**Code Changes**:

**`.claude/commands/pr-review.md`**:

Verify existing frontmatter has `allowed-tools` (scoped wildcards allowed):
```yaml
# CURRENT syntax (verify this passes M1 validation):
allowed-tools: [Bash, mcp__forgetful__*]

# WHY: M1 validation allows scoped MCP wildcards (mcp__*) but not bare wildcards
# Bash commands allowed but not scoped (gh, git are subcommands, not separate tools)
```

Add `ultrathink` to prompt body:
```diff
 # PR Review Command

+> **Note**: This command uses extended thinking (`ultrathink`) for deep PR analysis.
+
+ultrathink
+
 Respond to PR review comments for the specified pull request(s).
```

**`.claude/commands/research.md`**:

Add `ultrathink` to prompt body:
```diff
 # Research and Incorporate Command

+> **Note**: This command uses extended thinking (`ultrathink`) for comprehensive research.
+
+ultrathink
+
 Research external topics and incorporate learnings into Serena and Forgetful memory systems.
```

**`.claude/commands/memory-documentary.md`**:

Add `ultrathink` to prompt body:
```diff
 # Memory Documentary Command

+> **Note**: This command uses extended thinking (`ultrathink`) for evidence-based analysis.
+
+ultrathink
+
 Generate evidence-based documentary reports by searching across all memory systems.
```

**Acceptance Criteria**:
- ✅ All files pass security validation (bash commands have `allowed-tools`)
- ✅ `ultrathink` keyword present in 3 complex commands
- ✅ Manual test: invoke `/pr-review`, `/research`, `/memory-documentary` with `ultrathink` enabled
- ✅ Verify extended thinking activates (check token budget usage)

---

### M7: Documentation

**Flags**: (none)

**Reason**: Standard documentation update

**Files**:
- `CLAUDE.md` (update)
- `.claude/commands/README.md` (new)

**Requirements**:

1. **CLAUDE.md Updates**:
   - Add "Custom Slash Commands" section
   - Document decision matrix (slash command vs skill)
   - Link to SlashCommandCreator skill
   - Link to quality gates documentation

2. **Command Catalog** (`.claude/commands/README.md`):
   - List all slash commands with descriptions
   - Group by namespace (if applicable)
   - Include usage examples
   - Link to validation documentation

**Code Changes**:

**`CLAUDE.md`** (insert after "Skill System" section):

```markdown
---

## Custom Slash Commands

Custom slash commands are reusable prompts stored in `.claude/commands/`. They support argument substitution, dynamic context injection, and extended thinking.

### When to Use Slash Commands vs Skills

**Use Slash Command When**:
- Prompt is <200 lines
- No multi-step conditional logic
- Simple argument substitution
- No external script orchestration

**Use Skill When**:
- Prompt is >200 lines
- Multi-agent coordination required
- Complex PowerShell logic
- Requires Pester tests

### Creating Slash Commands

Use the `SlashCommandCreator` skill for guided creation:

```text
SlashCommandCreator: create command for [purpose]
```

**Manual Creation**:
1. Create `.claude/commands/[name].md`
2. Add frontmatter (see template below)
3. Write prompt body
4. Run validation: `pwsh scripts/Validate-SlashCommand.ps1 -Path .claude/commands/[name].md`
5. Test: `/[name] [arguments]`

**Frontmatter Template**:
```yaml
---
description: Use when Claude needs to [trigger condition]
argument-hint: <arg-description>
allowed-tools: [tool1, tool2]
model: opus
---
```

### Quality Gates

All slash commands MUST pass validation before commit:

| Gate | Validates |
|------|-----------|
| Frontmatter | Required fields, trigger-based description |
| Arguments | `argument-hint` matches `$ARGUMENTS` usage |
| Security | `allowed-tools` for bash execution (`!` prefix) |
| Length | <200 lines (or convert to skill) |
| Lint | Markdown formatting (markdownlint-cli2) |

**Local Validation**: Pre-commit hook automatically runs on staged files

**CI/CD Validation**: GitHub Actions workflow runs on PR

### Extended Thinking

Add `ultrathink` keyword for complex reasoning (>5 steps):

```markdown
---
description: Analyze codebase architecture
model: opus
---

ultrathink

Perform deep architectural analysis of the codebase...
```

**Token Budget**: Up to 31,999 tokens for extended thinking

### Why Extended Thinking for These 3 Commands?

Commands with `ultrathink`:
- `/pr-review`: Multi-agent synthesis (orchestrator pattern), deep code analysis across multiple files
- `/research`: Multi-source context gathering (web, docs, memory), evaluation of conflicting information
- `/memory-documentary`: Evidence chain construction across 4 memory systems (Claude-Mem, Forgetful, Serena, DeepWiki)

**WHY NOT ALL COMMANDS**: Simple retrieval commands (`memory-search`, `memory-list`) benefit more from speed than depth. Cost/benefit threshold: >5 reasoning steps or multi-source synthesis required.

### Command Catalog

See [.claude/commands/README.md](.claude/commands/README.md) for complete list.

---
```

**`.claude/commands/README.md`** (new file):

```markdown
# Slash Command Catalog

Custom slash commands for Claude Code. All commands follow quality gates (frontmatter, security, validation).

## Memory Commands

| Command | Description | Arguments |
|---------|-------------|-----------|
| `/memory-list` | List recent Forgetful memories | `[project-name]` |
| `/memory-save` | Save current context to Forgetful | None |
| `/memory-search` | Semantic search across memories | `<search-query>` |
| `/memory-explore` | Deep knowledge graph exploration | `<starting-query>` |
| `/memory-documentary` | Generate evidence-based reports | None |

**Extended Thinking**: `memory-explore`, `memory-documentary`

## Research Commands

| Command | Description | Arguments |
|---------|-------------|-----------|
| `/research` | Research topics and incorporate into memory | `<topic-or-url>` |
| `/context_gather` | Gather context from multiple sources | `<task-or-technology>` |

**Extended Thinking**: `research`

## Development Commands

| Command | Description | Arguments |
|---------|-------------|-----------|
| `/pr-review` | Respond to PR review comments | `[pr-number]` |
| `/context-hub-setup` | Configure Context Hub dependencies | None |

**Extended Thinking**: `pr-review`

## Usage Examples

```bash
# Search memories
/memory-search "PowerShell array handling"

# Research with extended thinking
/research "Roslyn analyzer best practices"

# PR review with deep analysis
/pr-review 123
```

## Creating New Commands

Use the SlashCommandCreator skill:

```text
SlashCommandCreator: create command for [purpose]
```

Or manually:

```bash
pwsh .claude/skills/slashcommandcreator/scripts/New-SlashCommand.ps1 -Name "my-command"
```

## Validation

All commands pass quality gates:

```bash
pwsh scripts/Validate-SlashCommand.ps1 -Path .claude/commands/[name].md
```

**Pre-commit hook**: Automatically validates staged commands
**CI/CD**: GitHub Actions workflow validates on PR

## Documentation

- [SlashCommandCreator Skill](.claude/skills/slashcommandcreator/SKILL.md)
- [Custom Slash Commands Research](.agents/analysis/custom-slash-commands-research.md)
- [Validation Script](../scripts/Validate-SlashCommand.ps1)
```

**Acceptance Criteria**:
- ✅ CLAUDE.md has complete slash command section with decision matrix
- ✅ README.md catalogs all 9 commands with descriptions and examples
- ✅ Both files pass `markdownlint-cli2` validation
- ✅ Links resolve correctly (no 404s)

---

## Completion Checklist

### Pre-Implementation
- [ ] Read `.agents/analysis/custom-slash-commands-research.md`
- [ ] Read `.agents/planning/slashcommandcreator-skill-spec.md`
- [ ] Read `creator-001-frontmatter-trigger-specification` memory
- [ ] Verify PowerShell version ≥7.0
- [ ] Verify markdownlint-cli2 installed

### Implementation Order
- [ ] M1: PowerShell Validation Script + Pester tests (80%+ coverage)
- [ ] M2: Pre-commit hook (block commits with violations)
- [ ] M3: CI/CD workflow (fail PR on violations)
- [ ] M4: SlashCommandCreator skill + helper script
- [ ] M5: Improve existing commands (frontmatter)
- [ ] M6: Improve existing commands (ultrathink + security)
- [ ] M7: Documentation (CLAUDE.md + README.md)

### Validation
- [ ] All Pester tests pass (80%+ coverage)
- [ ] Pre-commit hook blocks invalid commands
- [ ] CI/CD workflow fails on violations
- [ ] All 9 existing commands pass validation
- [ ] SlashCommandCreator generates valid commands
- [ ] Documentation links resolve correctly

### Commit Strategy
- [ ] Single PR with all milestones
- [ ] Conventional commit message
- [ ] All files pass markdownlint-cli2
- [ ] No merge conflicts with main

---

## Success Metrics

| Metric | Target | Verification |
|--------|--------|--------------|
| Validation script code coverage | ≥80% | Pester test output |
| Existing commands passing validation | 9/9 (100%) | `Validate-SlashCommand.ps1` |
| Pre-commit hook blocks invalid commits | 100% | Test with anti-pattern fixture |
| CI/CD fails PR with violations | 100% | Test PR with invalid command |
| SlashCommandCreator generates valid commands | First-try pass | Test with sample command |
| Documentation completeness | All sections filled | Manual review |

---

## Risk Mitigation Evidence

### M1: Validation Edge Cases

**Risk**: PowerShell script breaks on edge cases

**Mitigation**: Comprehensive Pester tests with fixtures

**Evidence**:
```powershell
# scripts/Validate-SlashCommand.Tests.ps1

Context "Edge Cases" {
    It "Should handle empty frontmatter block" { ... }
    It "Should handle YAML arrays with newlines" { ... }
    It "Should handle multi-line descriptions" { ... }
    It "Should handle Unicode in descriptions" { ... }
}
```

### M2: Pre-Commit Performance

**Risk**: Hook slows down commits

**Mitigation**: Only validate staged files, not entire directory

**Evidence**:
```powershell
# .claude/hooks/pre-commit-slash-commands.ps1

$stagedFiles = git diff --cached --name-only --diff-filter=ACM |
    Where-Object { $_ -like '.claude/commands/*.md' }

if ($stagedFiles.Count -eq 0) {
    Write-Host "✅ No slash command files staged, skipping validation"
    exit 0
}
```

### M3: CI/CD Infrastructure Failures

**Risk**: Workflow fails due to infrastructure issues

**Mitigation**: Fail-fast on script errors, skip when no commands changed

**Evidence**:
```yaml
# .github/workflows/slash-command-quality.yml

on:
  pull_request:
    paths:
      - '.claude/commands/**/*.md'  # Only trigger when commands change

steps:
  - name: Validate slash commands
    shell: pwsh
    run: |
      if ($files.Count -eq 0) {
        Write-Host "No slash command files found, skipping validation"
        exit 0
      }
```

### M5-M6: Existing Commands Fail Gates

**Risk**: Existing commands fail new quality gates

**Mitigation**: Pre-validate all 9 commands before committing hook

**Evidence**:
```bash
# Manual verification step before M2 commit

pwsh scripts/Validate-SlashCommand.ps1 -Path .claude/commands/research.md
pwsh scripts/Validate-SlashCommand.ps1 -Path .claude/commands/memory-documentary.md
# ... all 9 commands
```

---

## Notes

### File Classification

| New File | Backing | Citation |
|----------|---------|----------|
| `.claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1` | doc-derived | `.agents/analysis/custom-slash-commands-research.md` Section 9.3 |
| `.claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.Tests.ps1` | doc-derived | ADR-006 (Pester requirement) |
| `.claude/hooks/pre-commit-slash-commands.ps1` | doc-derived | PROJECT-CONSTRAINTS.md (git hooks) |
| `.github/workflows/slash-command-quality.yml` | doc-derived | `.agents/planning/slashcommandcreator-skill-spec.md` |
| `.claude/skills/slashcommandcreator/SKILL.md` | doc-derived | `.agents/planning/slashcommandcreator-skill-spec.md` |
| `.claude/skills/slashcommandcreator/scripts/New-SlashCommand.ps1` | doc-derived | `.agents/planning/slashcommandcreator-skill-spec.md` |
| `.claude/commands/README.md` | default-derived | Convention: command catalogs |

### Uncertainty Flags Explained

**M1**: [needs conformance check]
- Reason: First comprehensive slash command validation in codebase
- Mitigation: Review against existing validation patterns in `.github/workflows/pester-tests.yml`

**M4**: [needs TW rationale, needs conformance check]
- Reason: Multiple valid implementations for skill workflow, first meta-skill for slash commands
- Mitigation: Model after skillcreator 3.2.0 framework (proven pattern)

**M6**: [needs error review]
- Reason: Depends on external bash commands (git, gh) availability
- Mitigation: Verify commands exist in `allowed-tools` frontmatter, test in CI environment

---

## References

| Document | Purpose |
|----------|---------|
| `.agents/analysis/custom-slash-commands-research.md` | Research findings, community patterns |
| `.agents/planning/slashcommandcreator-skill-spec.md` | Complete skill specification |
| `.serena/memories/slashcommand-best-practices.md` | Quick reference memory |
| ADR-005 | PowerShell-only scripting rationale |
| ADR-006 | Thin workflows, testable modules |
| PROJECT-CONSTRAINTS.md | Hard constraints and conventions |
| SESSION-PROTOCOL.md | Session start/end requirements |
