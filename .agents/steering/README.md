# Steering System

## Purpose

The steering system provides context-aware guidance injection for agents based on file patterns. This reduces token usage by including only relevant guidance for the files being modified.

## Overview

Steering files contain domain-specific guidance that gets injected into agent context when working with matching files. This implements the Kiro pattern of glob-based inclusion.

### Unified Steering Architecture

The steering system uses a **single source of truth** approach:

- **Authoritative Source**: `.agents/steering/` - Full steering content for all platforms
- **Copilot Entry Points**: `.github/instructions/` - Lightweight pointers with quick reference

This design avoids content duplication while supporting both Claude-based agents (via orchestrator injection) and GitHub Copilot (via `applyTo:` directive). The `.github/instructions/` files contain:
1. Front matter with `applyTo:` glob patterns
2. Links to authoritative `.agents/steering/` content  
3. Quick reference snippets for immediate context

See [GitHub Copilot Custom Instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions#creating-path-specific-custom-instructions-3) for how Copilot uses these files.

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
applyTo: [Glob pattern(s)]
excludeFrom: [Optional: Glob pattern(s) to exclude]
priority: [1-10, higher = more important]
version: [Semantic version]
status: [placeholder | draft | published]
---
```

**Notes**:
- `applyTo` uses the same glob pattern format as GitHub Copilot's custom instructions for consistency.
- `excludeFrom` is optional and specifies patterns to exclude from matching (e.g., exclude test files from production patterns).

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
| `**/*.Tests.ps1` | Pester test files | `Get-Config.Tests.ps1` |
| `*.{cs,ts}` | C# or TypeScript | `Service.cs`, `service.ts` |

## Steering Files (Phase 4)

| File | applyTo Pattern | Purpose | Copilot Entry Point |
|------|-----------------|---------|---------------------|
| `agent-prompts.md` | `**/AGENTS.md,src/claude/**/*.md,templates/agents/**/*.md` | Agent prompt standards | `.github/instructions/agent-prompts.instructions.md` |
| `security-practices.md` | `**/Auth/**,*.env*,**/*.secrets.*,.github/workflows/**,.githooks/**` | Security best practices | `.github/instructions/security.instructions.md` |
| `testing-approach.md` | `**/*.Tests.ps1` | Pester testing conventions | `.github/instructions/testing.instructions.md` |
| `documentation.md` | `**/*.md` (excluding agents/steering) | Documentation standards | `.github/instructions/documentation.instructions.md` |
| `powershell-patterns.md` | `**/*.ps1,**/*.psm1` | PowerShell coding patterns | N/A (Phase 4) |

## Usage Example

### Task Scenario

```text
User: Write Pester tests for the steering matcher skill
Orchestrator analyzes:
- Files: .claude/skills/steering-matcher/Get-ApplicableSteering.Tests.ps1
- Matches:
  - testing-approach.md (**/*.Tests.ps1)

Orchestrator to qa:
"Create test strategy for PowerShell skill.

Context from steering:
- testing-approach.md: Use Pester AAA pattern, mock dependencies, verify behavior
"
```

### Token Usage Comparison

**Without steering scoping** (all files):
- agent-prompts.md: 1,800 tokens
- testing-approach.md: 2,200 tokens  
- security-practices.md: 3,000 tokens
- documentation.md: 1,500 tokens
- **Total**: 8,500 tokens

**With steering scoping** (matched only):
- testing-approach.md: 2,200 tokens
- **Total**: 2,200 tokens
- **Savings**: 74%

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0: Foundation | ✅ Complete | Directory structure created |
| Phase 4: Steering Scoping | 📋 Planned | Content creation and injection logic |

## Integration Points

### Orchestrator

Orchestrator determines which steering to inject using the PowerShell skill:

```powershell
# See .claude/skills/steering-matcher/Get-ApplicableSteering.ps1
$applicableSteering = Get-ApplicableSteering -Files $filesAffected
# Returns steering files sorted by priority (descending)
```

For implementation details, see [Claude Skill: Steering Matcher](../../.claude/skills/steering-matcher/README.md).

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
