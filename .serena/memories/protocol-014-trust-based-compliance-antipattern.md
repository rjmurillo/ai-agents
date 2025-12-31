# Skill: protocol-014 - Trust-Based Compliance Antipattern

**Atomicity**: 94%
**Category**: Protocol design, antipattern
**Source**: PR #669 PR co-mingling retrospective

## Antipattern

**Trust-Based Compliance**: Protocol requirements that rely on agent memory/behavior without verification.

**Failure Mode**: Agents forget, context limits cause omission, instructions drift over time.

**Success Rate**: ~0% for non-trivial protocols

## Why It Fails

1. **No persistent memory**: Agents have no memory across tool calls
2. **Context limits**: Long sessions truncate instructions
3. **Unverifiable**: No way to check compliance after the fact
4. **Silent failure**: No observable artifact when requirement skipped

## Replacement Pattern

**Verification-Based Enforcement** (see protocol-013):

Requirements that generate observable artifacts enabling verification.

**Success Indicators**: Tool output in transcript, files on disk, API responses, git history.

**Success Rate**: 90%+ when properly designed

## Examples

### Bad (Trust-Based)

| Requirement | Why It Fails | Evidence |
|-------------|--------------|----------|
| "Agent should verify branch before committing" | No artifact, unverifiable | PR #669: 4 PRs contaminated |
| "Remember to check for existing issues" | Context limit may truncate | Duplicate issues created |
| "Make sure to run tests before pushing" | No blocking enforcement | Tests skipped, CI fails |
| "Keep commits atomic" | Subjective, no verification | Large multi-topic commits |

### Good (Verification-Based)

| Requirement | Observable Artifact | Verifiable By |
|-------------|---------------------|---------------|
| "Run `git branch --show-current` and document in session log" | Tool output, file | grep session log |
| "Use `gh issue list --search` to check for duplicates" | Tool output in transcript | Session log |
| "Run `Invoke-Pester` and commit `TestResult.xml`" | Test report file | Pre-push hook |
| "Max 5 files per commit OR single topic" | Git history | commit-msg hook |

## Case Studies

### Case 1: Branch Verification (PR #669)

**Trust-Based (FAILED)**:

- Requirement: "Verify current branch before committing"
- Artifact: None
- Verification: Impossible
- Compliance: 0% (agents committed to wrong branches)
- Impact: 4 PRs contaminated, ~3 hours remediation

**Verification-Based (EXPECTED SUCCESS)**:

- Requirement: "Run `git branch --show-current` and document output"
- Artifact: Tool output in session log, branch field
- Verification: Validate-SessionEnd.ps1 checks field exists
- Expected compliance: 90%+
- Prevention: Pre-commit hook blocks wrong-branch commits

### Case 2: Test Execution

**Trust-Based (LOW COMPLIANCE)**:

- Requirement: "Run tests before pushing"
- Artifact: None
- Compliance: ~20% (skipped under token pressure)
- Impact: Broken commits, CI failures

**Verification-Based (HIGH COMPLIANCE)**:

- Requirement: "Run `Invoke-Pester`, commit `TestResult.xml`"
- Artifact: Test report file
- Verification: Pre-push hook checks file exists, 0 failures
- Expected compliance: 95%+
- Prevention: Push blocked if tests missing/failing

## Detection

Protocol requirement is trust-based if:

1. ✗ Uses "should", "remember", "make sure"
2. ✗ No observable artifact generated
3. ✗ Cannot verify compliance programmatically
4. ✗ Silent failure (no error when skipped)
5. ✗ Relies on agent memory

Protocol requirement is verification-based if:

1. ✓ Specifies exact command to run
2. ✓ Generates observable artifact (file, output, commit)
3. ✓ Verification can be automated
4. ✓ Failure is detectable (missing artifact)
5. ✓ Blocking (next step depends on artifact)

## Remediation

When you find a trust-based requirement:

1. **Identify the intent**: What behavior is the requirement trying to enforce?
2. **Design an artifact**: What observable output proves compliance?
3. **Add verification**: How can we check the artifact exists/is valid?
4. **Make it blocking**: Prevent next step if artifact missing

### Template

```markdown
## Phase N: [Action] (BLOCKING)

Before [next step], perform [action]:

```bash
[command that generates observable output]
```

**Exit criteria**: [Artifact] exists and [validation check] passes.
**Verification**: [How to check compliance]

```

## Evidence

### PR #669: Branch Verification Failure

**Trust-based requirement** (from implied protocol):
- "Verify current branch before committing"
- No artifact generated
- No verification possible

**Outcome**:
- 4 PRs received wrong commits (PRs #562-565)
- Remediation: ~3 hours cherry-picking ~15 commits
- Merge queue delay: ~12 hours
- Root cause: Trust-based compliance with 0% success rate

**Lesson**: If you can't verify compliance, assume 0% compliance.

## Related Skills

- protocol-013: Verification-based enforcement (replacement pattern)
- session-init-003: Branch declaration requirement (verification-based)
- git-004: Branch verification before commit (verification-based)
- protocol-blocking-gates: Blocking gate pattern

## References

- PR #669: PR co-mingling retrospective
- Issue #684: SESSION-PROTOCOL branch verification (verification-based redesign)
- Issue #686: Document trust antipattern (this skill)
- ADR-XXX: Protocol design principles (to be created)
