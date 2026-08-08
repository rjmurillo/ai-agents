# Ci Infrastructure: Required Check Path Filter Bypass

## Skill-CI-Infrastructure-006: Required Check Path Filter Bypass

**Statement**: Use workflow_dispatch to manually trigger required checks blocked by path filters

**Atomicity**: 89%

**Context**: PR blocked by required status check that won't trigger due to path filters

**Evidence**: PR #298 - YAML-only changes don't trigger Pester Tests (PowerShell path filter), manually triggered via workflow_dispatch, tests passed and PR unblocked

**Trigger**: PR shows "Waiting for status to be reported" for required check that won't run due to path filters

**Command**: `gh workflow run pester-tests.yml --ref <branch-name>`

## Direct-Input Filter Rule

Issue #4408 exposed a second failure mode. A required check can report success
without running tests when its internal filter omits non-code files that tests
read directly.

For a diff-scoped test workflow:

1. Enumerate every tracked direct input from `HEAD`, not the working tree.
2. Add each input root explicitly to the internal filter.
3. Test every tracked file under each root against the pinned action's matcher.
4. Keep an unrelated-file negative control so a broad glob cannot hide overreach.

The `Run Python Tests` workflow needs all three rule and instruction roots:

- `.claude/rules/**`
- `.github/instructions/**`
- `src/copilot-cli/instructions/**`

A global Markdown glob is wrong because historical session logs do not affect
pytest outcomes. The regression test belongs beside the workflow and must parse
the workflow YAML rather than duplicate the filter in test data.

**Related Skills**:
- Skill-CI-Infrastructure-004 (label/check validation before deployment)
- skills-dorny-paths-filter-checkout-requirement

**SMART Validation**:
- Specific: Y - One concept: manual workflow trigger workaround
- Measurable: Y - PR #298 unblocked, tests passed
- Attainable: Y - workflow_dispatch available via gh CLI
- Relevant: Y - Applies when required checks have path filters
- Timely: Y - Trigger: PR blocked by required check that won't run

## Related

- `decision-a-whole-corpus-gate-cannot-be-path-filtered.md` is the **opposite**
  failure of the same mechanism. Here the path filter stops a required check
  from ever reporting, so the PR waits forever and the problem announces itself.
  There the filter makes a whole-corpus check report **success** without
  measuring, so a real breach stays invisible until someone edits a filtered
  file. The discriminator is whether the gate's verdict depends on files outside
  the diff. If it does, do not path-filter it at all, and `workflow_dispatch` is
  not the remedy.
- [ci-infrastructure-001-fail-fast-infrastructure-failures](ci-infrastructure-001-fail-fast-infrastructure-failures.md)
- [ci-infrastructure-002-explicit-retry-timing](ci-infrastructure-002-explicit-retry-timing.md)
- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md)
- [ci-infrastructure-004-error-message-investigation](ci-infrastructure-004-error-message-investigation.md)
- [ci-infrastructure-aggregate-job-always-pattern](ci-infrastructure-aggregate-job-always-pattern.md)
