---
description: Review before merge. Five-axis code review across architecture, security, quality, tests, and standards. Run after /test.
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
argument-hint: [branch-or-pr-number]
---

@CLAUDE.md

Review: $ARGUMENTS

If no argument, review the current branch diff against the base branch. Detect the base branch from `gh pr view --json baseRefName` or fall back to `main`.

## Process

Run axes sequentially. Each axis produces findings categorized as Critical, Important, or Suggestion.

1. Read the diff (git diff against detected base branch)
2. **Classify complexity tier**: Task(subagent_type="analyst"): Read `.claude/skills/analyze/references/engineering-complexity-tiers.md` and the diff (`git diff` against detected base). Assess the change as Tier 1-5 based on scope, cross-team impact, ambiguity, and reversibility. Return: tier number, rationale, and recommended review depth. Use this to calibrate remaining axes:
   - Tier 1-2: Focus on correctness and standards. Single-pass review sufficient.
   - Tier 3: All five axes. Flag missing design docs or SLO definitions.
   - Tier 4-5: All five axes plus: challenge whether complexity can be driven out. Flag missing ADR, threat model, or stakeholder alignment. Ask "is this simpler than it needs to be?"
3. **Architecture pass**: Task(subagent_type="architect")
4. **Security pass**: Task(subagent_type="security")
5. **Quality pass**: Invoke Skill(skill="code-qualities-assessment")
6. **Test pass**: Task(subagent_type="qa")
7. **Standards pass**: Invoke Skill(skill="golden-principles") and Skill(skill="taste-lints")
8. Synthesize findings across all axes

## Axis 1: Architecture

Task(subagent_type="architect"): You are a software architect reviewing for structural integrity. Check ADR conformance in .agents/architecture/. Evaluate from the consumer perspective, not the implementer perspective. Findings must cite file:line.

- Follows existing patterns? Clean boundaries? Right abstraction level?
- Coupling intentional? Cohesion strong?
- ADR conformance? Any decisions that need a new ADR?

## Axis 2: Security

Invoke Skill(skill="security-scan") for CWE pattern detection.

Task(subagent_type="security"): You are a security auditor. Assume every input is malicious. Reference CWE numbers. Evaluate:

- Input validated? Secrets safe? Auth checked?
- OWASP top 10? STRIDE threats?
- New permissions, scopes, or access? Challenge each one (Principle of Least Privilege).

## Axis 3: Code Quality

Invoke Skill(skill="code-qualities-assessment") to score all 5 qualities: cohesion, coupling, encapsulation, testability, non-redundancy.

- Cyclomatic complexity <=10? Methods <=60 lines?
- DRY violations? Premature abstractions?

## Axis 4: Test Completeness

Task(subagent_type="qa"): You are a QA engineer verifying coverage. For every new code path in the diff, verify a corresponding test exists. Flag gaps with specific file:line references.

- Every new code path has a test? Failure paths covered?
- Acceptance criteria verified?

## Axis 5: Standards

Invoke Skill(skill="golden-principles") and Skill(skill="taste-lints").

- Golden principle violations? Naming conventions?
- Style enforcement? Consistency with existing patterns?

## Principles

- **Design to interfaces**: Review signatures from the consumer perspective. Hidden implementation details should stay hidden.
- **Encapsulate what varies**: If the diff introduces variation, is it encapsulated? Or scattered?
- **Chesterton's Fence**: Before removing code, verify you understand why it existed.
- **Principle of Least Privilege**: New permissions, scopes, or access? Challenge each one.

## Output

Categorize each finding as **Critical**, **Important**, or **Suggestion**.

Per-finding format:

- Finding (what is wrong)
- Location (file:line)
- Severity (Critical/Important/Suggestion)
- Fix (specific recommendation)
