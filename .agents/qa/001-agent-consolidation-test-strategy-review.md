# QA Review: 2-Variant Agent Consolidation Test Strategy

**Reviewer**: QA Agent
**Date**: 2025-12-15
**Documents Reviewed**:
- `.agents/planning/prd-agent-consolidation.md`
- `.agents/planning/tasks-agent-consolidation.md`

---

## Executive Summary

The 2-Variant Agent Consolidation plan has **adequate** test coverage for core functionality but **lacks detailed test specifications** for several critical validation scenarios. The plan relies heavily on "byte-identical" comparisons but does not specify the tooling or test patterns to achieve this.

## Verdict: **Needs Changes**

The plan requires additional test strategy details before implementation can proceed confidently.

---

## Review Findings

### 1. Test Strategy Assessment

#### What is Covered

| Area | Coverage | Notes |
|------|----------|-------|
| PoC Validation (TASK-012) | Explicit | 3 agents validated for byte-identical output |
| CI Validation (TASK-014) | Explicit | PR fails if generated files differ |
| Build Script Output | Implicit | Outputs verified via diff |
| Quality Gates | Explicit | 4 gates defined in task breakdown |

#### What is Missing

| Gap | Priority | Concern |
|-----|----------|---------|
| Pester test specification for build script | High | No `Generate-Agents.Tests.ps1` test cases defined |
| Byte-identical comparison methodology | High | How to handle line endings, encoding, whitespace? |
| Regression test suite for agents | Medium | After migration, how do we verify agents still work? |
| Frontmatter transformation unit tests | High | TASK-006 mentions tests but no test cases specified |
| Drift detection accuracy testing | Medium | How to verify false positives/negatives? |
| Performance benchmarks | Low | 5-second target mentioned but no test method |

---

### 2. PoC Validation Analysis (TASK-012)

**Current Specification:**
> - Diff comparison for all 3 VS Code outputs shows no differences
> - Diff comparison for all 3 Copilot CLI outputs shows no differences
> - Build script runs without errors
> - Build script completes in under 2 seconds for 3 agents

**Issues Identified:**

1. **No specified diff tool**: PowerShell `Compare-Object` vs `git diff` vs `fc.exe` have different behaviors
2. **Encoding sensitivity**: UTF-8 BOM vs no BOM can cause false failures
3. **Line ending normalization**: CRLF vs LF differences must be handled
4. **No test for partial generation**: What happens if only 2 of 3 succeed?

**Recommended Test Cases:**

```powershell
Describe "Generate-Agents.ps1 Proof of Concept" {
    Context "Analyst Agent Generation" {
        It "Generates VS Code output byte-identical to existing file" {
            # Arrange
            $expected = Get-Content "src/vs-code-agents/analyst.agent.md" -Raw

            # Act
            & build/Generate-Agents.ps1 -Agent "analyst" -WhatIf:$false
            $actual = Get-Content "src/vs-code-agents/analyst.agent.md" -Raw

            # Assert
            $actual | Should -BeExactly $expected
        }

        It "Generates Copilot CLI output byte-identical to existing file" {
            $expected = Get-Content "src/copilot-cli/analyst.agent.md" -Raw
            & build/Generate-Agents.ps1 -Agent "analyst"
            $actual = Get-Content "src/copilot-cli/analyst.agent.md" -Raw
            $actual | Should -BeExactly $expected
        }
    }
}
```

---

### 3. Byte-Identical Output Verification

**Current State:**
The PRD states generated files must be "byte-identical to current manually-maintained files during migration" (NFR-3) but does not specify:

1. How to capture baseline files before migration
2. How to handle intentional formatting improvements during consolidation
3. What constitutes acceptable vs unacceptable differences

**Recommended Approach:**

```text
Baseline Capture Strategy:
1. Create baseline directory: baseline/vs-code-agents/ and baseline/copilot-cli/
2. Copy all current agent files to baseline before any changes
3. Use git hash comparison for exact byte matching:
   Get-FileHash -Algorithm SHA256
4. Store baseline hashes in a manifest file for CI validation
```

**Suggested Manifest Format:**

```yaml
# baseline-hashes.yaml
version: 1.0
generated: 2025-12-15
files:
  - path: src/vs-code-agents/analyst.agent.md
    sha256: abc123...
  - path: src/copilot-cli/analyst.agent.md
    sha256: def456...
```

---

### 4. Regression Testing for Agent Functionality

**Gap:** The plan validates that generated files are identical but does not validate that agents **function correctly** after migration.

**Risk:** A subtle error in template processing could produce identical-looking files that fail at runtime.

**Recommended Tests:**

| Test Type | Purpose | Implementation |
|-----------|---------|----------------|
| YAML Frontmatter Validation | Verify all required fields present | Parse with `ConvertFrom-Yaml` |
| Tool Array Validation | Verify tools are valid identifiers | Regex validation |
| Section Presence | Verify all required sections exist | Markdown header parsing |
| Handoff Syntax Check | Verify handoff patterns are valid | Regex match per platform |

**Example Pester Test:**

```powershell
Describe "Generated Agent Validation" {
    $agents = Get-ChildItem "src/vs-code-agents/*.agent.md"

    It "All agents have valid YAML frontmatter" -ForEach $agents {
        $content = Get-Content $_.FullName -Raw
        $frontmatter = $content | Select-String -Pattern "(?s)^---(.+?)---" |
            ForEach-Object { $_.Matches.Groups[1].Value }

        { $frontmatter | ConvertFrom-Yaml } | Should -Not -Throw
    }

    It "All agents have required sections" -ForEach $agents {
        $content = Get-Content $_.FullName -Raw

        $content | Should -Match "## Core Identity"
        $content | Should -Match "## Core Mission"
        $content | Should -Match "## Key Responsibilities"
    }
}
```

