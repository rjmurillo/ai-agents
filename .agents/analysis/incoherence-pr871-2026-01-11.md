# Incoherence Report: PR #871 Coding Standards Consolidation

**Analysis Date**: 2026-01-11
**PR**: #871 - Agent coding standards review
**Dimensions Analyzed**: A (Spec vs Behavior), C (Cross-Reference), D (Temporal), H (Policy Compliance), I (Documentation Gaps), K (Implicit Contract)

## Executive Summary

- **Issues Found**: 10 confirmed incoherences
- **Severity Breakdown**:
  - Critical: 2
  - High: 5
  - Medium: 3
  - Low: 0
- **Root Causes**: Incomplete migrations (session format), policy violations (ADR-005, ADR-035), documentation inconsistencies

---

## Issues

### Issue I1: Session Format Migration Incomplete

**Type**: Contradiction + Temporal Staleness
**Severity**: CRITICAL
**Dimension**: D - Temporal Consistency

#### Source A (Authoritative - Current State)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/AGENTS.md`
**Lines**: 56, 78
```markdown
Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.json`
pwsh scripts/Validate-SessionJson.ps1 -SessionPath ".agents/sessions/[session-log].json"
```

#### Source B (Stale References)
**Files**: 299+ files across codebase
**Examples**:
- `/home/richard/src/GitHub/rjmurillo/ai-agents4/CRITICAL-CONTEXT.md:3`
- `/home/richard/src/GitHub/rjmurillo/ai-agents4/src/claude/orchestrator.md:54`
- `/home/richard/src/GitHub/rjmurillo/ai-agents4/.serena/memories/git-hooks-pre-commit-session-gap-796.md`
```markdown
`.agents/sessions/YYYY-MM-DD-session-NN.md`
```

#### Analysis
The codebase is mid-migration from `.md` to `.json` session format. AGENTS.md specifies `.json` as canonical, but 299+ files (agent definitions, memories, workflows, hooks) still reference the old `.md` format. This creates ambiguity about which format is current and can cause validation failures.

#### Suggestions
1. Complete migration: Update all 299 references to `.json` format
2. Create migration guide documenting both formats during transition period
3. Add deprecation warnings in code that detects `.md` format

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Complete the migration in phases.

**Phase 1 (Immediate)**: Global find-replace in documentation files:
- CRITICAL-CONTEXT.md: `.md` → `.json`
- All files in `src/claude/`, `src/copilot-cli/`, `src/vs-code-agents/`: Update session references
- Update `.serena/memories/` files that reference session format

**Phase 2 (Follow-up PR)**: Create migration tracking issue to systematically update remaining 299 files with validation that existing `.md` archives aren't broken.

**Rationale**: Critical issue blocking consistency. Phased approach prevents breaking archived sessions while establishing `.json` as canonical format going forward.

<!-- /Resolution -->

---

### Issue I2: ADR-005 Policy Violations - Undocumented Scripts

**Type**: Policy Violation
**Severity**: HIGH
**Dimension**: H - Policy & Convention Compliance

#### Source A (Policy)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.agents/architecture/ADR-005-powershell-only-scripting.md`
**Lines**: 21-22, 157
```markdown
MUST use PowerShell for all scripting
For all other scripts: PowerShell-only requirement remains in effect
```

#### Source B (Violations)
**Bash Scripts** (2 undocumented):
- `/home/richard/src/GitHub/rjmurillo/ai-agents4/scripts/bootstrap-vm.sh` (89 lines)
- `/home/richard/src/GitHub/rjmurillo/ai-agents4/.github/actions/ai-review/test-infrastructure-failure.sh` (44 lines)

**Python Scripts** (7 outside SkillForge exception):
- `.claude/skills/security-detection/detect_infrastructure.py`
- `.claude/skills/metrics/collect_metrics.py`
- `.claude/skills/planner/scripts/executor.py`
- `.claude/skills/planner/scripts/planner.py`
- `.claude/skills/analyze/scripts/analyze.py`
- `.claude/skills/decision-critic/scripts/decision-critic.py`
- `.claude/skills/fix-markdown-fences/fix_fences.py`

#### Analysis
ADR-005 mandates PowerShell-only with a narrow SkillForge exception (`.claude/skills/SkillForge/` only). Nine scripts violate this policy without documented exceptions or ADR amendments. PROJECT-CONSTRAINTS.md Line 160-162 states "Existing Violations (Grandfathered): None currently documented."

