# Technical Guardrails Implementation Guide

## Overview

This document describes the technical guardrails implemented to prevent autonomous agent execution failures. These guardrails enforce protocol compliance through automation rather than trust.

**Related**: Issue #230, Retrospective `.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md`

## Problem Statement

PR #226 was merged with 6 defects due to complete guardrail failure during autonomous execution. The agent bypassed all safety protocols to "be helpful" and complete the task quickly.

**Root Cause**: Trust-based protocol compliance fails when agents are given autonomy. Technical enforcement is required.

## Guardrails Implemented

### Pre-Commit Jobs

Lefthook filters staged files and runs the named validators in `lefthook.yml`
before each commit. That configuration is the authoritative list of jobs.

#### Validator Ownership

`lefthook.yml` owns changed-file filters, job names, and validator commands.
Reusable Git hook policy lives in `scripts/validation/git_hook_policy.py`.
Consult the configuration for the current jobs instead of maintaining a second
checklist here.

### Validation Scripts

#### PR Description Validation (BLOCKING in CI)

**Script**: `scripts/validation/pr_description.py`

**Usage**:

```bash
python3 scripts/validation/pr_description.py --pr-number 226 --ci
```

**Validates**:

- Files mentioned in PR description are actually in the diff (CRITICAL)
- Significant changed files are mentioned in description (WARNING)

**Exit Codes**:

- `0` = Pass
- `1` = Critical failure (CI blocks merge)
- `2` = Usage/environment error

**Prevents**: Analyst CRITICAL_FAIL verdicts (seen in PR #199)

#### GitHub Skill PR Creation

**Script directory**: `.claude/skills/github/scripts/pr/`

**Usage**:

```bash
# Normal PR creation through the github skill
uv run python .claude/skills/github/scripts/pr/new_pr.py --title "feat: Add feature" --body "Description"

# Draft PR
uv run python .claude/skills/github/scripts/pr/new_pr.py --title "WIP: Feature" --body "Description" --draft
```

**Validations Run**:

1. Session End validation (if `.agents/` changes)
2. Skill violation detection (WARNING)
3. Test coverage detection (WARNING)
4. Note about post-creation PR description validation

**Force Mode**: Creates audit trail in `.agents/audit/pr-creation-force-*.txt`

### Unattended Execution Requirements

**Added**: Stricter protocol for autonomous/unattended operation

**Requirements**:

| Req | Requirement | Verification |
|-----|-------------|--------------|
| MUST | Invoke orchestrator for task coordination | Orchestrator invoked in transcript |
| MUST | Invoke critic before ANY merge or PR creation | Critic report in `.agents/critique/` |
| MUST | Invoke QA after ANY code change | QA report in `.agents/qa/` |
| MUST NOT | Mark security comments "won't fix" without security agent review | Security approval documented |
| MUST NOT | Merge without explicit validation gate pass | All validations passed |
| MUST | Document all "won't fix" decisions with rationale | Transcript or pull request contains justification |
| MUST | Use skill scripts instead of raw commands | No raw `gh`, `curl` in automation |

**Rationale**: Autonomous execution removes human oversight, requiring **stricter** guardrails.

### CI Workflow Validation

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

1. Ensure the per-issue handoff is current and HANDOFF.md is unchanged
2. Stage all changes: `git add .`
3. Commit: `git commit -m "feat: description"`
4. Pre-commit hooks run automatically

If hooks fail, fix the reported issue and retry the commit.

#### Before Creating PR

**Recommended**: Use validated PR wrapper

```bash
uv run --frozen python -m scripts.new_validated_pr --title "feat: Add feature" --body "Full description"
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

1. Load the current per-issue handoff
2. Invoke orchestrator for coordination
3. Invoke critic before ANY merge
4. Invoke QA after ANY code change
5. Use skill scripts (never raw `gh`)
6. Document all "won't fix" decisions

**Verification**:

- Pre-commit hooks validate a staged session log
- CI enforces PR description validation
- QA validation required for code changes

#### Protocol Violations

If violation detected:

1. **Stop work immediately**
2. **Invoke missing agents** (orchestrator, critic, QA)
3. **Document violation** in the transcript or per-issue handoff
4. **Complete all MUST requirements** before resuming

## Success Metrics

| Metric | Baseline (Pre-#230) | Target | Status |
|--------|---------------------|--------|--------|
| Session Protocol CRITICAL_FAIL | 60% | <5% | ⏳ Pending data |
| PR description mismatches | 10% | <2% | ⏳ Pending data |
| Defects merged to main | 6 (PR #226) | 0 | ✅ 0 since implementation |
| QA WARN rate | 40% | <15% | ⏳ Pending data |
| Autonomous execution failures | 100% (1/1) | <10% | ⏳ Pending data |

## Testing

Script tests live under `tests/`:

```bash
# Run all tests
uv run pytest tests/ -x

# Run a targeted test selection
uv run pytest tests/ -k stale_script_ref -q
```

**Test Coverage**:

- `Detect-SkillViolation.Tests.ps1` - Skill violation detection
- `Detect-TestCoverageGaps.Tests.ps1` - Test coverage detection
- `New-ValidatedPR.Tests.ps1` - Validated PR creation
- `Validate-PRDescription.ps1` - (Manual testing with live PRs)
- `tests/test_validate_memory_tier.py` - Memory tier validation (16 tests)

## Known Limitations

1. **PR Description Validation**: Runs post-creation (can't block PR creation, only merge)
2. **Review Comment Detection**: GitHub API limitations on "resolved" status
3. **Skill Violations**: WARNING level (non-blocking) to avoid false positives
4. **Test Coverage**: WARNING level (non-blocking) as not all scripts need tests

## Future Enhancements

1. **Branch Protection Rules**
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

**Solution**: Install and verify Lefthook

```bash
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
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

```bash
# Run script directly
python3 scripts/detect_skill_violation.py

# Run memory tier validation directly
python3 scripts/validate_memory_tier.py --path .serena/memories
```

## Related Documents

- [`.claude/rules/session-logs.md`](../.claude/rules/session-logs.md) - Session log mechanics
- [Retrospective: PR #226](../.agents/retrospective/2025-12-22-pr-226-premature-merge-failure.md) - Failure analysis
- [Issue #230](https://github.com/rjmurillo/ai-agents/issues/230) - Implementation tracking
- [usage-mandatory.md](../.serena/memories/usage-mandatory.md) - Skill usage policy
