# Skill: Skill-Implementation-Architecture-001-Memory-First-Pattern

**Atomicity Score**: 92%
**Source**: jeta (implementer agent) - Sessions 40-41 retrospective
**Date**: 2025-12-20
**Validation Count**: 1 (Session 41 refactor)

## Definition

For agent-facing patterns (detection, routing, decision logic), document in Serena memory FIRST. Only write executable code if the pattern cannot be executed by agent reasoning alone.

## Decision Tree

```text
If pattern is "detection" or "decision logic":
  -> Document in memory (Skill-X-Y format)
  -> Agent reads memory at Step 0
  -> Agent executes pattern in reasoning
  -> NO shell scripts needed
  -> Go to code only if Step X requires actual external CLI execution

If pattern is "external CLI operation":
  -> Document memory pattern first
  -> Document shell command in memory comment block
  -> Test command works locally
  -> Add to documented workflows (not hidden in scripts)
```

## Trigger

When you identify a repeating pattern that multiple agents need to follow.

## Correct Pattern

```text
# .serena/memories/pr-comment-responder-skills.md:
# Skill-PR-Copilot-001: Detection heuristics
#   - Branch pattern: copilot/sub-pr-{N}
#   - Verification: announcement comment exists
#   - Categorization: DUPLICATE/SUPPLEMENTAL/INDEPENDENT
```

## Anti-Pattern (Avoid)

```powershell
# WRONG: Function in external script
function Detect-CopilotFollowUpPR { ... }
```

## Comparison

| Aspect | Shell Scripts | Memory-First |
|--------|---------------|--------------|
| Maintenance | Edit script files, redeploy | Edit memory file, agents learn automatically |
| Cross-Agent | Each agent must know script location | All agents access unified memory |
| Versioning | Script versions can diverge | Single source of truth in memory |
| Institutional Knowledge | Lost if script deleted | Persisted in version control |
| Onboarding | New agents must learn script syntax | New agents read memory documentation |
| Dependency | External file dependency | Self-contained in agent reasoning |

## Evidence

- Anti-Pattern (Shell Scripts): Sessions 40-41 Copilot detection created 2 external scripts
- Correct Pattern (Memory-First): Session 41 refactor moved logic to Skill-PR-Copilot-001
- Validation: Both implementations have same functionality; memory version requires NO external files
- Impact: Removed 2 files, centralized logic, improved maintainability

## Why 92% Atomicity

- Single concern: Memory-first vs code-first decision
- Reusable: Applies to any agent pattern
- Clear criteria: If detection/decision -> memory first
- Observable: Scripts exist or don't
- Enforceable: bigboss governance feedback validates this

## Related Skills

- Skill-PR-Copilot-001: Example of correctly implemented memory-first pattern
- SESSION-PROTOCOL.md Step 0: list_memories requirement

## Related

- [implementation-001-pre-implementation-test-discovery](implementation-001-pre-implementation-test-discovery.md)
- [implementation-002-test-driven-implementation](implementation-002-test-driven-implementation.md)
- [implementation-006-graphql-first](implementation-006-graphql-first.md)
- [implementation-additive-approach](implementation-additive-approach.md)
- [implementation-clarification](implementation-clarification.md)
