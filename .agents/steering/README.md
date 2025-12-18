# Steering System

## Purpose

The steering system provides context-aware guidance injection for agents based on file patterns. This reduces token usage by including only relevant guidance for the files being modified.

## Overview

Steering files contain domain-specific guidance that gets injected into agent context when working with matching files. This implements the Kiro pattern of glob-based inclusion.

## How It Works

### 1. Task Analysis

When orchestrator delegates work, it analyzes the files affected:

```text
Task: Implement OAuth2 token endpoint
Files: src/Auth/Controllers/TokenController.cs
       src/Auth/Services/TokenService.cs
```

### 2. Pattern Matching

Orchestrator matches file paths against steering glob patterns:

```yaml
csharp-patterns.md → **/*.cs ✓ MATCH
security-practices.md → **/Auth/** ✓ MATCH
testing-approach.md → **/*.test.* ✗ NO MATCH
```

### 3. Context Injection

Matched steering files are injected into agent prompt:

```text
@implementer Implement token endpoint.

Relevant Steering:
- csharp-patterns.md (C# conventions)
- security-practices.md (Auth security)
```

### 4. Token Savings

By including only relevant guidance, we reduce token usage:

- **Without steering scoping**: All guidance included (10K+ tokens)
- **With steering scoping**: Only matched guidance (2-3K tokens)
- **Target savings**: 30%+ for focused tasks

## Directory Structure

```text
.agents/steering/
├── README.md                 # This file
├── csharp-patterns.md       # C# coding standards (Phase 4)
├── agent-prompts.md         # Agent prompt patterns (Phase 4)
├── testing-approach.md      # Testing conventions (Phase 4)
├── security-practices.md    # Security requirements (Phase 4)
└── documentation.md         # Documentation standards (Phase 4)
```

## Steering File Format

Each steering file includes:

### Front Matter

```yaml
---
name: [Steering File Name]
scope: [Glob pattern(s)]
priority: [1-10, higher = more important]
version: [Semantic version]
---
```

### Content Sections

```markdown
# [Domain] Steering

## Scope

**Applies to**: [glob pattern]

## Guidelines

[Domain-specific guidance]

## Patterns

### Pattern 1
[Description]

**Example**:
```[language]
[code example]
```

## Anti-Patterns

[What to avoid]

## Examples

### Good
[Positive example]

### Bad
[Negative example]
```

## Glob Pattern Reference

| Pattern | Matches | Example |
|---------|---------|---------|
| `*.cs` | C# files (current dir) | `Program.cs` |
| `**/*.cs` | C# files (all dirs) | `src/Auth/TokenService.cs` |
| `**/Auth/**` | Files in Auth dirs | `src/Auth/Models/User.cs` |
| `**/*.test.*` | Test files | `TokenService.test.cs` |
| `*.{cs,ts}` | C# or TypeScript | `Service.cs`, `service.ts` |

## Steering Files (Planned - Phase 4)

### csharp-patterns.md

**Scope**: `**/*.cs`

**Content**:
- SOLID principles
- Naming conventions
- Async/await patterns
- Exception handling
- Performance patterns

### agent-prompts.md

**Scope**: `src/claude/**/*.md`

**Content**:
- Prompt engineering guidelines
- Agent interface consistency
- Memory protocol usage
- Handoff format

### testing-approach.md

**Scope**: `**/*.test.*, **/*.spec.*`

**Content**:
- xUnit conventions
- Test naming patterns
- Mocking strategies
- Coverage expectations

### security-practices.md

**Scope**: `**/Auth/**, *.env*, **/*.secrets.*`

**Content**:
- OWASP guidelines
- Authentication patterns
- Secrets management
- Input validation

### documentation.md

**Scope**: `**/*.md` (excluding `src/claude/`)

**Content**:
- Markdown formatting
- Document structure
- Cross-reference format
- Metadata requirements

## Usage Example

### Task Scenario

```text
User: Implement user login endpoint
Orchestrator analyzes:
- Files: src/Auth/Controllers/AuthController.cs
- Matches:
  - csharp-patterns.md (**.cs)
  - security-practices.md (**/Auth/**)

Orchestrator to implementer:
"Implement login endpoint.

Context from steering:
- csharp-patterns.md: Use async/await, validate inputs
- security-practices.md: Hash passwords with bcrypt, prevent timing attacks
"
```

### Token Usage Comparison

**Without steering scoping** (all files):
- csharp-patterns.md: 2,500 tokens
- agent-prompts.md: 1,800 tokens
- testing-approach.md: 2,200 tokens
- security-practices.md: 3,000 tokens
- documentation.md: 1,500 tokens
- **Total**: 11,000 tokens

**With steering scoping** (matched only):
- csharp-patterns.md: 2,500 tokens
- security-practices.md: 3,000 tokens
- **Total**: 5,500 tokens
- **Savings**: 50%

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0: Foundation | ✅ Complete | Directory structure created |
| Phase 4: Steering Scoping | 📋 Planned | Content creation and injection logic |

## Integration Points

### Orchestrator

Orchestrator determines which steering to inject:

```python
def get_applicable_steering(files_affected):
    steering_files = []
    for file in files_affected:
        for steering in all_steering_files:
            if glob_match(steering.scope, file):
                steering_files.append(steering)
    return dedupe_by_priority(steering_files)
```

### Agent Prompts

Agents receive steering in context section:

```markdown
## Context

### Files to Modify
- src/Auth/Controllers/AuthController.cs

### Applicable Steering
See `.agents/steering/csharp-patterns.md` for coding standards.
See `.agents/steering/security-practices.md` for security requirements.
```

## Validation

Phase 2 validation scripts will check:

- [ ] All steering files have valid glob patterns
- [ ] No conflicting guidance between steering files
- [ ] Glob patterns match intended file sets
- [ ] Token usage measured and tracked

## Future Enhancements

1. **Dynamic Priority**: Adjust priority based on task type
2. **Conditional Guidance**: Include sections based on task context
3. **Learning Integration**: Update steering from retrospectives
4. **Metrics Dashboard**: Track token savings over time

## Related Documents

- [Enhancement Project Plan](../planning/enhancement-PROJECT-PLAN.md)
- [Agent System](../AGENT-SYSTEM.md)
- [Orchestrator Agent](../../src/claude/orchestrator.md)

---

*Version: 1.0*
*Created: 2025-12-18*
*Phase: 0 - Foundation*
*Implementation: Phase 4 - Steering Scoping*
