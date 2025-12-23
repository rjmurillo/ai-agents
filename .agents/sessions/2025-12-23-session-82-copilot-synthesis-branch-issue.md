# Session 82: Copilot Synthesis Branch Execution Investigation

**Date**: 2025-12-23
**Issue**: #265, PR #296
**Branch**: fix/copilot-synthesis-not-posting-comment
**Status**: INVESTIGATION COMPLETE

---

## Protocol Compliance

| Phase | Status | Evidence |
|-------|--------|----------|
| Serena Init | PASS | `mcp__serena__initial_instructions` called |
| HANDOFF Read | PASS | Read `.agents/HANDOFF.md` |
| Session Log | PASS | This file created |

---

## Context

User reported that workflow run 20469129997 (triggered on Issue #284) did not post a synthesis comment, even though it was triggered "from the PR branch" that contains the fallback logic fix.

---

## Investigation Results

### Critical Finding: Workflow Executed from MAIN, Not PR Branch

| Metric | Value |
|--------|-------|
| Run ID | 20469129997 |
| Head Branch | **main** (not the PR branch) |
| Head SHA | d491a12bbf16c5b6c1c2f070d7e7fcd4ebb4b2fc |
| PR Branch SHA | a19beadf95d9db46febcc5df0c12fbda26b5b53a |
| Event Type | issues (labeled) |

### Root Cause

**GitHub Actions behavior**: For `issues` events, workflows **always** execute from the default branch (main), regardless of any open PRs.

This is by design - GitHub cannot know which PR branch (if any) should be used for issue events.

### Workflow Condition Comparison

| Branch | Condition in `Post synthesis comment` step |
|--------|-------------------------------------------|
| **main** (d491a12) | `steps.synthesize.outputs.verdict == 'PASS'` |
| **PR branch** (a19bead) | `steps.synthesize.outputs.verdict == 'PASS' \|\| (steps.synthesize.outputs.findings != '' && steps.synthesize.outputs['copilot-exit-code'] == '0')` |

The fix exists in PR #296 but is **not yet merged to main**.

### Run Analysis

From the workflow logs:

```
Stdout length: 2699 chars
Stderr length: 0 chars
##[error]Could not parse verdict from AI output - treating as failure
Verdict: CRITICAL_FAIL
```

- **AI execution**: SUCCESS (exit code 0, 2699 chars output)
- **Verdict parsing**: FAILED (could not find `VERDICT:` token)
- **Post synthesis comment step**: SKIPPED (condition `verdict == 'PASS'` was false)
- **Assign copilot-swe-agent step**: SKIPPED (same condition)

---

## Solution

**The fix is correct. The PR just needs to be merged.**

Once PR #296 is merged to main, the fallback condition will be active for all future `issues` event triggers.

### Verification Steps

1. Merge PR #296 to main
2. Re-apply `copilot-ready` label to Issue #265 (or use workflow_dispatch)
3. Verify synthesis comment is posted

---

## Lessons Learned

### Pattern: Issue Event Workflows Always Run from Default Branch

**Trigger**: Any `issues` event (labeled, opened, etc.)
**Behavior**: Workflow YAML is read from default branch (usually main)
**Implication**: PR changes to issue-triggered workflows only take effect after merge

### Testing Workflow Changes Before Merge

For workflows triggered by non-PR events (issues, schedule, workflow_dispatch without ref override):

1. **Cannot test from PR branch** - the workflow definition from main is always used
2. **Must merge to main first** - or use a different testing strategy
3. **Alternative**: Use `workflow_dispatch` with explicit `ref` parameter to specify branch

---

## Session End Checklist

- [x] Investigation complete
- [x] Root cause identified
- [x] Solution documented
- [ ] Retrospective (not needed - no code changes)
- [ ] HANDOFF.md update (read-only per protocol)
- [ ] Commit session log
