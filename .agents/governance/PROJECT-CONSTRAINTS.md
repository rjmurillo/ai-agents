# Project Constraints

> **Status**: Canonical Source of Truth
> **Last Updated**: 2025-12-18
> **RFC 2119**: This document uses RFC 2119 key words.

## Purpose

Single source of truth for project constraints. Index-style document pointing to authoritative sources.

**How to use**: Read at session start. When in doubt, click through to Source for full rationale.

---

## Language Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST NOT create bash scripts (.sh) | ADR-005 | Pre-commit hook, code review |
| MUST NOT create Python scripts (.py) | ADR-005 | Pre-commit hook, code review |
| MUST use PowerShell for all scripting (.ps1, .psm1) | ADR-005 | Pre-commit hook, code review |

**Reference**: [ADR-005-powershell-only-scripting.md](../architecture/ADR-005-powershell-only-scripting.md)

**Rationale Summary**: 100% of existing infrastructure is PowerShell. Single testing framework (Pester). Cross-platform (PowerShell Core). Token efficiency (agents stop wasting tokens on bash/Python).

**Exceptions**: None. If PowerShell is genuinely insufficient, document why and get explicit approval.

---

## Skill Usage Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST NOT use raw `gh` commands when skill exists | usage-mandatory | Check-SkillExists.ps1 |
| MUST check `.claude/skills/` before GitHub operations | usage-mandatory | Phase 1.5 gate |
| MUST extend skills if capability missing, not write inline | usage-mandatory | Code review |

**Reference**: Use `mcp__serena__read_memory` with `memory_file_name="usage-mandatory"`

**Rationale Summary**: Skills are tested, handle errors, have proper parameter validation, and are maintained centrally. Raw commands bypass all quality controls.

**Process**:

1. Before ANY GitHub operation, check if skill exists
2. If exists, use the skill script
3. If missing, ADD to skill (don't write inline), then use it

**Skill Location**: `.claude/skills/github/scripts/{pr,issue,reactions}/`

---

## Workflow Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST NOT put business logic in workflow YAML | ADR-006 | Code review |
| SHOULD keep workflows under 100 lines (orchestration only) | ADR-006 | Lint check |
| MUST put complex logic in .psm1 modules | ADR-006 | Code review |
| MUST have Pester tests for modules (80%+ coverage) | ADR-006 | CI coverage check |
| MUST add new AI-powered workflows to monitoring list | workflow-coalescing | Code review, manual validation |
**Reference**: [ADR-006-thin-workflows-testable-modules.md](../architecture/ADR-006-thin-workflows-testable-modules.md)

**Rationale Summary**: GitHub Actions workflows cannot be tested locally. The feedback loop (edit -> push -> wait -> check) is slow. Extracting logic to modules enables fast local testing with Pester.

**Pattern**:

- Workflow YAML: Orchestration only (calls, parameters, artifacts)
- PowerShell Module (.psm1): All business logic
- Pester Tests (.Tests.ps1): Fast local feedback

**New AI-Powered Workflow Checklist**:

When creating a new AI-powered workflow with concurrency control:

1. Add workflow name to monitoring list in `.github/scripts/Measure-WorkflowCoalescing.ps1` (line 47, `$Workflows` parameter default)
2. Document workflow in `.github/AGENTS.md`
3. Ensure concurrency group follows naming pattern: `{prefix}-${{ github.event.pull_request.number }}`

---

## Commit Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST NOT mix multiple logical changes in one commit | code-style-conventions | commit-msg hook |
| SHOULD use one logical change per commit | code-style-conventions | commit-msg hook |
| SHOULD limit to max 5 files OR single topic | code-style-conventions | commit-msg hook |
| MUST use conventional commit format | code-style-conventions | commit-msg hook |

**Reference**: Use `mcp__serena__read_memory` with `memory_file_name="code-style-conventions"`

**Format**:

```text
<type>(<scope>): <description>

<optional body>
```

**Types**: feat, fix, docs, refactor, test, chore, style

---

## Session Protocol Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST initialize Serena before any other action | SESSION-PROTOCOL | Tool output in transcript |
| MUST read .agents/HANDOFF.md before starting work | SESSION-PROTOCOL | Content in context |
| MUST create session log early in session | SESSION-PROTOCOL | File exists |
| MUST NOT modify HANDOFF.md during session | SESSION-PROTOCOL, ADR-014 | HANDOFF.md unchanged |
| MUST update session log at session end | SESSION-PROTOCOL | Session log complete |
| MUST commit all changes before ending | SESSION-PROTOCOL | Git status clean |

**Reference**: [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md)

**Rationale Summary**: Verification-based enforcement (tool output required) succeeds where trust-based compliance ("agent should remember") fails.

---

## Validation Checklist

Use this checklist during session start:

- [ ] Read this document (PROJECT-CONSTRAINTS.md)
- [ ] For GitHub operations: Verify skill exists before writing code
- [ ] For new scripts: Verify PowerShell-only (no .sh or .py files)
- [ ] For workflow changes: Verify logic in modules, not YAML
- [ ] Before commit: Verify atomic commit rule (single logical change)

---

## Existing Violations (Grandfathered)

None currently documented. Add here if legacy code violates constraints but is accepted.

---

## Maintenance

| Attribute | Value |
|-----------|-------|
| Owner | Retrospective agent (quarterly review) |
| Update trigger | When ADRs added/amended, new preferences documented |
| Review cadence | Quarterly (align with agent consolidation review) |
| Validation | Link checker (all Source links valid) |

---

## Related Documents

- [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md) - Session start/end requirements
- [ADR-005-powershell-only-scripting.md](../architecture/ADR-005-powershell-only-scripting.md) - Language decision
- [ADR-006-thin-workflows-testable-modules.md](../architecture/ADR-006-thin-workflows-testable-modules.md) - Workflow architecture
- [Analysis 002 - Project Constraints Consolidation](../analysis/002-project-constraints-consolidation.md) - Background analysis
