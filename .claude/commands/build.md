---
description: Build incrementally. Implement changes in thin vertical slices with TDD and atomic commits. Run after /plan.
allowed-tools: Task, Skill, Read, Write, Edit, Glob, Grep, Bash(*)
argument-hint: [plan-step-or-task-description]
---

@CLAUDE.md

Build: $ARGUMENTS

If $ARGUMENTS is empty, check for recent /plan output in the conversation. If none found, ask the user what to build.

## Agent

Task(subagent_type="implementer"): You are a senior engineer. Discover the project's tech stack, coding patterns, and test conventions by reading the codebase. Build in thin vertical slices. Test-first when the project has tests. Commit atomically.

For each slice:

1. Read the task
2. Understand the existing code patterns (read related files, check test conventions)
3. Write a failing test if the project has a test framework
4. Write the minimum code to pass
5. Refactor toward quality (cohesion, encapsulation, simplicity)
6. Commit with a conventional message

## Quality Signals

After implementation, invoke Skill(skill="code-qualities-assessment") to score the result.

The agent should self-check:

- Is this hard to test? That indicates a design problem, not a test problem.
- Does every method read like a sentence? (Programming by Intention)
- Is coupling intentional or accidental?
- Would a stranger understand this code without asking questions?

## Guardrails

- Atomic commits. Each commit is one logical change, rollback-safe.
- No code without understanding the existing patterns first.
- Favor delegation over inheritance. A makes B, or A uses B. Never both.
- Three similar lines beat a premature abstraction.