#### Suggestions
1. Create ADR amendment for necessary non-PowerShell scripts with rationale
2. Rewrite scripts in PowerShell to comply with ADR-005
3. Document as grandfathered violations in PROJECT-CONSTRAINTS.md

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Amend ADR-005 to document skill Python exception pattern + rewrite bash scripts.

**Actions**:
1. **Amend ADR-005** (Lines 150-160): Add "Skill Agent Pattern Exception" allowing Python in `.claude/skills/*/scripts/*.py` for agent-specific logic (rationale: some agents require Python-specific libraries like AST parsing, ML models). Document 7 existing Python skills.

2. **Rewrite Bash Scripts**:
   - `scripts/bootstrap-vm.sh` → `scripts/Install-BootstrapVM.ps1` (PowerShell supports all platforms)
   - `.github/actions/ai-review/test-infrastructure-failure.sh` → delegate to PowerShell module

3. **Update PROJECT-CONSTRAINTS.md**: Document grandfathered bash hooks (`.githooks/pre-commit` already has documented exception).

**Rationale**: Skills pattern is established (7 agents already using Python). Bash scripts lack documented justification and can be rewritten. Maintains ADR-005 spirit while recognizing agent ecosystem reality.

<!-- /Resolution -->

---

### Issue I3: Exit Code Semantic Violation

**Type**: Specification vs Behavior
**Severity**: HIGH
**Dimension**: A - Specification vs Behavior

#### Source A (Specification)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.agents/architecture/ADR-035-exit-code-standardization.md`
**Lines**: 121, 137-162
```markdown
exit 1 = Logic Error / Validation failure
100+: Script-specific codes for domain-specific states
```

#### Source B (Implementation)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.claude/skills/github/scripts/pr/Test-PRMerged.ps1`
**Lines**: 26-29, 103
```powershell
# exit 1: PR IS merged (skip review work)
exit 1
```

**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.claude/skills/github/scripts/pr/Get-PRChecks.ps1`
**Lines**: 37-43, 390
```powershell
# exit 1: Check failed
exit 1
```

#### Analysis
ADR-035 defines exit 1 as "Logic Error / Validation failure" but Test-PRMerged.ps1 uses it for success state ("PR IS merged"). ADR-035 specifies 100+ for script-specific domain states. Get-PRChecks.ps1 uses exit 7 (in reserved range 5-99). Both violate the standard without justification.

#### Suggestions
1. Migrate Test-PRMerged.ps1 to use exit 100 for "PR merged" state
2. Migrate Get-PRChecks.ps1 to use exit 101 for "timeout" state
3. Document as pre-standardization implementations with migration plan

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Document as grandfathered pre-ADR-035 with migration plan in Phase 2.

**Immediate** (ADR-035 amendment):
- Add section "Pre-Standardization Scripts" listing Test-PRMerged.ps1 (exit 1 = PR merged) and Get-PRChecks.ps1 (exit 7 = timeout) as grandfathered implementations

**Phase 2 Migration** (create tracking issue):
- Test-PRMerged.ps1: exit 0 (not merged), exit 100 (merged)
- Get-PRChecks.ps1: exit 0 (success), exit 100 (timeout), maintain exit 1-4 for errors

**Rationale**: Scripts predate ADR-035. Breaking change requires caller updates (workflows, other scripts). Document current state, plan migration separately to avoid scope creep in PR #871.

<!-- /Resolution -->

---

### Issue I4: Nonexistent Script Reference

**Type**: Temporal Staleness + Documentation Gap
**Severity**: CRITICAL
**Dimension**: D - Temporal Consistency

#### Source A (Stale References)
**Files**: 12 files reference nonexistent script
**Examples**:
- `/home/richard/src/GitHub/rjmurillo/ai-agents4/AGENTS.md:71`
- `/home/richard/src/GitHub/rjmurillo/ai-agents4/.claude/skills/session-init/SKILL.md`
- `/home/richard/src/GitHub/rjmurillo/ai-agents4/.claude/skills/session-log-fixer/SKILL.md`
```powershell
pwsh scripts/Validate-SessionProtocol.ps1
```

#### Source B (Actual Implementation)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/scripts/Validate-SessionJson.ps1`
**Status**: EXISTS (verified)

