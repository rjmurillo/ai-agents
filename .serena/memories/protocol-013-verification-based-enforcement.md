# Skill: protocol-013 - Verification-Based Enforcement

**Atomicity**: 88%
**Category**: Protocol design, compliance
**Source**: PR #669 PR co-mingling retrospective

## Pattern

Protocol requirements MUST generate observable artifacts that can be verified, not rely on agent memory.

## Problem

**Trust-Based Compliance** fails because:

- Agents have no persistent memory across tool calls
- Context limits cause instruction truncation
- No way to verify compliance after the fact

**Success rate**: ~0% for non-trivial protocols

## Solution

**Verification-Based Enforcement**: Requirements that generate observable artifacts.

### Design Criteria

For each protocol requirement, ask:

1. **Observable?** Does it generate an artifact (file, output, commit)?
2. **Verifiable?** Can compliance be checked after the fact?
3. **Blocking?** Does the next step depend on this artifact?

If "no" to any question, redesign with verification.

### Examples

**Bad (trust-based)**:

- "Agent should verify branch before committing"
- "Remember to check for existing issues"
- "Make sure to run tests before pushing"

**Good (verification-based)**:

- "Run `git branch --show-current` and document output in session log" (artifact: file)
- "Use `gh issue list` to search" (artifact: tool output in transcript)
- "Run tests with `Invoke-Pester` and include results" (artifact: test report)

## Implementation

### Session Protocol Pattern

```markdown
## Phase N: [Action Name] (BLOCKING)

Before [next step], perform [action]:

```bash
[command that generates observable output]
```

**Exit criteria**: [Artifact] exists and contains [expected content].

```

### Validation Pattern

```powershell
# Validate-SessionEnd.ps1
function Test-ProtocolCompliance {
    param([string]$SessionLogPath)
    
    $log = Get-Content $SessionLogPath -Raw
    
    # Check for required artifacts
    if ($log -notmatch 'git branch --show-current') {
        Write-Error "Missing branch verification output"
        return $false
    }
    
    return $true
}
```

## Case Studies

### Case 1: Branch Verification (PR #669)

**Original (trust-based)**: "Verify current branch before committing"

- Compliance: 0% (agents committed to wrong branches)
- Impact: 4 PRs contaminated, 3 hours remediation

**Redesign (verification-based)**:

- Phase 1.0: "Run `git branch --show-current` and document in session log"
- Phase 8.0: "Verify `git branch --show-current` matches session log before commit"

**Expected compliance**: 90%+ (tool output required, pre-commit hook validates)

### Case 2: Test Execution

**Original (trust-based)**: "Run tests before pushing"

- Compliance: ~20% (agents skip when under token pressure)

**Redesign (verification-based)**:

- "Run `Invoke-Pester` and include `TestResult.xml` in commit"
- Pre-push hook: Verify `TestResult.xml` exists and has 0 failures

**Expected compliance**: 95%+ (artifact required, hook enforces)

## Evidence

**PR #669**: Trust-based "verify branch" requirement

- 4 PRs received wrong commits
- No verification artifacts in session logs
- Remediation required cherry-picking ~15 commits

**Contrast**: Verification-based requirements (e.g., "tool output MUST appear in transcript")

- High compliance (90%+ in practice)
- Failures detectable immediately
- Audit trail in session logs

## Related Skills

- protocol-014: Trust-based compliance antipattern
- session-init-003: Branch declaration requirement
- git-004: Branch verification before commit
- protocol-blocking-gates: Blocking gate pattern

## Design Checklist

Use this checklist when designing new protocol requirements:

1. [ ] Requirement generates observable artifact (file, output, API response)
2. [ ] Artifact can be verified programmatically (not just "agent should")
3. [ ] Next step blocked until artifact verified
4. [ ] Failure mode is detectable (missing artifact, wrong content)
5. [ ] Audit trail exists (session log, git history, file system)

## Anti-Patterns to Avoid

| Bad (trust-based) | Good (verification-based) |
|-------------------|---------------------------|
| "Agent should..." | "Run [command] and verify output" |
| "Remember to..." | "Generate [artifact] before proceeding" |
| "Make sure..." | "Tool output MUST appear in transcript" |
| No artifact | File, output, commit, API response |
| Unverifiable | Programmatically checkable |

## References

- PR #669: PR co-mingling retrospective
- Issue #684: SESSION-PROTOCOL branch verification (verification-based)
- Issue #686: Trust antipattern documentation
- ADR-XXX: Protocol design principles (to be created)
