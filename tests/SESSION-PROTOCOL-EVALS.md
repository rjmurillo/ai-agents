# Session Protocol Compliance Evaluation Suite

Behavior-based evaluation suite for session protocol compliance, built per
[Vercel methodology](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals).

**Issue**: #1106

## Design Principles

1. **Target novel behaviors**: Tests verify session protocol steps absent from
   standard agent training data (Serena activation, HANDOFF.md read-only,
   MUST NOT inverted semantics).

2. **Behavior-based assertions**: Tests verify what happens, not how.
   - Correct: "Session log with incomplete Serena activation fails validation"
   - Wrong: "SessionLogger.ValidateSerena() returns false"

3. **No duplication**: Does not repeat `Validate-SessionJson.ps1` structural
   tests. Instead tests behavioral invariants the validator enforces.

## Running the Suite

```bash
# Run all evals
pwsh -NoProfile -Command "Invoke-Pester -Path tests/SessionProtocolCompliance.Tests.ps1 -Output Detailed"

# Run a specific category
pwsh -NoProfile -Command "Invoke-Pester -Path tests/SessionProtocolCompliance.Tests.ps1 -Tag SessionStart -Output Detailed"

# Run with pass/fail exit code only (CI mode)
pwsh -NoProfile -Command "Invoke-Pester -Path tests/SessionProtocolCompliance.Tests.ps1 -Output Minimal"
```

Exit code 0 = all evals pass. Non-zero = at least one violation detected.

## Eval Categories

| Category | Tag | Tests | What It Verifies |
|----------|-----|-------|------------------|
| Serena Activation | `SessionStart` | 3 | Two-step Serena init is a blocking gate |
| HANDOFF.md Read-Only | `SessionEnd` | 3 | HANDOFF.md modification is detected and rejected |
| Branch Verification | `GitSafety` | 3 | Branch must be verified before git operations |
| Schema Compliance | `Schema` | 4 | Session number matching, SHA format enforcement |
| Memory-First Pattern | `MemoryFirst` | 5 | Memory loading requirements and infrastructure |
| QA Routing | `QARouting` | 5 | QA gate for features, investigation-only allowlist |
| Session End Completeness | `SessionEnd` | 5 | All 6 MUST items at session end are enforced |
| MUST NOT Semantics | `Semantics` | 2 | Inverted completion logic for prohibited actions |
| Session Uniqueness | `Uniqueness` | 1 | Duplicate session numbers are rejected (CWE-362) |
| Skill Infrastructure | `SkillGate` | 3 | Skill scripts and usage-mandatory memory exist |
| Evidence Quality | `Evidence` | 2 | Empty evidence on MUST items produces warnings |

### Total: 36 eval test cases

## CI Integration

The eval suite runs within the existing Pester CI workflow
(`.github/workflows/pester-tests.yml`). Tests are in `tests/` and follow the
`*.Tests.ps1` naming convention, so they are automatically discovered.

No additional CI configuration is required.

## Pass vs Fail Examples

**Passing behavior**: A session log with all MUST items complete, evidence
fields populated, HANDOFF.md untouched, and valid session number/SHA format.

**Failing behavior**: Any of these triggers a failure:

- Serena activation incomplete (exit code 1)
- HANDOFF.md modified during session (MUST NOT violation)
- Branch not verified before work
- Session number mismatch between filename and JSON
- Missing session end checklist items
- Duplicate session numbers in the same directory

## Relationship to Existing Tests

| File | Purpose | Overlap |
|------|---------|---------|
| `Validate-SessionJson.Tests.ps1` | Structural validation of the validator script | None: tests the validator's internal logic |
| `SessionProtocolCompliance.Tests.ps1` | Behavioral protocol compliance | None: tests protocol invariants via the validator |
| `Invoke-SessionStartGate.Tests.ps1` | Gate script execution and parameters | None: tests the gate script, not session logs |
| `Invoke-SessionLogGuard.Tests.ps1` | Pre-commit hook behavior | None: tests the hook, not session log content |
