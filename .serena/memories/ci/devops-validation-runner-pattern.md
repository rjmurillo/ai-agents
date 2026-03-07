# DevOps: Unified Validation Runner Pattern

## Context

Issue #325: Create unified shift-left validation runner script.

## Solution

**Script**: `scripts/Validate-PrePR.ps1`

Unified validation orchestration that runs all shift-left validations in optimized order.

## Key Features

1. **Optimized validation order**: Fast checks first (session end, tests, markdown), slow checks last (path normalization, planning artifacts, agent drift)
2. **Quick mode**: `-Quick` flag skips slow validations (saves ~50-90s per run)
3. **Fail-fast**: Stop on first failure for quick feedback
4. **Consistent status indicators**: [PASS], [FAIL], [WARNING], [SKIP], [RUNNING]
5. **NO_COLOR support**: Respects CI environments
6. **Clear fix suggestions**: Actionable error messages with remediation steps
7. **Performance metrics**: Track duration, pass/fail counts

## Validation Sequence

1. **Session End** (2-5s): Validate latest session log
2. **Pester Tests** (10-30s): Run all unit tests
3. **Markdown Lint** (5-10s): Auto-fix and validate markdown
4. **Path Normalization** (15-30s, skip if -Quick): Check for absolute paths
5. **Planning Artifacts** (10-20s, skip if -Quick): Validate planning consistency
6. **Agent Drift** (20-40s, skip if -Quick): Detect semantic drift

## Performance

**Quick mode**: ~20-50s (validations 1-3)
**Full mode**: ~60-120s (all validations)

**Baseline** (Ubuntu 22.04, i7, 16GB RAM):
- Quick: ~35s
- Full: ~95s

## Integration Points

### Pre-Commit Hook

Pre-commit hook now suggests running unified validation:

```bash
echo_info "Before creating a PR, run the full validation suite:"
echo_info "  pwsh scripts/Validate-PrePR.ps1"
```

### Developer Workflow

```text
Make changes → Quick validation → Fix → Commit → Full validation → Create PR
```

## Exit Codes

- 0 = PASS (all validations succeeded)
- 1 = FAIL (one or more validations failed)
- 2 = ERROR (environment or configuration issue)

## Future Enhancements

1. **Parallel execution**: Add `-Parallel` flag for independent validations
2. **Incremental validation**: Skip unchanged files
3. **Watch mode**: Auto-run on file changes
4. **IDE integration**: VS Code task definitions

## Related Files

- `scripts/Validate-PrePR.ps1` - Main validation runner
- `.agents/SHIFT-LEFT.md` - User-facing documentation
- `.agents/devops/validation-runner-pattern.md` - DevOps pattern documentation
- `.githooks/pre-commit` - Pre-commit hook with validation suggestion

## Lessons Learned

1. **Fast feedback is critical**: Quick mode (30s) vs Full mode (90s) dramatically changes developer behavior
2. **Fail-fast reduces cognitive load**: Stop on first failure to focus attention
3. **Clear fix suggestions are essential**: Generic error messages are useless
4. **Consistent status indicators improve scannability**: Text-based indicators easier to scan than emojis

## Session

Session 87: 2025-12-23
Branch: docs/velocity
Issue: #325
