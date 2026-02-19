# Skill: Python Lint Pre-Push Fix Strategy

**Skill ID**: python-lint-prepush-fix
**Domain**: Python Development, Quality Gates
**Atomicity**: 92%
**Evidence**: Session 1187 commit 8cbd580c - bypassed ruff failures without attempting fix
**Related**: quality-gates-bypass-enforcement

## Statement

When ruff fails in pre-push hook, run `ruff check --fix` on failed files and review auto-fixes before committing.

## Context

Pre-push hook Phase 2 Python lint failure (check #6 in `.githooks/pre-push`). Before considering bypass, attempt auto-fix.

**Trigger Conditions:**

- Pre-push hook fails with ruff errors
- CI fails with Python lint errors
- Local development: ruff check returns errors

## Application

### When Pre-Push Fails

```bash
# Pre-push hook output:
ERROR: Python lint/ruff
  Ruff issues:
    scripts/my_script.py:42:5: F401 [*] `os` imported but unused
    scripts/my_script.py:89:1: E501 Line too long (120 > 88 characters)
  Fix: ruff check --fix <files>
```

### Step 1: Run Auto-Fix

```bash
# Fix all auto-fixable issues
ruff check --fix scripts/my_script.py

# Or fix all Python files in changed set
git diff --name-only --diff-filter=d '*.py' | xargs ruff check --fix
```

### Step 2: Review Changes

```bash
# See what ruff changed
git diff scripts/my_script.py

# Verify changes are safe:
# - Removed unused imports: Safe
# - Reformatted code: Safe
# - Changed logic: REVIEW CAREFULLY
```

### Step 3: Handle Unfixable Issues

```bash
# If ruff still reports errors after --fix:
ruff check scripts/my_script.py

# Common unfixable issues:
# - E501 (line too long): Manually wrap line
# - F821 (undefined name): Fix undefined variable
# - E999 (syntax error): Fix Python syntax
```

### Step 4: Commit and Retry Push

```bash
# Stage the fixes
git add scripts/my_script.py

# Commit
git commit -m "fix: apply ruff auto-fixes"

# Retry push (pre-push hook will re-validate)
git push
```

## When NOT to Bypass

**Never bypass for:**

- Unused imports (F401) - Auto-fixable with `--fix`
- Missing whitespace (W291, W293) - Auto-fixable
- Import ordering (I001) - Auto-fixable
- Trailing commas (COM812) - Auto-fixable

**Consider bypass only for:**

- Broken CI requiring immediate hotfix push
- Lint tool bug (false positive confirmed by team)
- Emergency security patch (document in bypass justification)

## Evidence

**Session 1187 Failure:**

- Commit 8cbd580c bypassed ruff failures with SKIP_PREPUSH=1
- No evidence of running `ruff check --fix` before bypass
- Justification: "fix(pre-push): use bash arrays for markdownlint command to prevent command injection"
- Actual reason: Python lint errors present (unrelated to bash arrays)
- Pattern: Used escape hatch instead of fixing root cause

**Correct Behavior:**

```bash
# What should have happened:
$ git push
# Pre-push fails with ruff errors

$ ruff check --fix scripts/*.py
# Auto-fixes applied

$ git add scripts/*.py
$ git commit -m "fix: apply ruff auto-fixes"
$ git push
# Pre-push succeeds
```

## Integration with Pre-Push Hook

The pre-push hook already suggests this command:

```bash
# From .githooks/pre-push lines 348-349:
echo_info "  Fix: ruff check --fix <files>"
```

**Follow the suggested fix before considering bypass.**

## Related Skills

- quality-gates-bypass-enforcement: When bypass is actually needed
- quality-gates-root-cause-before-bypass: Five Whys before bypass
- process-bypass-pattern-interrupt: Interrupt shortcut-taking pattern

## Anti-Patterns

| Anti-Pattern | Why It Fails | Instead |
|--------------|--------------|---------|
| Bypass without fix attempt | Ignores auto-fixable issues | Run `ruff check --fix` first |
| Manual editing without ruff | May introduce new lint issues | Use ruff's auto-fix |
| Commit without re-running ruff | May still have unfixed issues | Let pre-push re-validate |

## Keywords

python, ruff, lint, auto-fix, pre-push, quality-gates, validation, bypass-prevention
