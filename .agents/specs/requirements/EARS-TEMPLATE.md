# EARS Requirements Template

## Overview

EARS (Easy Approach to Requirements Syntax) provides structured patterns for writing clear, testable, and unambiguous requirements. EARS was developed by Alistair Mavin and colleagues at Rolls-Royce PLC.

This template provides patterns and examples for all five EARS categories plus complex requirements.

## Requirement File Structure

All requirements use this YAML front matter:

```yaml
---
type: requirement
id: REQ-NNN
category: ubiquitous | event-driven | state-driven | unwanted-behavior | optional-feature | complex
status: draft | review | approved | implemented
priority: P0 | P1 | P2
epic: EPIC-NNN (optional)
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

## Category 1: Ubiquitous Requirements

**Use when**: The requirement is always active, regardless of external events or states.

**Pattern**: No EARS keyword needed.

```text
THE <system> SHALL <system response>
```

### Example: Mass Constraint

```markdown
---
type: requirement
id: REQ-U01
category: ubiquitous
status: approved
priority: P1
created: 2026-02-21
---

# REQ-U01: Agent Response Length

## Requirement Statement

THE agent system SHALL limit response length to 4000 tokens maximum.

## Rationale

Prevents context window overflow and ensures responses remain focused.

## Acceptance Criteria

- [ ] All agent responses ≤ 4000 tokens
- [ ] Token counter validates output before delivery
- [ ] Truncation logs a warning when triggered
```

### Example: Security Constraint

```markdown
---
type: requirement
id: REQ-U02
category: ubiquitous
status: approved
priority: P0
created: 2026-02-21
---

# REQ-U02: Credential Handling

## Requirement Statement

THE system SHALL never log credentials, API keys, or secrets in plaintext.

## Rationale

Prevents credential exposure in logs, audit trails, and error messages.

## Acceptance Criteria

- [ ] Secret detection runs on all log output
- [ ] API keys masked with `***` in all contexts
- [ ] Security scan passes without credential warnings
```

## Category 2: Event-Driven Requirements

**Use when**: A specific event triggers the requirement.

**Pattern**:

```text
WHEN <trigger>
THE <system> SHALL <system response>
```

### Example: User Action

```markdown
---
type: requirement
id: REQ-E01
category: event-driven
status: approved
priority: P1
created: 2026-02-21
---

# REQ-E01: Session Initialization

## Requirement Statement

WHEN the user starts a new session
THE agent system SHALL read the HANDOFF.md file and query relevant Serena memories.

## Rationale

Ensures agents have context from previous sessions before starting work.

## Acceptance Criteria

- [ ] HANDOFF.md content loaded into context
- [ ] Relevant memories retrieved from Serena
- [ ] Session log created with timestamp
```

### Example: External Event

```markdown
---
type: requirement
id: REQ-E02
category: event-driven
status: approved
priority: P0
created: 2026-02-21
---

# REQ-E02: PR Comment Notification

## Requirement Statement

WHEN a new review comment is added to a pull request
THE pr-comment-responder agent SHALL acknowledge the comment within the current session.

## Rationale

Ensures reviewer feedback is tracked and addressed promptly.

## Acceptance Criteria

- [ ] Comment detected via GitHub API
- [ ] Eyes reaction added as acknowledgment
- [ ] Comment logged in session log
```

## Category 3: State-Driven Requirements

**Use when**: The requirement is active while a specific state persists.

**Pattern**:

```text
WHILE <in a state>
THE <system> SHALL <system response>
```

### Example: Mode-Based Behavior

```markdown
---
type: requirement
id: REQ-S01
category: state-driven
status: approved
priority: P1
created: 2026-02-21
---

# REQ-S01: Plan Mode Restrictions

## Requirement Statement

WHILE the agent is in plan mode
THE system SHALL prevent file modifications and only allow read and search operations.

## Rationale

Plan mode is for research and design. Implementation should wait for approval.

## Acceptance Criteria

- [ ] Write tool disabled in plan mode
- [ ] Edit tool disabled in plan mode
- [ ] Read, Glob, Grep tools remain functional
- [ ] ExitPlanMode tool available for transition
```

### Example: Resource State

```markdown
---
type: requirement
id: REQ-S02
category: state-driven
status: approved
priority: P1
created: 2026-02-21
---

# REQ-S02: Rate Limit Throttling

## Requirement Statement

WHILE the GitHub API rate limit is below 100 remaining requests
THE system SHALL insert a 1-second delay between API calls.

## Rationale

Prevents hitting rate limits and ensures stable operation.

## Acceptance Criteria

- [ ] Rate limit headers checked on each response
- [ ] Throttling activated at 100 remaining requests
- [ ] Normal operation resumes when limit resets
```

## Category 4: Unwanted Behavior Requirements

**Use when**: Defining how the system responds to errors or undesirable situations.

**Pattern**:

```text
IF <unwanted condition or event>
THEN THE <system> SHALL <system response>
```

### Example: Error Recovery

```markdown
---
type: requirement
id: REQ-W01
category: unwanted-behavior
status: approved
priority: P0
created: 2026-02-21
---

