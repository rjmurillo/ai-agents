# Protocol Design Antipatterns

> **Status**: Canonical Source of Truth
> **Last Updated**: 2025-12-31
> **RFC 2119**: This document uses RFC 2119 key words.

This document catalogs protocol design antipatterns observed in AI agent systems and provides replacement patterns with evidence of their effectiveness.

---

## Antipattern: Trust-Based Compliance

### Description

Protocol requirements that rely on agent memory or behavior without external verification.

**Failure Mode**: Agents forget, context limits cause omission, instructions drift over time.

**Success Rate**: ~0% for non-trivial protocols across extended sessions.

### Examples of Trust-Based Compliance

| Pattern | Why It Fails |
|---------|--------------|
| "Agent MUST check current branch before operations" | Agent forgets; no enforcement mechanism |
| "Agent SHOULD verify PR state before commenting" | Instruction buried in context; omitted under load |
| "Agent MUST NOT update HANDOFF.md" | Works initially; fails as context grows |
| "Remember to run tests after changes" | Memory-dependent; no verification |

### Why Trust-Based Compliance Fails

1. **Context Limits**: As conversations grow, earlier instructions are summarized or dropped
2. **Instruction Drift**: Agents interpret "should" as optional over time
3. **No Feedback Loop**: Agent receives no signal that compliance was missed
4. **Competing Priorities**: When under pressure, agents skip "soft" requirements
5. **Cross-Session Loss**: Each new session starts without prior session memory

### Evidence

**PR #669 Analysis** (2025-12-30):

- 5 PRs commented on wrong branches despite explicit instructions
- Branch verification instructions present in CLAUDE.md and session protocol
- Failure rate: 100% when relying on agent memory alone
- Root cause: Trust-based compliance pattern

---

## Pattern: Verification-Based Enforcement

### Description

Protocol requirements that generate observable artifacts that can be verified by tools, hooks, or CI.

**Success Indicators**: Tool output in transcript, files on disk, API responses, git history.

**Success Rate**: 90%+ when properly designed with blocking enforcement.

### Examples of Verification-Based Enforcement

| Requirement | Verification Method | Blocking? |
|-------------|---------------------|-----------|
| Session initialization | Tool output MUST appear in transcript | Yes |
| Branch verification | Pre-commit hook checks current branch | Yes |
| QA validation | Validate-Session.ps1 checks session log | Yes |
| Skill usage | CI workflow detects raw `gh` calls | Yes |
| Test execution | CI fails without test results | Yes |

### Design Principles

1. **Observable**: Requirement produces artifact that can be inspected
2. **Verifiable**: Automated tool can check compliance
3. **Blocking**: Workflow cannot proceed without verification
4. **Immediate**: Feedback provided at point of violation

### Implementation Checklist

When designing a new protocol requirement:

- [ ] What artifact proves compliance? (file, API response, tool output)
- [ ] What tool verifies the artifact exists/is correct?
- [ ] Does verification block the workflow on failure?
- [ ] Is feedback immediate and actionable?
- [ ] Does verification work across sessions?

---

## Case Studies

### Case Study 1: Branch Verification (PR #669)

**Context**: Agent must verify current branch before GitHub operations.

**Trust-Based Approach (Failed)**:

```markdown
## CLAUDE.md Instruction
Before ANY mutating git or GitHub operation, you MUST verify the current branch.
```

**Result**: 5 PRs commented on wrong branches. Agent "forgot" to check.

**Verification-Based Approach (Succeeded)**:

```powershell
# Pre-commit hook: .githooks/pre-commit
$currentBranch = git branch --show-current
if ($currentBranch -ne $expectedBranch) {
    Write-Error "E_WRONG_BRANCH: Expected $expectedBranch, got $currentBranch"
    exit 1
}
```

**Result**: Hook blocks commits to wrong branch. Zero violations since implementation.

### Case Study 2: Session Initialization

**Context**: Agent must initialize Serena MCP at session start.

**Trust-Based Approach (Failed)**:

```markdown
## CLAUDE.md Instruction
At session start, you SHOULD call mcp__serena__activate_project.
```

**Result**: Agents skipped initialization when eager to respond to user.

**Verification-Based Approach (Succeeded)**:

```markdown
## SESSION-PROTOCOL.md
| Req | Step | Verification |
|-----|------|--------------|
| MUST | `mcp__serena__activate_project` | Tool output in transcript |
```

**Result**: Session validation script checks for tool output. Violations detected and reported.

### Case Study 3: Test Execution

**Context**: Code changes must have passing tests.

**Trust-Based Approach (Failed)**:

```markdown
Remember to run tests after making changes.
```

**Result**: Agents frequently skipped tests when "confident" in changes.

**Verification-Based Approach (Succeeded)**:

```yaml
# CI Workflow
- name: Run Tests
  run: pwsh -Command "Invoke-Pester -CI"
- name: Block Merge
  if: failure()
  run: exit 1
```

**Result**: CI blocks merge without passing tests. Zero test-skip violations.

---

## Design Guidelines

### When to Use Verification-Based Enforcement

| Scenario | Recommendation |
|----------|----------------|
| Critical path (commits, PRs, merges) | MUST use verification-based |
| Security-sensitive operations | MUST use verification-based |
| Cross-session requirements | MUST use verification-based |
| Documentation/style | MAY use trust-based (low risk) |
| Suggestions/recommendations | MAY use trust-based |

### Verification Hierarchy

| Level | Mechanism | Blocking | Use Case |
|-------|-----------|----------|----------|
| 1 | Pre-commit hook | Yes | Branch verification, linting |
| 2 | CI workflow | Yes | Tests, security scans |
| 3 | PR checks | Yes | Required reviewers, status checks |
| 4 | Session validation | Soft | Protocol compliance |
| 5 | Agent instruction | No | Suggestions, best practices |

### Red Flags in Protocol Design

These patterns indicate trust-based compliance that will likely fail:

- "Agent MUST remember to..."
- "Before X, always check Y"
- "SHOULD verify state before..."
- "Don't forget to..."
- Requirements without observable artifacts

---

## References

- PR #669: Branch verification root cause analysis
- Issue #684: Branch verification protocol
- ADR-034: Investigation session QA exemption (verification-based design)
- SESSION-PROTOCOL.md: Verification-based session requirements

---

Reference: Issue #686
