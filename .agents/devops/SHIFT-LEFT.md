# Shift-Left Validation Strategy

**Status**: Active
**Version**: 1.0
**Last Updated**: 2025-12-23

## Overview

Shift-left validation catches issues early in development before PR creation.
This reduces review cycles, accelerates merge velocity, and improves code quality.

## Unified Validation Runner

Use `scripts/Validate-PrePR.ps1` as the single command to run all shift-left validations.

### Quick Start

```powershell
# Full validation (recommended before creating PR)
pwsh scripts/Validate-PrePR.ps1

# Quick validation (fast checks only, for rapid iteration)
pwsh scripts/Validate-PrePR.ps1 -Quick

# Verbose output (for troubleshooting)
pwsh scripts/Validate-PrePR.ps1 -Verbose
```

## Validation Sequence

The runner executes validations in optimized order (fast checks first):

| # | Validation | Purpose | Skip if -Quick | Typical Duration |
|---|------------|---------|----------------|------------------|
| 1 | Session End | Verify session protocol compliance | No | 2-5s |
| 2 | Pester Tests | Run all unit tests | No | 10-30s |
| 3 | Markdown Lint | Auto-fix and validate markdown | No | 5-10s |
| 4 | Path Normalization | Check for absolute paths | Yes | 15-30s |
| 5 | Planning Artifacts | Validate planning consistency | Yes | 10-20s |
| 6 | Agent Drift | Detect semantic drift | Yes | 20-40s |

### Total Duration

- **Quick mode**: ~20-50s (validations 1-3)
- **Full mode**: ~60-120s (all validations)

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | PASS | All validations succeeded, ready for PR |
| 1 | FAIL | One or more validations failed, fix issues |
| 2 | ERROR | Environment or configuration issue |

## Validation Details

### 1. Session End Validation

**Script**: `scripts/Validate-SessionEnd.ps1`

**Checks**:

- Session log exists in `.agents/sessions/`
- Session End checklist complete (all MUST rows checked)
- Evidence provided for each checklist item
- HANDOFF.md updated with session link
- Markdown linting passed
- Git worktree clean (all changes committed)

**Fix suggestions**:

- Create session log if missing
- Complete Session End checklist in session log
- Run `npx markdownlint-cli2 --fix "**/*.md"`
- Commit all changes including `.agents/` files

### 2. Pester Unit Tests

**Script**: `build/scripts/Invoke-PesterTests.ps1`

**Checks**:

- All Pester tests pass
- Test coverage meets thresholds
- No test failures or errors

**Fix suggestions**:

- Review test failure output
- Run individual test file: `pwsh -File tests/MyTest.Tests.ps1`
- Use `Invoke-Pester -Output Diagnostic` for detailed output

### 3. Markdown Linting

**Tool**: `markdownlint-cli2`

**Checks**:

- No markdown linting violations
- Auto-fixable issues corrected
- Code blocks have language identifiers

**Fix suggestions**:

- Run `npx markdownlint-cli2 --fix "**/*.md"` to auto-fix
- Add language identifiers to code blocks (MD040)
- Wrap generic types like `ArrayPool<T>` in backticks (MD033)

### 4. Path Normalization

**Script**: `build/scripts/Validate-PathNormalization.ps1`

**Checks**:

- No absolute paths in documentation files
- All paths use relative format
- Cross-platform path separators (forward slashes)

**Fix suggestions**:

- Replace absolute paths with relative paths
- Use forward slashes (/) for cross-platform compatibility
- Examples: `docs/guide.md`, `../architecture/design.md`

### 5. Planning Artifacts

**Script**: `build/scripts/Validate-PlanningArtifacts.ps1`

**Checks**:

- Effort estimate consistency (within 20% threshold)
- No orphan conditions (all conditions linked to tasks)
- Requirement coverage complete

**Fix suggestions**:

- Add Estimate Reconciliation section to task breakdown
- Link specialist conditions to specific tasks
- Add Conditions column to Work Breakdown table

