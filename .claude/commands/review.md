---
description: Review before merge. Five-axis code review across architecture, security, quality, tests, and standards. Run after /test.
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(git diff:*), Bash(git log:*), Bash(git status:*)
argument-hint: [branch-or-pr-number]
---

@CLAUDE.md

Invoke the analyze, code-qualities-assessment, and security-scan skills.

Review the current changes across all five axes: $ARGUMENTS

If no argument, review the current branch diff against main.

Sequential evaluation order:

1. **Architecture** - Follows existing patterns? Clean boundaries? Right abstraction level? Coupling intentional? ADR conformance?
2. **Security** - Input validated? Secrets safe? Auth checked? OWASP top 10? STRIDE threats? CWE scan? (Use Task(subagent_type="security"))
3. **Code quality** - Score all 5 qualities: cohesion, coupling, encapsulation, testability, non-redundancy. Cyclomatic complexity <=10? Methods <=60 lines?
4. **Test completeness** - Every new code path has a test? Failure paths covered? Acceptance criteria verified?
5. **Standards** - Golden principles, taste lints, style enforcement, naming conventions

## Principles

- **Design to interfaces**: Review signatures from the consumer perspective. Hidden implementation details should stay hidden.
- **Encapsulate what varies**: If the diff introduces variation, is it encapsulated? Or scattered?
- **Chesterton's Fence**: Before removing code, verify you understand why it existed.
- **Principle of Least Privilege**: New permissions, scopes, or access? Challenge each one.

## Process

1. Read the diff (git diff main...HEAD)
2. Architecture pass: Task(subagent_type="architect") evaluates structure
3. Security pass: Task(subagent_type="security") evaluates threats
4. Quality pass: invoke code-qualities-assessment skill
5. Test pass: Task(subagent_type="qa") evaluates coverage
6. Standards pass: invoke golden-principles and taste-lints skills
7. Synthesize findings

## Output

Categorize each finding as **Critical**, **Important**, or **Suggestion**.

Structured review with:

- Finding (what is wrong)
- Location (file:line)
- Severity (Critical/Important/Suggestion)
- Fix (specific recommendation)