**Missing File**: `Validate-SessionProtocol.ps1` (does not exist in scripts directory)

#### Analysis
Twelve files reference `Validate-SessionProtocol.ps1` which doesn't exist. The actual script is `Validate-SessionJson.ps1`. This creates failures when following documentation instructions.

#### Suggestions
1. Global find-replace: Validate-SessionProtocol.ps1 → Validate-SessionJson.ps1
2. Create alias/symlink for backward compatibility during transition
3. Add deprecation notice if both scripts should coexist

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Global find-replace `Validate-SessionProtocol.ps1` → `Validate-SessionJson.ps1` in all 12 files.

**Files to Update**:
- AGENTS.md (line 71)
- `.claude/skills/session-init/SKILL.md`
- `.claude/skills/session-log-fixer/SKILL.md`
- `.claude/skills/session-init/references/validation-patterns.md`
- All other files identified in exploration

**Verification**: Run `scripts/Validate-SessionJson.ps1` after update to confirm script exists and works.

**Rationale**: Simple fix. No symlink needed - script was renamed, not duplicated. Clean cut removes ambiguity.

<!-- /Resolution -->

---

### Issue I5: Test-DocumentationOnly Gate Bypass Risk

**Type**: Implicit Contract Violation
**Severity**: HIGH
**Dimension**: K - Implicit Contract Integrity

#### Source A (Contract Promise)
**File**: `.claude/hooks/Invoke-RoutingGates.ps1`
**Lines**: 183-184
```powershell
# Tests whether the current changes are documentation-only
# only documentation files (.md) have been modified
```

#### Source B (Actual Implementation)
**File**: Same file
**Lines**: 215-223
```powershell
$_ -notmatch '\.md$' -and
$_ -notmatch '\.txt$' -and
$_ -notmatch '(^|/)README$' -and
$_ -notmatch '(^|/)LICENSE$' -and
$_ -notmatch '(^|/)CHANGELOG$' -and
$_ -notmatch '\.gitignore$'
```

#### Analysis
Function description claims "only documentation files (.md)" but implementation treats .txt, README, LICENSE, CHANGELOG, .gitignore as documentation too. QA gate could be incorrectly bypassed for non-markdown changes. Security risk if .txt contains executable config that bypasses validation.

#### Suggestions
1. Rename to `Test-NonCodeChangesOnly` to match actual behavior
2. Update docstring to list all allowed file types explicitly
3. Add comment explaining why these file types are considered documentation

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Update docstring to accurately document allowed file types. Keep function name.

**Change** (`.claude/hooks/Invoke-RoutingGates.ps1` lines 183-184):
```powershell
# Tests whether the current changes are documentation-only
# Allowed: .md, .txt, README, LICENSE, CHANGELOG, .gitignore files
# Rationale: These files don't affect runtime behavior and don't require QA validation
```

**Add inline comment** (line 215):
```powershell
# Documentation-only: markdown, text files, standard repo metadata, git config
$_ -notmatch '\.md$' -and
```

**Rationale**: Function name `Test-DocumentationOnly` is acceptable if we broaden "documentation" definition to include "non-executable repo metadata." Docstring fix addresses the incoherence. Security risk is minimal (.txt files are typically docs, not config in this repo pattern).

<!-- /Resolution -->

---

### Issue I6: Cyclomatic Complexity Threshold Ambiguity

**Type**: Cross-Reference Inconsistency
**Severity**: HIGH
**Dimension**: C - Cross-Reference Consistency

#### Source A
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/CLAUDE.md` (user global)
```markdown
Cyclomatic complexity ≤10
```

#### Source B
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/src/claude/qa.md`
```markdown
Cyclomatic complexity <= 10 per method
```