---

### 5. Coverage Requirements

**Current State:** No explicit coverage targets defined in the PRD or task breakdown.

**Recommended Coverage Targets:**

| Component | Target | Rationale |
|-----------|--------|-----------|
| `Generate-Agents.ps1` | 80% line coverage | Core build logic |
| `Detect-AgentDrift.ps1` | 70% line coverage | Detection logic |
| Frontmatter transformation | 100% branch coverage | Critical path |
| Platform configuration parsing | 90% line coverage | Configuration validation |

**Measurement Method:**
The existing `Invoke-PesterTests.ps1` does not include code coverage. Recommend adding:

```powershell
$config.CodeCoverage.Enabled = $true
$config.CodeCoverage.Path = @(
    "./build/Generate-Agents.ps1",
    "./build/Detect-AgentDrift.ps1"
)
$config.CodeCoverage.OutputPath = "./artifacts/coverage.xml"
```

---

### 6. Test Data Management

**Gap:** No specification for test fixtures or mock data.

**Recommendations:**

1. **Create test fixtures directory**: `build/tests/fixtures/`
2. **Sample shared sources**: Minimal agent templates for testing
3. **Platform config mocks**: Isolated configuration for testing
4. **Expected outputs**: Pre-validated expected output files

**Structure:**

```text
build/tests/
  fixtures/
    agents/
      minimal.shared.md     # Minimal valid agent
      no-frontmatter.md     # Invalid - missing frontmatter
      invalid-yaml.md       # Invalid - malformed YAML
    platforms/
      test-vscode.yaml      # Test platform config
      test-copilot.yaml     # Test platform config
    expected/
      minimal.vscode.agent.md
      minimal.copilot.agent.md
```

---

### 7. CI Validation Workflow Testing

**TASK-014 Acceptance Criteria Analysis:**

| Criterion | Testable? | Test Method |
|-----------|-----------|-------------|
| Workflow triggers on PR/push | Yes | GitHub Actions workflow syntax check |
| Only runs on agent-related changes | Yes | Path filter validation |
| Regenerates all agent files | Yes | Workflow step verification |
| Fails with clear error message | Yes | Integration test with modified file |
| Error identifies modified files | Yes | Output parsing |

**Recommended Validation:**

Before merging TASK-014, manually test:

1. Create a branch that modifies a generated file directly
2. Open PR, verify CI fails
3. Verify error message lists the modified file(s)
4. Verify PR cannot merge (branch protection)

---

### 8. Drift Detection Testing (Phase 2)

**TASK-018 Gap:** No test cases for verifying drift detection accuracy.

**Recommended Test Scenarios:**

| Scenario | Expected Result | Test Method |
|----------|-----------------|-------------|
| Identical content | No drift detected, exit 0 | Pester test |
| Whitespace-only difference | No drift (normalized) | Pester test |
| Semantic content change | Drift detected, exit 1 | Pester test |
| Known exclusion (frontmatter) | No drift | Pester test |
| Known exclusion (tool syntax) | No drift | Pester test |
| Mixed (exclusion + semantic) | Drift on semantic only | Pester test |

---

## Specific Concerns

### Concern 1: No Test File Created in Task Breakdown

TASK-006 mentions "Unit tests cover transformation edge cases" but does not specify a test file or test cases. This should be explicit:

**Add to TASK-006:**
- `build/tests/Generate-Agents.Tests.ps1`: Create with transformation tests

### Concern 2: QA Task Effort Underestimated

TASK-012 allocates 30 minutes for QA validation. This is insufficient for:
- Setting up baseline comparisons
- Running full diff analysis
- Documenting findings
- Addressing any discrepancies

**Recommend:** 1-2 hours for thorough PoC validation.

### Concern 3: No Rollback Testing

**Question:** If consolidation fails, how do we restore the original files?

**Recommend:** Add task for rollback procedure documentation and testing.

---

## Required Changes Before Approval

### High Priority (Must Address)

1. **Add explicit test file creation** to TASK-006:
   - Create `build/tests/Generate-Agents.Tests.ps1`
   - Define minimum 10 test cases for frontmatter transformation
   - Define minimum 5 test cases for handoff syntax transformation

2. **Specify byte-comparison methodology**:
   - Define normalization rules (line endings, encoding)
   - Specify comparison tool (recommend `Get-FileHash` or `git diff --no-index`)
   - Document acceptable vs unacceptable differences

3. **Increase QA effort for TASK-012**:
   - Increase from 30 minutes to 1.5 hours
   - Add explicit test report deliverable

### Medium Priority (Should Address)

4. **Add regression test specification**:
   - YAML frontmatter validation tests
   - Required section presence tests
   - Handoff syntax validation tests

5. **Add drift detection test cases to TASK-018**:
   - Define positive and negative test scenarios
   - Specify expected outputs for each

### Low Priority (Nice to Have)

6. **Add code coverage targets** to project standards

7. **Create test fixtures directory structure** specification

---

## Recommendations for Implementer

When implementing `Generate-Agents.ps1`:

1. **Write tests first** (TDD approach) for transformation functions
2. **Use `BeforeAll` to backup** existing files before generation
3. **Include verbose logging** for troubleshooting test failures
4. **Add `-DryRun` flag** that outputs to temporary directory for safe testing

---

## Summary

The consolidation plan is well-structured but lacks the test strategy depth needed for a confident implementation. The "byte-identical" requirement is critical and requires explicit tooling and methodology. Adding the recommended changes will significantly reduce the risk of regression during migration.

**Next Steps:**
1. Address high-priority concerns in task breakdown
2. Create test file specifications before implementation begins
3. Return to QA for re-validation after updates

---

**Handoff**: Route to **milestone-planner** to incorporate test strategy feedback into task breakdown.