# REQ-W01: Test Failure Response

## Requirement Statement

IF a test fails during the commit workflow
THEN THE agent system SHALL abort the commit and report the failure to the user.

## Rationale

Prevents broken code from being committed. Maintains code quality.

## Acceptance Criteria

- [ ] Commit blocked on any test failure
- [ ] Test failure message displayed to user
- [ ] No partial commits on test failure
```

### Example: Defensive Behavior

```markdown
---
type: requirement
id: REQ-W02
category: unwanted-behavior
status: approved
priority: P0
created: 2026-02-21
---

# REQ-W02: Invalid JSON Response

## Requirement Statement

IF the GitHub API returns invalid JSON
THEN THE system SHALL retry the request up to 3 times before failing.

## Rationale

Transient API errors should not immediately fail the operation.

## Acceptance Criteria

- [ ] Retry logic implements exponential backoff
- [ ] Maximum 3 retry attempts
- [ ] Clear error message after final failure
- [ ] Each retry logged for debugging
```

## Category 5: Optional Feature Requirements

**Use when**: Behavior depends on whether a feature is included or enabled.

**Pattern**:

```text
WHERE <feature is included>
THE <system> SHALL <system response>
```

### Example: Conditional Feature

```markdown
---
type: requirement
id: REQ-O01
category: optional-feature
status: approved
priority: P2
created: 2026-02-21
---

# REQ-O01: Forgetful Memory Integration

## Requirement Statement

WHERE the Forgetful Memory MCP server is configured
THE system SHALL persist cross-session learnings to the knowledge graph.

## Rationale

Forgetful provides semantic memory. When available, use it for persistence.

## Acceptance Criteria

- [ ] MCP server availability detected at startup
- [ ] Learnings saved via execute_forgetful_tool
- [ ] Graceful degradation when unavailable
```

### Example: Platform-Specific Behavior

```markdown
---
type: requirement
id: REQ-O02
category: optional-feature
status: approved
priority: P2
created: 2026-02-21
---

# REQ-O02: PowerShell Script Execution

## Requirement Statement

WHERE PowerShell 7+ is available on the system
THE installation scripts SHALL use PowerShell for cross-platform execution.

## Rationale

PowerShell provides consistent behavior across Windows, Linux, and macOS.

## Acceptance Criteria

- [ ] PowerShell version detected at script start
- [ ] Fallback to Python scripts when unavailable
- [ ] Version requirement: 7.0.0 or higher
```

## Category 6: Complex Requirements

**Use when**: Requirements combine multiple EARS patterns.

**Pattern**: Combine keywords as needed.

```text
WHILE <in a state>
WHEN <trigger>
THE <system> SHALL <system response>
```

### Example: State + Event

```markdown
---
type: requirement
id: REQ-C01
category: complex
status: approved
priority: P1
created: 2026-02-21
---

# REQ-C01: Branch Protection Enforcement

## Requirement Statement

WHILE on a protected branch (main or master)
WHEN the user attempts a force push
THE system SHALL reject the operation and display a warning.

## Rationale

Protected branches should never receive force pushes to preserve history.

## Acceptance Criteria

- [ ] Branch protection status checked before push
- [ ] Force push blocked with clear error message
- [ ] Warning includes branch name and protection reason
```

### Example: Feature + Event + Unwanted

```markdown
---
type: requirement
id: REQ-C02
category: complex
status: approved
priority: P1
created: 2026-02-21
---

# REQ-C02: Secure Credential Handling

## Requirement Statement

WHERE the credential manager is configured
WHEN the user provides a secret value
IF the value matches a known credential pattern
THEN THE system SHALL store it in the secure credential store instead of plaintext.

## Rationale

Credentials should never be stored in plaintext configuration files.

## Acceptance Criteria

- [ ] Credential patterns detected (API keys, tokens, passwords)
- [ ] Secure storage used when credential manager available
- [ ] User notified of secure storage location
- [ ] Fallback behavior documented when unavailable
```

## Writing Guidelines

1. **Be specific**: Avoid vague terms like "quickly" or "efficiently"
2. **Be testable**: Each requirement must have measurable acceptance criteria
3. **Be atomic**: One requirement per behavior
4. **Use consistent terminology**: Reference the project glossary
5. **Include rationale**: Explain WHY the requirement exists
6. **Link traceability**: Reference related designs and tasks

## Validation Checklist

Before submitting a requirement:

- [ ] Follows correct EARS pattern for its category
- [ ] YAML front matter is complete
- [ ] Acceptance criteria are measurable
- [ ] Rationale explains business value
- [ ] No duplicate REQ-NNN ID
- [ ] Links to related documents

## References

- [EARS: Easy Approach to Requirements Syntax](https://alistairmavin.com/ears/)
- [Spec Layer Overview](../README.md)
- [Naming Conventions](../../governance/naming-conventions.md)
