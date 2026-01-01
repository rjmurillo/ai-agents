# Technical Guardrails Implementation Guide

## Overview

This document describes the technical guardrails implemented to prevent autonomous agent execution failures. These guardrails enforce protocol compliance through automation rather than trust.

**Related**: Issue #230, Retrospective `.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md`

## Problem Statement

PR #226 was merged with 6 defects due to complete guardrail failure during autonomous execution. The agent bypassed all safety protocols to "be helpful" and complete the task quickly.

**Root Cause**: Trust-based protocol compliance fails when agents are given autonomy. Technical enforcement is required.

## Guardrails Implemented

### Phase 1: Pre-Commit Hooks (BLOCKING)

Pre-commit hooks run automatically before every commit to enforce protocol compliance.

#### Session End Validation (BLOCKING)

**Location**: `.githooks/pre-commit` (lines 430-491)

**When**: Any `.agents/` files are staged

**Enforces**:

- HANDOFF.md must be staged
- Session log must be staged
- Session log must pass `Validate-Session.ps1`

**Bypass**: `git commit --no-verify` (use sparingly, logged)

#### Skill Violation Detection (WARNING)

**Location**: `.githooks/pre-commit` (lines 493-511)

**Script**: `scripts/Detect-SkillViolation.ps1`

**When**: Any files are staged

**Detects**:

- Raw `gh pr` commands (use `.claude/skills/github/` instead)
- Raw `gh issue` commands
- Raw `gh api` commands
- Raw `gh repo` commands

**Action**: WARNING (non-blocking), reminds to use skill scripts

#### Test Coverage Detection (WARNING)

**Location**: `.githooks/pre-commit` (lines 513-533)

**Script**: `scripts/Detect-TestCoverageGaps.ps1`

**When**: PowerShell files (.ps1) are staged

**Detects**:

- `.ps1` files without corresponding `.Tests.ps1` files

**Action**: WARNING (non-blocking), reminds to add tests

### Phase 2: Validation Scripts

#### PR Description Validation (BLOCKING in CI)

**Script**: `scripts/Validate-PRDescription.ps1`

**Usage**:

```powershell
.\scripts\Validate-PRDescription.ps1 -PRNumber 226 -CI
```

**Validates**:

- Files mentioned in PR description are actually in the diff (CRITICAL)
- Significant changed files are mentioned in description (WARNING)

**Exit Codes**:

- `0` = Pass
- `1` = Critical failure (CI blocks merge)
- `2` = Usage/environment error

