---
description: Build incrementally. Implement changes in thin vertical slices with TDD and atomic commits. Run after /plan.
allowed-tools: Task, Skill, Read, Write, Edit, Glob, Grep, Bash(*)
argument-hint: [plan-step-or-task-description]
---

@CLAUDE.md

Build: $ARGUMENTS

If $ARGUMENTS is empty, check for recent /plan output in the conversation. If none found, ask the user what to build.

## Complexity Assessment

Before implementation, Task(subagent_type="analyst"): Read `.claude/skills/analyze/references/engineering-complexity-tiers.md` and the task description. Classify as Tier 1-5. Return: tier, rationale, and recommended oversight level. Use this to calibrate implementation approach:

- Tier 1-2: Implement directly. Async code review sufficient.
- Tier 3: Validate approach before coding. Active mentorship pattern (check in at milestones).
- Tier 4-5: Proof-of-concept first. Get design sign-off before full implementation.

## Pre-Mortem (Risk Identification)

Before any code changes, invoke Skill(skill="pre-mortem") on the task as briefed. Capture the top 2-3 critical risks and their mitigations into the session log. Risks surfaced by reviewers late in the cycle are usually knowable up front. A 5-minute pre-mortem is cheaper than a 10-round bot review.

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

The agent should self-check:

- Is this hard to test? That indicates a design problem, not a test problem.
- Does every method read like a sentence? (Programming by Intention)
- Is coupling intentional or accidental?
- Would a stranger understand this code without asking questions?

## Mandatory Exit Gates

The build is not complete until all four gates below return clean. These are **hard preconditions for declaring done**, not advisory output. If any gate returns findings, the implementer must address them in the same `/build` cycle. Do not kick the can to PR review; advisory framing here produces the iteration paradox where reviewers flag what the implementer should have caught, multiplying the cost of every revision.

Run, in order:

1. Skill(skill="code-qualities-assessment") with `--changed-only` against the changed files. Reject the build if any new or modified method scores below the configured thresholds in `.qualityrc.json`.
2. Skill(skill="taste-lints") against the changed files (use `--git-staged` or pass paths explicitly). Reject the build on any error-level violation; address every warning surfaced on lines you touched.
3. Skill(skill="doc-accuracy") with `--diff-base main` so it audits changed comments, docstrings, and prose. Reject the build on any critical or high finding in code or docs you authored.
4. Skill(skill="orphan-ref-validator"). Reject the build on `VERDICT: CRITICAL_FAIL`. Catches references to deleted skills and missing script paths before they reach review. Manifest count drift is caught by the canonical `build/scripts/validate_marketplace_counts.py` (which orphan-ref-validator's `COUNT_CLAIM_RE` mirrors but does not duplicate emission). The skill invocation is platform-agnostic; each platform mirror runs its own copy of `scan.py`.

If a gate flags an item that is genuinely out of scope for this build, document the rationale in the session log and link to the follow-up issue. "I will fix it in review" is not an acceptable rationale.

## Guardrails

- Atomic commits. Each commit is one logical change, rollback-safe.
- No code without understanding the existing patterns first.
- Favor delegation over inheritance. A makes B, or A uses B. Never both.
- Three similar lines beat a premature abstraction.
