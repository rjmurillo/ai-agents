# ADR-006: Thin Workflows, Testable Modules

**Status**: Accepted
**Date**: 2025-12-18
**Deciders**: User, High-Level-Advisor Agent
**Context**: [PR #60](https://github.com/rjmurillo/ai-agents/pull/60) AI workflow implementation
**Related**: [ADR-005](./ADR-005-powershell-only-scripting.md) (PowerShell-Only Scripting), [PR #60 Remediation Plan](../planning/PR-60/002-pr-60-remediation-plan.md)

---

## Context and Problem Statement

GitHub Actions workflows cannot be tested locally. The feedback loop is:

1. Edit workflow YAML
2. Commit and push
3. Wait for CI to run (1-5 minutes)
4. Check results
5. If failed, repeat from step 1

This **slow OODA loop** makes workflow debugging painful and time-consuming.

**Key Question**: How should we structure workflows to enable fast local testing?

---

## Decision Drivers

1. **Testing Gap**: Workflows can't be tested with Pester locally
2. **Slow Feedback**: 1-5 minute wait per iteration vs seconds for local tests
3. **Business Logic**: Complex parsing, validation, and formatting logic needs testing
4. **DRY Principle**: Logic duplicated across workflows is error-prone
5. **Maintainability**: Bugs in workflows require slow fix-test-deploy cycle
6. **Developer Experience**: Frustration with slow feedback loop

---

## Considered Options

### Option 1: Thin Workflows, Testable Modules (CHOSEN)

**Workflows orchestrate only; all logic in PowerShell modules**

**Architecture**:
```
Workflow (YAML) - Orchestration only
  ↓ calls
PowerShell Module (.psm1) - Business logic
  ↓ tested by
Pester Tests (.Tests.ps1) - Fast local feedback
```

**Pros**:
- ✅ Fast OODA loop: Edit module → Run Pester → Get feedback (seconds)
- ✅ Full test coverage for business logic
- ✅ DRY: Reusable modules across workflows
- ✅ Debugging: Can debug PowerShell locally with breakpoints
- ✅ Separation of concerns: Orchestration vs logic

**Cons**:
- ❌ More files to maintain (module + tests)
- ❌ Requires discipline to keep workflows thin

### Option 2: All Logic in Workflows

**Put business logic directly in workflow YAML `run:` blocks**

**Pros**:
- ✅ Fewer files (everything in YAML)
- ✅ No module/workflow boundary to maintain

**Cons**:
- ❌ Slow OODA loop: Must push to test
- ❌ No local testing possible
- ❌ Logic duplication across workflows
- ❌ Difficult to debug (no breakpoints, limited logging)
- ❌ YAML is poor language for complex logic

### Option 3: Hybrid (Simple Logic in Workflows)

**Simple logic in workflows, complex logic in modules**

**Pros**:
- ✅ Flexibility for one-liners

**Cons**:
- ❌ Ambiguous boundary: What's "simple" vs "complex"?
- ❌ "Simple" logic often becomes complex over time
- ❌ Still have slow OODA loop for workflow changes
- ❌ Inconsistent: Some workflows thin, others fat

---

## Decision Outcome

**Chosen option: Option 1 - Thin Workflows, Testable Modules**

### Rationale

1. **Empirical Evidence**: PR #60 workflows initially had logic in YAML. Debugging required 5+ push-wait-check cycles. After extracting to modules, bugs fixed locally in minutes.

2. **Testability**: Business logic (verdict parsing, label extraction, formatting) requires tests. Pester tests caught 6+ bugs before CI.

3. **DRY**: 4 workflows share comment posting logic. Single module ([`AIReviewCommon.psm1`](../../.github/scripts/AIReviewCommon.psm1)) serves all 4.

4. **Speed**: Local Pester runs in ~2 seconds. CI runs in ~3 minutes. 90x faster feedback loop.

5. **Maintainability**: Logic changes require module edit + Pester test, not workflow edit + push + wait.

### Implementation Rules

#### Workflows (YAML)

**DO**:
- Orchestrate: Call scripts, pass parameters, handle success/failure
- Set environment variables for modules to consume
- Handle artifacts (upload/download)
- Manage concurrency, timeouts, triggers

**DON'T**:
- Parse complex strings (verdict, labels, etc.) - delegate to module
- Validate business rules - delegate to module
- Format output - delegate to module
- Duplicate logic from other workflows - use shared module

**Maximum workflow size**: 100 lines (orchestration only)

#### Modules (.psm1)

**DO**:
- Contain ALL business logic
- Be pure functions where possible (input → output, no side effects)
- Have comprehensive Pester tests (80%+ coverage)
- Use meaningful function names (verb-noun format)
- Export only public functions

**DON'T**:
- Directly call GitHub CLI (`gh`) - use `.claude/skills/github/` wrappers
- Depend on workflow environment variables where avoidable (pass as parameters)
- Duplicate functionality from Claude skills

**Test coverage requirement**: 80% for all exported functions

#### Example Pattern

**BAD** (Logic in workflow):
```yaml
- name: Parse verdict
  shell: bash
  run: |
    # 20 lines of complex bash parsing
    VERDICT=$(echo "$OUTPUT" | grep -oP '(?<=VERDICT:\s*)[A-Z_]+')
    if [ -z "$VERDICT" ]; then
      # 10 lines of fallback parsing
    fi
    if [ "$VERDICT" = "CRITICAL_FAIL" ]; then
      exit 1
    fi
```

**Problem**: 30 lines of untestable bash. Must push to test.

**GOOD** (Logic in module):
```yaml
- name: Parse verdict
  shell: pwsh
  run: |
    Import-Module .github/scripts/AIReviewCommon.psm1
    $result = Get-VerdictFromOutput -Output $env:AI_OUTPUT
    if ($result.Verdict -eq 'CRITICAL_FAIL') {
      exit 1
    }
```

**Benefit**: `Get-VerdictFromOutput` has Pester tests. Edit → Test locally → Deploy.

---

## Consequences

### Positive

1. **Fast Feedback**: Seconds vs minutes for testing changes
2. **Higher Quality**: Bugs caught by Pester before CI
3. **Maintainability**: Logic changes don't require workflow edits
4. **Reusability**: Modules shared across workflows
5. **Debuggability**: Can set breakpoints in PowerShell
6. **Confidence**: 80%+ test coverage provides safety net

### Negative

1. **More Files**: Each workflow needs companion module + tests
   - **Mitigation**: Modules are reusable across workflows
2. **Learning Curve**: Developers must understand module boundary
   - **Mitigation**: Clear rules in this ADR
3. **Initial Effort**: Extracting logic to modules takes time
   - **Mitigation**: Faster iteration pays back quickly

### Neutral

1. **Existing Workflows**: Some existing workflows have logic in YAML
   - **Action**: Refactor when touching those workflows
   - **No** retroactive refactoring required unless workflow needs changes

---

## Validation Checklist

Before merging workflow changes:

- [ ] Workflow YAML < 100 lines
- [ ] No complex parsing/formatting in YAML `run:` blocks
- [ ] Business logic extracted to `.psm1` module
- [ ] Module has Pester tests (`.Tests.ps1`)
- [ ] Tests achieve 80%+ coverage
- [ ] Tests can run locally: `pwsh ./build/scripts/Invoke-PesterTests.ps1`
- [ ] Module functions use verb-noun naming
- [ ] GitHub operations use `.claude/skills/github/` (not direct `gh` calls)

---

## Related Decisions

- [ADR-005: PowerShell-Only Scripting](./ADR-005-powershell-only-scripting.md) (all modules must be PowerShell)
- **Pattern**: `pattern-thin-workflows` memory (use `mcp__serena__read_memory` with `memory_file_name="pattern-thin-workflows"`) - detailed pattern documentation
- **Skill**: [`.claude/skills/github/`](../../.claude/skills/github/) (reusable GitHub operations)

---

## References

- [PR #60](https://github.com/rjmurillo/ai-agents/pull/60): Workflows refactored from bash-in-YAML to PowerShell modules
- [`.github/scripts/AIReviewCommon.psm1`](../../.github/scripts/AIReviewCommon.psm1): 708 lines, 93 Pester tests
- [`.github/scripts/AIReviewCommon.Tests.ps1`](../../.github/scripts/AIReviewCommon.Tests.ps1): Comprehensive test suite
- [Session log](../sessions/2025-12-18-session-15-pr-60-response.md): `.agents/sessions/2025-12-18-session-15-pr-60-response.md`

---

## Migration Strategy

For existing workflows with embedded logic:

1. **No Forced Refactoring**: Don't refactor working workflows unless changing them
2. **On Touch**: When modifying a workflow, extract logic to module at that time
3. **Gradual**: Refactor one workflow at a time as needed
4. **Test First**: Create Pester tests for extracted logic before changing workflow

---

**Supersedes**: None (new decision)
**Amended by**: None
