# Documentation Skills

**Created**: 2025-12-20
**Sources**: Various retrospectives and PR reviews

## Skill-Documentation-005: User-Facing Content Restrictions

**Statement**: Exclude internal PR/Issue/Session references from src/ and templates/ directories

**Context**: When creating or updating user-facing documentation

**Evidence**: PR #212 - User policy request, 6 files updated to remove internal references

**Atomicity**: 92%

**Tag**: critical (user experience)

**Impact**: 9/10 (maintains professional external documentation)

**Created**: 2025-12-20

**Scope**:

This policy applies to all files distributed to end-users:

- `src/claude/` - Claude agent definitions
- `src/copilot-cli/` - Copilot CLI agent definitions
- `src/vs-code-agents/` - VS Code agent definitions
- `templates/agents/` - Agent templates

**Prohibited Content**:

### 1. Internal PR References

- **Prohibited**: `PR #60`, `PR #211`, `PR #212`, or any internal PR numbers
- **Rationale**: End-users do not know or care about issues internal to our repository
- **Alternative**: Describe the pattern generically without referencing specific internal PRs

**Example Fix:**

```markdown
<!-- WRONG -->
Security issues can cause critical damage; CWE-20/CWE-78 introduced in PR #60 went undetected until PR #211

<!-- CORRECT -->
Security issues can cause critical damage if missed during review
```

### 2. Internal Issue References

- **Prohibited**: `Issue #16`, `Issue #183`, or any internal issue numbers
- **Rationale**: Same as above - internal tracking is meaningless to users

### 3. Session References

- **Prohibited**: `Session 44`, `Session 15`, or any session identifiers
- **Rationale**: These are internal implementation details

### 4. Internal File Paths

- **Prohibited**: References to `.agents/`, `.serena/`, or other internal directories
- **Rationale**: Users may not have the same directory structure

**Permitted Content**:

- Generic descriptions of patterns and behaviors
- Security vulnerability identifiers (CWE-20, CWE-78, etc.) - these are public standards
- Best practice recommendations without internal context
- Public references (RFC numbers, standard specifications)

**Validation**:

Before committing changes to user-facing directories, verify no internal references are present.

**Pattern**:

```bash
# Scan for internal references before commit
grep -r "PR #\|Issue #\|Session \d\+\|\.agents/\|\.serena/" src/ templates/
# Should return no matches in user-facing files
```

**Anti-Pattern**:

Including internal tracking numbers or file paths in templates that users will copy.

**Validation**: 1 (PR #212, 6 files updated)

**Related Memory**: `user-facing-content-restrictions` (policy reference)

---

## Application Checklist

When creating/updating user-facing documentation:

1. [ ] Remove all `PR #XXX` references
2. [ ] Remove all `Issue #XXX` references
3. [ ] Remove all `Session XX` references
4. [ ] Remove all `.agents/` and `.serena/` path references
5. [ ] Replace specific examples with generic patterns
6. [ ] Keep public standard references (CWE, RFC, etc.)
7. [ ] Verify no internal tracking numbers remain

---

## Skill-Documentation-006: Self-Contained Operational Prompts

**Statement**: When creating prompts for autonomous operation, include all resource constraints, failure modes, shared resource context, and dynamic adjustment rules that the executing agent will need.

**Context**: Prompts intended for standalone Claude instances or autonomous agents

**Evidence**: PR #301 - Rate limit guidance was missing from autonomous-pr-monitor.md. User had to point out that rjmurillo-bot is used for MANY operations and the prompt needed sustainability guidance.

**Atomicity**: 88%

**Tag**: operational (autonomous agents)

**Impact**: 9/10 (prevents resource exhaustion, enables sustainable operation)

**Created**: 2025-12-23

**The Problem**:

Prompts written by an agent during a session often contain implicit knowledge that the agent uses but doesn't document. When another agent (or the same agent in a new session) uses the prompt, they lack this context and may:

- Exhaust shared resources (API limits, rate limits)
- Miss failure modes the original author handled dynamically
- Not understand system-wide constraints

**Required Sections for Operational Prompts**:

### 1. Resource Constraints

```markdown
RESOURCE CONSTRAINTS:
- **API Rate Limits**: MUST check before each cycle, MUST NOT exceed X%
- **Shared Resources**: This bot account is also used by [list other systems]
- **Budget**: Target X% usage to leave room for other operations
```

### 2. Failure Modes & Recovery

```markdown
FAILURE MODES:
| Failure | Detection | Recovery |
|---------|-----------|----------|
| Rate limit exceeded | 429 response or >80% used | Pause until reset |
| Network timeout | Command hangs >30s | Retry with backoff |
| Authentication failure | 401 response | Alert and stop |
```

### 3. Dynamic Adjustment Rules

```markdown
DYNAMIC ADJUSTMENTS:
| Condition | Action |
|-----------|--------|
| Rate limit 0-50% | Normal operation (120s cycles) |
| Rate limit 50-70% | Reduced frequency (300s cycles) |
| Rate limit >70% | Minimal operation (600s cycles) |
```

### 4. Shared Context

```markdown
SHARED CONTEXT:
- This bot account (rjmurillo-bot) is used by:
  - GitHub Actions workflows (CI/CD)
  - PR review automation
  - Issue triage automation
  - This monitoring process
- Your API usage affects ALL of these systems
```

### 5. Self-Termination Conditions

```markdown
STOP CONDITIONS:
1. Explicit user instruction to stop
2. Resource constraint violation (>80% rate limit)
3. Critical error preventing further operation
4. [Any domain-specific conditions]
```

**Validation Questions**:

Before finalizing an operational prompt, ask:

1. "If I had amnesia and only had this document, could I operate correctly?"
2. "What do I know that the next agent won't?"
3. "What implicit decisions am I making that should be explicit?"
4. "What resources am I consuming? Who else uses them?"
5. "What happens if this runs forever? Is it sustainable?"

**Anti-Pattern**:

```markdown
# BAD: Implicit knowledge, no constraints
Run continuously, checking PRs every 120 seconds for up to 8 hours.
```

**Pattern**:

```markdown
# GOOD: Explicit constraints, shared context, sustainability
Run continuously with dynamic cycle intervals (120-600s based on rate limits).
MUST check rate limit before each cycle.
MUST NOT exceed 80% of API limit (rjmurillo-bot serves many systems).
SHOULD stay under 50% during normal operation.
```

**Validation**: 1 (PR #301, user steering required to add rate limit guidance)

---

## Related Skills

- Skill-Documentation-001: Systematic migration search
- Skill-Documentation-002: Reference type taxonomy
- Skill-Documentation-003: Fallback preservation
- Skill-Documentation-004: Pattern consistency
- Skill-Documentation-005: User-facing content restrictions
- Skill-Documentation-006: Self-contained operational prompts

## References

- PR #212: User policy creation
- Memory: `user-facing-content-restrictions`