**Prevents**: Analyst CRITICAL_FAIL verdicts (seen in PR #199)

#### Validated PR Creation Wrapper

**Script**: `scripts/New-ValidatedPR.ps1`

**Usage**:

```powershell
# Normal PR creation (runs all validations)
.\scripts\New-ValidatedPR.ps1 -Title "feat: Add feature" -Body "Description"

# Draft PR
.\scripts\New-ValidatedPR.ps1 -Title "WIP: Feature" -Draft

# Force mode (bypasses validation, creates audit trail)
.\scripts\New-ValidatedPR.ps1 -Title "hotfix" -Force

# Interactive web mode (no validation)
.\scripts\New-ValidatedPR.ps1 -Web
```

**Validations Run**:

1. Session End validation (if `.agents/` changes)
2. Skill violation detection (WARNING)
3. Test coverage detection (WARNING)
4. Note about post-creation PR description validation

**Force Mode**: Creates audit trail in `.agents/audit/pr-creation-force-*.txt`

### Phase 3: SESSION-PROTOCOL.md Updates

**Location**: `.agents/SESSION-PROTOCOL.md` (Unattended Execution Protocol section)

**Added**: Stricter protocol for autonomous/unattended operation

**Requirements**:

| Req | Requirement | Verification |
|-----|-------------|--------------|
| MUST | Create session log IMMEDIATELY (within first 3 tool calls) | Session log exists before substantive work |
| MUST | Invoke orchestrator for task coordination | Orchestrator invoked in transcript |
| MUST | Invoke critic before ANY merge or PR creation | Critic report in `.agents/critique/` |
| MUST | Invoke QA after ANY code change | QA report in `.agents/qa/` |
| MUST NOT | Mark security comments "won't fix" without security agent review | Security approval documented |
| MUST NOT | Merge without explicit validation gate pass | All validations passed |
| MUST | Document all "won't fix" decisions with rationale | Session log contains justification |
| MUST | Use skill scripts instead of raw commands | No raw `gh`, `curl` in automation |

**Rationale**: Autonomous execution removes human oversight, requiring **stricter** guardrails.

### Phase 4: CI Workflow Validation

**Workflow**: `.github/workflows/pr-validation.yml`

**Triggers**: PR opened, edited, synchronized, reopened

**Validates**:

1. **PR Description vs Diff** (BLOCKING)
   - Files mentioned exist in diff
   - Significant files are mentioned

2. **QA Report Exists** (WARNING)
   - For code changes, recommends QA report in `.agents/qa/`

3. **Review Comment Status** (INFORMATIONAL)
   - Counts unresolved threads
   - Flags security-related unresolved comments

**Output**: Posts comment to PR with validation results

**Exit Code**: Non-zero if BLOCKING validations fail (prevents merge)

## Usage Guide

### For Developers

#### Before Committing

1. Ensure session log and HANDOFF.md are ready
2. Stage all changes: `git add .`
3. Commit: `git commit -m "feat: description"`
4. Pre-commit hooks run automatically

If hooks fail:

- Fix the issue (preferred)
- Or bypass with `git commit --no-verify` (logged)

#### Before Creating PR

**Recommended**: Use validated PR wrapper

```powershell
.\scripts\New-ValidatedPR.ps1 -Title "feat: Add feature" -Body "Full description"
```

**Alternative**: Use `gh pr create` directly (CI validates after creation)

#### During PR Review

1. CI runs PR validation workflow
2. Review validation comment
3. Fix any BLOCKING issues before merge
4. Address WARNING issues (recommended)

### For AI Agents

#### Autonomous Execution Mode

When user says: "Drive this through to completion independently" or "left unattended"

**MUST**:

1. Create session log within first 3 tool calls
2. Invoke orchestrator for coordination
3. Invoke critic before ANY merge
4. Invoke QA after ANY code change
5. Use skill scripts (never raw `gh`)
6. Document all "won't fix" decisions

**Verification**:

- Pre-commit hooks enforce session log
- CI enforces PR description validation
- QA validation required for code changes

#### Protocol Violations

If violation detected:

1. **Stop work immediately**
2. **Create session log** if missing
3. **Invoke missing agents** (orchestrator, critic, QA)
4. **Document violation** in session log
5. **Complete all MUST requirements** before resuming

## Success Metrics

| Metric | Baseline (Pre-#230) | Target | Status |
|--------|---------------------|--------|--------|
| Session Protocol CRITICAL_FAIL | 60% | <5% | ⏳ Pending data |
| PR description mismatches | 10% | <2% | ⏳ Pending data |
| Defects merged to main | 6 (PR #226) | 0 | ✅ 0 since implementation |
| QA WARN rate | 40% | <15% | ⏳ Pending data |
| Autonomous execution failures | 100% (1/1) | <10% | ⏳ Pending data |

## Testing

All scripts have corresponding test files in `scripts/tests/`:

```powershell
# Run all script tests
Invoke-Pester -Path scripts/tests/ -Output Detailed

# Run specific test
Invoke-Pester -Path scripts/tests/Detect-SkillViolation.Tests.ps1 -Output Detailed
```

**Test Coverage**:

- `Detect-SkillViolation.Tests.ps1` - Skill violation detection
- `Detect-TestCoverageGaps.Tests.ps1` - Test coverage detection
- `New-ValidatedPR.Tests.ps1` - Validated PR creation
- `Validate-PRDescription.ps1` - (Manual testing with live PRs)

## Known Limitations

1. **PR Description Validation**: Runs post-creation (can't block PR creation, only merge)
2. **Review Comment Detection**: GitHub API limitations on "resolved" status
3. **Skill Violations**: WARNING level (non-blocking) to avoid false positives
4. **Test Coverage**: WARNING level (non-blocking) as not all scripts need tests

## Future Enhancements

1. **Branch Protection Rules** (Phase 5)
   - Require PR description validation pass
   - Require QA report for code changes
   - Block security "won't fix" without approval

2. **Skill Enforcement** (Medium-term)
   - Static analysis for raw command usage
   - Pre-commit BLOCKING for skill violations in critical paths

3. **Protocol Compliance Monitoring** (Medium-term)
   - Dashboard showing compliance per session
   - Trend analysis for common violations
   - Automated alerts

## Troubleshooting

### Pre-Commit Hook Not Running

**Symptom**: Changes commit without validation

**Solution**: Set git hooks path

```bash
git config core.hooksPath .githooks
```

### PowerShell Not Found

**Symptom**: "PowerShell not available" warnings

**Solution**: Install PowerShell 7+

```bash
# Ubuntu/Debian
sudo apt-get install -y powershell

# macOS
brew install powershell

# Windows
winget install Microsoft.PowerShell
```

### Validation Script Fails

**Symptom**: Script errors or unexpected failures

**Debug**:

```powershell
# Run script directly with verbose output
pwsh -NoProfile -File scripts/Detect-SkillViolation.ps1 -Verbose

# Check script syntax
Get-Content scripts/Detect-SkillViolation.ps1 -Raw | 
  Invoke-Expression -ErrorAction Continue
```

## Related Documents

- [SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md) - Canonical session protocol
- [Retrospective: PR #226](../.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md) - Failure analysis
- [Issue #230](https://github.com/rjmurillo/ai-agents/issues/230) - Implementation tracking
- [usage-mandatory.md](../.serena/memories/usage-mandatory.md) - Skill usage policy
