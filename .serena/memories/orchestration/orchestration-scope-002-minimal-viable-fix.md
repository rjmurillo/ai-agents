# Skill: Minimal Viable Fix (Scope Discipline)

**ID**: skill-scope-002-minimal-viable-fix
**Category**: Scope Discipline
**Atomicity Score**: 95%
**Evidence**: PR #395 failure analysis (2025-12-25)

## Trigger

Any request containing:
- "debug"
- "fix"
- "investigate"
- "why doesn't this work"

## Behavior

1. **Default to smallest possible change**
2. **Investigate before implementing**
3. **Stop and verify after minimal fix**

## Rules

1. If estimated changes exceed 50 lines, STOP and ask user
2. If discovering unrelated issues, DOCUMENT but do not fix
3. If tests fail after change, REVERT code (not modify tests)
4. After minimal fix works, VERIFY before any expansion

## Anti-Patterns (AVOID)

- Removing "dead code" during debug task
- Adding logging beyond immediate problem
- Changing function signatures/return types
- Creating ADRs for small fixes
- "Fixing" tests to match broken code

## Checkpoint Template

Before implementing:
```
Investigation complete:
- Root cause: [description]
- Minimal fix: [X lines, Y files]
- Scope within limit: [yes/no]

Proceed with implementation? [wait for confirmation]
```

## Evidence

PR #395: Copilot asked to debug "ran but did nothing"
- Expected: ~50 line visibility fix
- Actual: 847 lines, broke script
- Root cause: No scope constraint in prompt

## Related Skills

- skill-implementation-010: checkpoint validation
- skill-test-001: test preservation
- skill-prompt-001: Copilot SWE constraints

## Related

- [orchestration-003-orchestrator-first-routing](orchestration-003-orchestrator-first-routing.md)
- [orchestration-copilot-swe-anti-patterns](orchestration-copilot-swe-anti-patterns.md)
- [orchestration-handoff-coordination](orchestration-handoff-coordination.md)
- [orchestration-parallel-execution](orchestration-parallel-execution.md)
- [orchestration-pr-chain](orchestration-pr-chain.md)
