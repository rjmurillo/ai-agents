# Security Review: PR #4247 - Comment Restoration and Skip-Guard Tests

## Scope
- `.github/workflows/pr-validation.yml` - Comment restoration
- `tests/ci/test_pr_validation_workflow.py` - Skip-guard classifier tests

## Key Security Elements Reviewed

### 1. Bot Skip Guard Mechanism
**Location**: `.github/workflows/pr-validation.yml` line 46-53

Skip guard checks GITHUB_ACTOR against excluded bots:
```
$excludedBots = @('dependabot[bot]', 'github-actions[bot]', 'renovate[bot]')
```

The bot-skip guard is the **sole execution control** that prevents validation steps from running for dependency-update PRs.

### 2. Unconditional Security Gates (from pr-validation.yml)

Three security correctness gates are **explicitly marked UNCONDITIONAL** (no bot skip):

1. **Line 283-293: ADR-006 run-block ratchet** - Detects business logic in workflow run blocks
   - Comment states: "Unconditional (Issue #4151): Renovate and Dependabot open workflow-only PRs (action SHA bumps), which are exactly the PRs that could smuggle a new run block past this gate if it were skip-guarded."
   - NO `if:` condition present

2. **Line 261-264: Workflow YAML validation** - Validates workflow schema
   - Comment: "Checkout repository for workflow validation"
   - Checkout only runs when bot-skip guard is TRUE (skip=='true')
   - Validation and uv-setup are UNCONDITIONAL

3. **Line 299-309: Taste-lint error-count ratchet** - Quality debt tracking
   - UNCONDITIONAL

4. **Line 320-325: Type-ignore count ratchet** - MyPy suppression tracking
   - UNCONDITIONAL

5. **Line 326-338: Conflict marker detection** - Catches merge conflict markers
   - UNCONDITIONAL

6. **Line 352-360: Model pin enforcement** - Validates ADR-080 compliance
   - UNCONDITIONAL

### 3. Skip-Guard Classifier Tests

**Location**: `tests/ci/test_pr_validation_workflow.py` lines 825-1050

Class: `TestBotSkipGuardClassification`

**Allowlist of permitted skip-guarded steps** (lines 920-932):
```python
_ALLOWED_BEHIND_GUARD: frozenset[str] = frozenset({
    "Checkout repository",
    "Setup PowerShell",
    "Validate PR Description vs Diff",
    "Validate PR Description Standards",
    "Check QA Report Exists",
    "Generate Validation Report",
    "Post PR Comment",
    "Set Job Summary",
    "Check PR commit count",
    "Enforce Blocking Issues",
})
```

**Key test methods** (all present in the branch):

1. `test_adr006_ratchet_is_unconditional()` - **CRITICAL TEST**
   - Verifies ADR-006 step has no `if:` condition
   - Blocks any attempt to conditionally gate the run-block scanner

2. `test_no_security_gate_is_skip_guarded()` - **CRITICAL TEST**
   - Verifies no new security/correctness gates are hidden behind bot skip
   - Requires new skipped steps to be justified in allowlist with comments

3. `test_all_allowed_guarded_steps_are_present()` - **MAINTENANCE TEST**
   - Removes dead entries from allowlist when steps are deleted
   - Prevents permission creep

4. `test_skip_guard_classifier_detects_compound_conditions()` - **PARSER TEST**
   - Handles compound conditions like: `steps.should-run.outputs.skip != 'true' && github.event_name == 'push'`

5. `test_skip_guard_classifier_rejects_negated_conditions()` - **PARSER TEST**
   - Correctly rejects: `!(steps.should-run.outputs.skip != 'true') && ...`

6. `test_skip_guard_classifier_accepts_wrapped_expression()` - **PARSER TEST**
   - Handles GitHub's `${{ ... }}` expression wrapper syntax

## Threat Model

### Asset: CI/CD Workflow Trust Boundary
- **Attack Surface**: Bot-authored PRs modifying workflow YAML
- **Threat Actors**: Renovate/Dependabot (dependency update service accounts) with legitimate access
- **Impact**: Workflow schema bypass; run-block injection; model-pin violations

### Identified Risk Control
The skip-guard mechanism is a **throughput optimization**, not a security control. It exempts bots from expensive PR-body validation (description, standards, QA checks) because bots don't author human prose.

However, **correctness gates must never be skipped**:
- Workflow schema changes apply to all actors (bots included)
- Run-block injection is a code-execution vector regardless of author
- Model pins are architectural constraints, not documentation

### How Tests Enforce This
1. `test_adr006_ratchet_is_unconditional()` - Ensures the gate that catches run-block injection is never guarded
2. `test_no_security_gate_is_skip_guarded()` - Prevents new security gates from being hidden
3. Compound/negation/wrapper tests - Ensure the classifier can't be tricked into reading `!=true` as `==true`

## Comment Restoration Impact
The comments restored in pr-validation.yml explain WHY each gate is conditional or unconditional:
- Issue #3330: Why workflow validation must be unconditional
- Issue #2967: Why ADR-006 must be unconditional
- Issue #3779: Why taste-lint is unconditional
- Issue #3770: Why conflict-marker detection is unconditional
- Issue #2840: Why model-pin enforcement is unconditional
- Issue #3997: Why commit-count checkout must be unshallow

These comments serve as **in-workflow documentation** of security policy. Without them, a future maintainer might "optimize" an unconditional gate back to skip-guarded form without realizing the correctness implication.

## Baseline Assessment
- **Changes are NON-DESTRUCTIVE**: Comments added, tests added, no behavior change
- **Comments document existing policy**: No new policy introduced
- **Tests enforce existing constraints**: No new constraints added
- **Parser tests prevent regression**: Fixes against misclassification of negated/wrapped conditions
