# Skill-Git-002: Fix Hook Errors, Never Bypass

**Statement**: Fix pre-commit hook errors before committing; NEVER use --no-verify to bypass protocol checks

**Context**: When pre-commit hooks fail due to protocol violations (missing session logs, linting failures)

**Evidence**: User correction after agent used `git commit --no-verify` to bypass session log requirement, creating PR churn and violating SESSION-PROTOCOL Phase 3 blocking gate

**Atomicity**: 92%

**Tag**: critical

**Impact**: 10/10 (Protocol enforcement)

**Created**: 2025-12-24

**Validation Count**: 1 (User correction - session log bypass violation)

**Failure Count**: 0

**Category**: Git

## Anti-Pattern

```bash
# Pre-commit hook fails
ERROR: BLOCKED: Create session log NOW

# WRONG: Bypass the check
git commit --no-verify -m "fix: some change"
# This creates protocol violations and technical debt
```

## Correct Pattern

```bash
# Pre-commit hook fails
ERROR: BLOCKED: Create session log NOW

# RIGHT: Fix the root cause
# 1. Create session log at .agents/sessions/YYYY-MM-DD-session-NN.md
# 2. Complete Protocol Compliance checklist
# 3. Commit normally (hooks will pass)
git commit -m "fix: some change"
```

## Why This Matters

Pre-commit hooks enforce protocol requirements:

- Session log creation (Phase 3: REQUIRED)
- Markdown linting (Phase 2: Quality Checks)
- Security validation
- File size limits

Using `--no-verify` bypasses ALL quality gates, not just the one blocking you.

## When Hooks Fail

1. **Read the error message** - hooks tell you exactly what's wrong
2. **Fix the root cause** - don't bypass validation
3. **Commit normally** - validation will pass
4. **NEVER use --no-verify** - explicitly discouraged in git documentation

## Git Documentation

From `git commit --help`:

> --no-verify
> This option bypasses the pre-commit and commit-msg hooks.
> **See also githooks(5).**
>
> Use sparingly.

"Use sparingly" means for emergencies, not routine protocol compliance.

## Related Protocol Requirements

### SESSION-PROTOCOL.md Phase 3: Session Log Creation (REQUIRED)

> The agent MUST create a session log file at `.agents/sessions/YYYY-MM-DD-session-NN.md`
> The session log SHOULD be created within the first 5 tool calls of the session

### SESSION-PROTOCOL.md Phase 2: Quality Checks (REQUIRED)

> The agent MUST run `npx markdownlint-cli2 --fix "**/*.md"` to fix markdown issues
> The agent MUST NOT end session with known failing lints

## Enforcement Discipline

Pre-commit hooks exist to prevent protocol violations from entering the repository. Bypassing hooks:

- Violates protocol blocking gates
- Creates technical debt
- Wastes reviewer time
- Requires manual cleanup

Fix the issue, don't bypass the check.

## Related Skills

- Skill-Logging-002: Create session log early (WHEN to create)
- Skill-Git-001: Pre-commit branch validation (WHAT to check)
- Skill-Protocol-001: Verification-based blocking gates (HOW to design gates)

This skill focuses on: HOW to respond when enforcement fails (fix, don't bypass)