#### Source C
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.github/prompts/pr-quality-gate-qa.md`
```markdown
Complexity | Less than 10
[note: Any function over 15]
```

#### Analysis
Sources A and B specify ≤10 as standard. Source C introduces "15" threshold. Unclear if 15 is documentation error, warning threshold, or separate fail condition. Creates ambiguity about which threshold to enforce.

#### Suggestions
1. Clarify: 10 is target, 15 is hard limit (update docs to explain two-tier system)
2. Standardize on single threshold (10) and remove 15 reference
3. Document as warning (10) vs error (15) thresholds with rationale

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Standardize on ≤10 as single threshold. Remove "15" reference as documentation error.

**Change** (`.github/prompts/pr-quality-gate-qa.md`):
- Remove "[note: Any function over 15]"
- Update to: "Complexity | ≤10 (per CLAUDE.md standard)"

**Rationale**: CLAUDE.md is user's global standard (≤10). The "15" appears to be copy-paste error or outdated threshold. No evidence in codebase of two-tier system. Simplify to single threshold for consistency.

<!-- /Resolution -->

---

### Issue I7: Error Handling Pattern Documentation Asymmetry

**Type**: Cross-Reference Inconsistency
**Severity**: HIGH
**Dimension**: C - Cross-Reference Consistency

#### Source A (Complete Documentation)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/scripts/AGENTS.md`
**Lines**: 78-87
```powershell
$ErrorActionPreference = 'Stop'  # Fail fast

try {
    # Operations
    exit 0  # Success
} catch {
    Write-Error $_.Exception.Message
    exit 1  # Failure
}
```

#### Source B (Missing Documentation)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/AGENTS.md`
**Location**: No error handling pattern section

#### Source C (Broken Reference)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.gemini/styleguide.md`
**Line**: 11
```markdown
| PowerShell standards | `scripts/AGENTS.md`, `AGENTS.md` Coding Standards section |
```

#### Analysis
Explicit PowerShell error handling pattern documented only in scripts/AGENTS.md. Root AGENTS.md lacks this documentation. Styleguide references non-existent "AGENTS.md Coding Standards section." Pattern is critical for exit code standardization but has no canonical location.

#### Suggestions
1. Add error handling pattern section to root AGENTS.md
2. Make scripts/AGENTS.md canonical and update styleguide reference
3. Remove broken reference from styleguide.md or fix AGENTS.md structure

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Update styleguide.md reference to point only to scripts/AGENTS.md as canonical PowerShell standards source.

**Change** (`.gemini/styleguide.md` line 11):
```markdown
| PowerShell standards | `scripts/AGENTS.md` (canonical) |
```

**Rationale**: PR #871 already established scripts/AGENTS.md as the consolidated PowerShell standards location. Root AGENTS.md is for cross-tool agent instructions, not PowerShell-specific patterns. Fixing the reference completes the consolidation intent. No need to duplicate error handling pattern in root AGENTS.md.

<!-- /Resolution -->

---

### Issue I8: Test-ProtectedBranch Semantic Mismatch

**Type**: Implicit Contract Violation
**Severity**: MEDIUM
**Dimension**: K - Implicit Contract Integrity

#### Source A (Name Contract)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1`
**Line**: 51
```powershell
function Test-ProtectedBranch {
```

#### Source B (Implementation)
**File**: Same file
**Lines**: 58-59
```powershell
$protectedBranches = @('main', 'master')
return $protectedBranches -contains $Branch
```

#### Analysis
Function name "Test-ProtectedBranch" implies testing for GitHub branch protection rules (requiring reviews, status checks, etc.). Implementation only checks hardcoded list. "Protected branch" has technical meaning in GitHub that this doesn't verify.

#### Suggestions
1. Rename to `Test-IsMainOrMaster` to reflect actual behavior
2. Rename to `Test-RestrictedBranch` if restricting branch names
3. Implement actual GitHub API check for branch protection rules

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Rename function to `Test-IsMainOrMasterBranch` for semantic accuracy.

**Change** (`.claude/hooks/SessionStart/Invoke-SessionInitializationEnforcer.ps1` line 51):
```powershell
function Test-IsMainOrMasterBranch {
    param([string]$Branch)
    # Check if branch is main or master (common default branches)
    $protectedBranches = @('main', 'master')
    return $protectedBranches -contains $Branch
}
```

**Update all callers** to use new function name.

**Rationale**: Name accurately reflects behavior (checking if branch is main/master) without implying GitHub branch protection API checks. Avoids confusion with GitHub's "protected branch" technical feature.

<!-- /Resolution -->

---

### Issue I9: Exit Code Documentation Missing ADR-035 Format

**Type**: Documentation Gap
**Severity**: MEDIUM
**Dimension**: I - Completeness & Documentation Gaps