### 6. Agent Drift Detection

**Script**: `build/scripts/Detect-AgentDrift.ps1`

**Checks**:

- Semantic alignment between Claude and VS Code agents
- Core sections consistent (>80% similarity)
- No unintended divergence in responsibilities

**Fix suggestions**:

- Review drifting sections in output
- Sync content between agent variants
- Document intentional platform-specific differences

## Integration with Workflows

### Pre-Commit Hook

The pre-commit hook (`.githooks/pre-commit`) runs a subset of validations automatically:

- Markdown linting (auto-fix enabled)
- PowerShell script analysis
- Session End validation (if `.agents/` files staged)

**Recommendation**: Run `Validate-PrePR.ps1` before committing to catch issues earlier.

### CI Pipeline

The full validation suite runs in CI via GitHub Actions workflow:

- Workflow: `.github/workflows/shift-left-validation.yml`
- Trigger: On push to feature branches
- Mode: Full validation (no -Quick flag)

### Developer Workflow

Recommended workflow for feature development:

```text
1. Make changes
2. Run: pwsh scripts/Validate-PrePR.ps1 -Quick
3. Fix any issues
4. Commit changes (pre-commit hook runs subset)
5. Before PR: pwsh scripts/Validate-PrePR.ps1 (full validation)
6. Create PR (CI runs full validation)
```

## Performance Optimization

### Quick Mode

Use `-Quick` flag during rapid iteration to skip slow validations:

```powershell
pwsh scripts/Validate-PrePR.ps1 -Quick
```

**Skipped validations**:

- Path Normalization (15-30s saved)
- Planning Artifacts (10-20s saved)
- Agent Drift (20-40s saved)

**Total time saved**: ~50-90s per run

### Parallel Execution

Validations run sequentially by design to:

- Provide clear progress feedback
- Fail fast on blocking issues
- Simplify error diagnosis

Future enhancement: Add `-Parallel` flag for independent validations.

## Troubleshooting

### Environment Issues

**Symptom**: Script exits with code 2

**Common causes**:

- PowerShell not installed: Install PowerShell Core 7+
- Node.js not installed: Install Node.js 18+ for markdownlint
- Git repository not initialized: Run in git repository root

### Validation Failures

**Symptom**: Script exits with code 1

**Steps**:

1. Review error messages in output
2. Run individual validation script for details
3. Fix issues based on fix suggestions above
4. Re-run `Validate-PrePR.ps1`

### Performance Issues

**Symptom**: Validation takes >2 minutes

**Optimization**:

- Use `-Quick` flag for rapid iteration
- Skip tests during markdown-only changes: `-SkipTests`
- Run individual validations: `pwsh scripts/Validate-SessionEnd.ps1`

## Metrics

Target validation times (as of 2025-12-23):

| Metric | Target | Maximum |
|--------|--------|---------|
| Quick mode | <30s | 60s |
| Full mode | <90s | 120s |
| Session End | <5s | 10s |
| Pester Tests | <20s | 60s |
| Markdown Lint | <10s | 20s |

**Current baseline**: Measured on Ubuntu 22.04, Intel i7, 16GB RAM

## Future Enhancements

Planned improvements:

- **Parallel execution**: Add `-Parallel` flag for independent validations
- **Incremental validation**: Skip unchanged files
- **Watch mode**: Auto-run on file changes
- **IDE integration**: VS Code task definitions
- **Metrics dashboard**: Track validation trends over time

## Related Documentation

- **Session Protocol**: `.agents/SESSION-PROTOCOL.md`
- **Pre-commit Hook**: `.githooks/pre-commit`
- **CI Pipeline**: `.github/workflows/shift-left-validation.yml`
- **DevOps Patterns**: `.agents/devops/validation-runner-pattern.md`

## References

- **Issue #325**: Unified shift-left validation runner
- **ADR-017**: Tiered memory index architecture
- **ADR-014**: Distributed handoff architecture
- **ADR-005**: PowerShell-only scripting standard
