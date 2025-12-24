# Skill-CI-001: Copilot CLI Authentication Failures

## Statement

When Copilot CLI returns exit code 1 with no stdout/stderr output, this indicates an authentication or access issue with the bot account, not a code review failure. Treat as infrastructure issue (WARN) not code quality issue (CRITICAL_FAIL).

## Atomicity Score: 95%

## Impact: 9/10

## Context

Applies when:

- Copilot CLI exits with code 1
- Both stdout and stderr are empty (0 chars)
- This pattern indicates missing Copilot access, not code issues

## Pattern

### Symptoms

```text
Exit code: 1
Stdout length: 0 chars
Stderr length: 0 chars
```

### Root Causes

1. GitHub account lacks Copilot access
2. PAT token lacks 'copilot' scope
3. Rate limiting
4. Network issues reaching Copilot API

### Resolution

For auth failures (no output), emit `WARN` instead of `CRITICAL_FAIL`:

```bash
# In .github/actions/ai-review/action.yml
if [ -z "$OUTPUT" ] && [ -z "$STDERR_OUTPUT" ]; then
  echo "::warning::Copilot CLI authentication/access failure"
  OUTPUT="VERDICT: WARN"$'\n'"MESSAGE: AI review skipped - infrastructure issue"
fi
```

## Evidence

Session 04-05 (2025-12-24): Bot account lacks Copilot access. DevOps agent returned `CRITICAL_FAIL` with no output, blocking all PRs. Fixed by changing verdict to `WARN` for auth failures.

## Related

- Memory: `skills-ci-infrastructure-index`
- Memory: `copilot-synthesis-verdict-parsing`

## Tags

- #copilot-cli
- #authentication
- #ci-infrastructure
- #verdict
