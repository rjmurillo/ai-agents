---
description: Run QA verification on implementation results. Validates acceptance criteria, test coverage, and quality standards.
argument-hint: <verification scope>
model: sonnet
---

# /3-qa - Quality Assurance

Validate that implementation meets acceptance criteria, test coverage targets, and quality standards. Routes to the **qa** agent.

## Actions

1. **Review implementation** - Examine changed files from `/2-impl`
2. **Validate acceptance criteria** - Check each criterion from the plan
3. **Verify test coverage** - Ensure new/changed code has adequate tests
4. **Run existing tests** - Execute test suite, report failures
5. **Generate QA report** - Structured pass/fail with evidence

## Agent Routing

Routes to **qa** (Tier 3: Builder). For complex QA requiring design review, escalates to **critic** (Tier 2: Manager).

Maps to Agent Orchestration MCP (ADR-013): `invoke_agent("qa", ...)`, `track_handoff()`. Fallback: `Task(subagent_type="qa", prompt=...)`.

## QA Checklist

| Check | Required | Description |
|-------|----------|-------------|
| Acceptance criteria met | MUST | Each criterion from plan passes |
| Tests pass | MUST | All existing tests remain green |
| New tests added | SHOULD | Changed code has corresponding tests |
| Edge cases covered | SHOULD | Boundary conditions tested |
| No regressions | MUST | Existing functionality unaffected |
| Code quality | RECOMMENDED | Lint clean, no warnings introduced |

## Output

- **QA Report** - Pass/fail per acceptance criterion
- **Test Results** - Suite execution summary
- **Coverage Delta** - Test coverage change from implementation
- **Issues Found** - List of defects or concerns, if any
- **Recommendation** - Proceed to `/4-security` or return to `/2-impl` for fixes

## Sequence Position

```text
/0-init → /1-plan → /2-impl → ▶ /3-qa → /4-security → /9-sync
```

## Prerequisites

Requires implementation from `/2-impl`.

## Examples

```text
/3-qa Verify the authentication implementation meets acceptance criteria
/3-qa Run full test suite and report coverage for the caching changes
```
