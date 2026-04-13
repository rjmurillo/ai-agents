**Statement**: Verify actual tool output before accepting error handler messages.

**Context**: CI failure analysis when error messages seem generic or vague

**Evidence**: PR #402 session - Error message said "COPILOT_GITHUB_TOKEN expired" but actual issue was unparseable Copilot CLI output. The `infra: false` flag revealed this was NOT an infrastructure error.

**Atomicity**: 95% | **Impact**: 9/10

## Pattern

When investigating CI failures:

1. Read the workflow logs to find actual tool output
2. Check classification flags (`infra: true/false`, `verdict: PASS/FAIL`)
3. Examine tool stdout/stderr before the error handler
4. Distinguish between:
   - Infrastructure failures (auth, network, missing tools)
   - Execution failures (tool ran but output was wrong)

```yaml
# Example: Check flags first
- name: Analyze failure
  run: |
    echo "infra: ${{ steps.check.outputs.infra }}"
    echo "verdict: ${{ steps.check.outputs.verdict }}"
    # infra: false means tool executed - check its actual output
```

## Anti-Pattern

```text
[HARMFUL] Accept error message at face value
- CI shows: "COPILOT_GITHUB_TOKEN secret is expired"
- Agent posts: "Issue #328 is blocking this PR"
- Reality: Token works, Copilot CLI output unparseable
```

**Why harmful**: Error handlers often show generic messages. The actual tool output reveals root cause.

## Related

- [ci-infrastructure-001-fail-fast-infrastructure-failures](ci-infrastructure-001-fail-fast-infrastructure-failures.md)
- [ci-infrastructure-002-explicit-retry-timing](ci-infrastructure-002-explicit-retry-timing.md)
- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md)
- [ci-infrastructure-ai-integration](ci-infrastructure-ai-integration.md)
- [ci-infrastructure-claude-code-action-installer-race-condition](ci-infrastructure-claude-code-action-installer-race-condition.md)
