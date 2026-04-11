---
description: Build incrementally. Implement changes in thin vertical slices with TDD and atomic commits. Run after /plan.
allowed-tools: Task, Skill, Read, Write, Edit, Glob, Grep, Bash(git add:*), Bash(git commit:*), Bash(git status:*), Bash(git diff:*), Bash(python3:*)
argument-hint: [plan-step-or-task-description]
---

@CLAUDE.md

Invoke the code-qualities-assessment and golden-principles skills.

Build: $ARGUMENTS

Use Task(subagent_type="implementer") as the primary agent. If no argument provided, check for recent /plan output or ask what to build.

Evaluate across all 5 axes:

1. **Test-first discipline** - Red before green before refactor. No code without a failing test.
2. **Commit atomicity** - Each commit is one logical change, rollback-safe.
3. **Code quality** - Cohesion, coupling, encapsulation, testability, non-redundancy.
4. **Complexity budget** - Cyclomatic complexity <=10. Methods <=60 lines. No nesting.
5. **Standards compliance** - Golden principles, style enforcement, naming conventions.

## Software Hierarchy of Needs

Design emerges bottom-up. Enforce qualities before reaching for patterns.

1. Qualities: Cohesion, Coupling, DRY, Encapsulation, Testability
2. Principles: Open-Closed, Encapsulate by Policy, Separation of Concerns
3. Practices: Programming by Intention, State Always Private, CVA
4. Wisdom: Design to interfaces, Favor delegation over inheritance, Encapsulate what varies, Separate use from creation
5. Patterns: Only when the problem demands it. Three similar lines beat a premature abstraction.

## Process

1. Read the task or plan step
2. Write a failing test (red)
3. Write the minimum code to pass (green)
4. Refactor toward the hierarchy of needs (refactor)
5. Run golden-principles and taste-lints before committing
6. Commit atomically with conventional message
7. Repeat for next slice

## Guardrails

- Hard to test? Fix the design, not the test. Indicates tight coupling or weak encapsulation.
- Ask "how would I test this?" even without tests.
- Every method should read like a sentence (Programming by Intention).
- Favor delegation over inheritance. A makes B, or A uses B. Never both.