#### Source A (Requirement)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.agents/architecture/ADR-035-exit-code-standardization.md`
**Lines**: 172-193
```markdown
All scripts MUST include exit code documentation in the script header
```

#### Source B (Incomplete Implementation)
**Scripts**: 19+ scripts in `.claude/skills/github/scripts/pr/`
**Examples**:
- `Merge-PR.ps1` - Has exit statements, no `.NOTES` section
- `New-PR.ps1` - Has exit statements, no ADR-035 format
- `Close-PR.ps1` - Has exit statements, no ADR-035 format

#### Analysis
ADR-035 Phase 1 requires "Add exit code documentation to existing scripts without changing behavior." Only ~2/20 sampled scripts have complete ADR-035 compliant headers. Migration incomplete.

#### Suggestions
1. Create GitHub issue for Phase 1 implementation (per ADR-035 Line 230)
2. Add exit code documentation to all scripts systematically
3. Add linting rule to enforce ADR-035 header format

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Create GitHub tracking issue for ADR-035 Phase 1 implementation.

**Issue Title**: "ADR-035 Phase 1: Add exit code documentation to existing scripts"

**Scope**:
- 19+ scripts in `.claude/skills/github/scripts/pr/`
- Scripts in `.claude/hooks/`
- Scripts in `.github/scripts/`
- All other scripts with exit statements

**Template** (from ADR-035 Lines 172-193):
```powershell
.NOTES
    Exit Codes: 0=Success, 1=Validation error, 2=Missing parameter, 3=API error, 4=Auth error
    See: ADR-035 Exit Code Standardization
```

**Rationale**: ADR-035 Phase 1 explicitly requires systematic documentation addition. Creating tracked issue prevents this from being forgotten and enables incremental progress.

<!-- /Resolution -->

---

### Issue I10: Workflow YAML Logic Violates ADR-006

**Type**: Policy Violation
**Severity**: MEDIUM
**Dimension**: H - Policy & Convention Compliance

#### Source A (Policy)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/AGENTS.md`
**Line**: 299 (references ADR-006)
```markdown
No logic in workflow YAML files (delegate to PowerShell modules)
```

#### Source B (Violation)
**File**: `/home/richard/src/GitHub/rjmurillo/ai-agents4/.github/workflows/validate-generated-agents.yml`
**Lines**: 60-77
```yaml
run: |
  if [ -f "path/file.md" ]; then
    echo "exists"
  else
    echo "missing"
  fi
```

#### Analysis
ADR-006 requires thin workflows with logic in testable PowerShell modules. Workflow contains bash conditional logic in `run:` block instead of delegating to script. Violates testability principle.

#### Suggestions
1. Extract logic to PowerShell script in scripts/ directory
2. Update workflow to call: `pwsh scripts/Test-FileExists.ps1 -Path "path/file.md"`
3. Document as pre-ADR-006 workflow with migration plan

#### Resolution
<!-- USER: Write your decision below. Be specific. -->

**Decision**: Document as grandfathered pre-ADR-006 workflow. Add to technical debt backlog.

**Immediate**: Add comment in workflow file:
```yaml
# TODO: Extract logic to PowerShell module per ADR-006 thin workflows principle
# Grandfathered: Pre-dates ADR-006, scheduled for migration in workflow refactor epic
run: |
  if [ -f "path/file.md" ]; then
```

**Rationale**: Workflow refactoring is separate epic scope. PR #871 focuses on documentation consolidation. Document the violation for future cleanup rather than expanding scope. Bash in workflows is common pattern across GitHub Actions ecosystem.

<!-- /Resolution -->

---

## Summary

**Total Issues**: 10
**Critical**: 2 (Session format migration, dead script references)
**High**: 5 (ADR-005 violations, exit codes, gate bypass, complexity ambiguity, error pattern)
**Medium**: 3 (Protected branch naming, ADR-035 docs, workflow logic)

**Recommended Priority**:
1. I4 (Dead script refs) - Blocks documentation followers
2. I1 (Session migration) - Affects 299+ files
3. I2 (ADR-005 violations) - 9 policy violations
4. I3 (Exit codes) - Affects script reliability
5. I5-I10 - Address based on impact to PR #871 scope

**Next Steps**: User fills in Resolution sections, then run reconciliation phase (steps 14-22).
