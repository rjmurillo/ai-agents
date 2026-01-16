---
name: fix-ci
version: 1.0.0
model: claude-opus-4-5
description: Autonomously inspect failing GitHub Actions CI checks, fetch logs, analyze
  failures, and implement fixes without user approval. Integrates with Get-PRCheckLogs.ps1
  for log retrieval. Use for "fix ci", "why is ci failing", "debug ci failures".
license: MIT
metadata:
  domains:
    - github
    - ci-cd
    - debugging
    - automation
  type: workflow
  timelessness_score: 8
  inputs:
    - pr-number
    - current-branch
  outputs:
    - fixed-code
    - commit
    - ci-status
---

# Fix CI Skill

Autonomous workflow for debugging and fixing failing GitHub Actions CI checks.

---

## Triggers

| Phrase(s) | Action |
|-----------|--------|
| `fix ci`, `fix ci failures`, `fix failing checks` | Full autonomous fix workflow |
| `why is ci failing` | Analyze failures, report findings |
| `debug ci` | Fetch logs and analyze without fixing |
| `get ci logs for #123` | Fetch failure logs only |

---

## Quick Reference

| Phase | Script/Tool | Purpose |
|-------|-------------|---------|
| 1. Identify PR | `gh pr view --json` | Resolve target PR |
| 2. Check Status | `Get-PRChecks.ps1` | Get failing checks |
| 3. Fetch Logs | `Get-PRCheckLogs.ps1` | Extract failure snippets |
| 4. Analyze | Agent analysis | Categorize and plan fixes |
| 5. Implement | Edit/Write tools | Apply code changes |
| 6. Commit | Git operations | Push fixes |
| 7. Verify | `Get-PRChecks.ps1 -Wait` | Confirm CI passes |

---

## Process

### Phase 1: Identify Target PR

Determine which PR to analyze:

```text
Current branch has open PR? --> Use that PR
User specified PR number?   --> Use specified PR
Otherwise                   --> Ask user for PR number
```

**Command:**

```bash
gh pr view --json number,state,headRefName 2>/dev/null
```

**Failure Handling:** If no PR found, prompt user for PR number or URL.

### Phase 2: Fetch Check Status

Use the GitHub skill to retrieve CI check status:

```powershell
pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest <PR_NUMBER>
```

**Parse output to identify:**

- Failing checks: `Conclusion` in (FAILURE, CANCELLED, TIMED_OUT)
- Pending checks: `State` in (IN_PROGRESS, QUEUED)
- External checks: Non-GitHub Actions URLs (note as out-of-scope)

**Decision Point:**

- All passing --> Report success, exit
- Pending only --> Wait or report status
- Failures --> Continue to Phase 3

### Phase 3: Fetch Failure Logs

For failing GitHub Actions checks, retrieve logs:

```powershell
pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRCheckLogs.ps1 -PullRequest <PR_NUMBER> -MaxLines 200 -ContextLines 40
```

**Output structure:**

```json
{
  "CheckLogs": [
    {
      "Name": "build",
      "RunId": "12345678",
      "LogSource": "run-failed",
      "Snippets": [
        {
          "LineNumber": 142,
          "MatchedLine": "error TS2322: Type 'string' not assignable to 'number'",
          "Context": "... surrounding lines ..."
        }
      ]
    }
  ]
}
```

### Phase 4: Analyze Failures

For each failure snippet, determine:

**Error Type Classification:**

| Pattern | Category | Fixable |
|---------|----------|---------|
| `error CS\d+`, `error TS\d+` | Compile error | YES |
| `FAILED.*test`, `Expected.*Received` | Test failure | YES |
| `prettier.*check`, `eslint` | Lint/format | YES |
| `npm ERR!`, `dotnet restore failed` | Dependency | MAYBE |
| `secret.*not found` | Missing secret | NO (blocked) |
| `rate limit`, `timeout` | Infrastructure | RETRY |

**Root Cause Analysis:**

1. Identify affected file(s) and line numbers
2. Determine expected vs actual behavior
3. Check if error is in code we can modify

**Decision Matrix:**

- Fixable in code --> Continue to Phase 5
- Requires secrets/config --> Log as BLOCKED, skip
- Infrastructure issue --> Suggest workflow re-run

### Phase 5: Implement Fixes

For each fixable failure:

1. **Read** the relevant source file(s)
2. **Understand** the failure context from snippets
3. **Implement** the fix using Edit tool
4. **Validate locally** if possible:
   - Test failures: Run specific test
   - Lint errors: Run linter
   - Build errors: Attempt local build

**Do not stop for user approval.** Proceed autonomously.

### Phase 6: Commit and Push

After all fixes implemented:

```bash
git add -A
git commit -m "fix: resolve CI failures" \
  -m "- [List each fix made]" \
  -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push
```

### Phase 7: Verify

Wait for CI to re-run:

```powershell
pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRChecks.ps1 -PullRequest <PR_NUMBER> -Wait -TimeoutSeconds 300
```

**Report final status to user.**

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Fixing without reading logs | Guessing wastes time | Always fetch and analyze logs first |
| Modifying workflow YAML for quick fixes | Creates technical debt | Fix root cause in code |
| Ignoring external CI | Incomplete picture | Note external checks, provide URLs |
| Committing without local validation | May introduce new failures | Run local checks when possible |
| Stopping for approval on obvious fixes | Defeats autonomous purpose | Trust the analysis, proceed |
| Hardcoding run IDs | Brittle | Extract from URLs dynamically |

---

## Scope Limitations

### In Scope

- GitHub Actions workflow failures
- Build errors (compilation, syntax)
- Test failures (assertions, exceptions)
- Lint/format violations
- Code-level fixes in repository files

### Out of Scope (Note and Skip)

- External CI systems (Buildkite, CircleCI, Jenkins)
- Failures requiring secrets or environment variables
- Infrastructure issues (GitHub outages, rate limits)
- Workflows outside the repository
- Permissions or authentication failures

**For out-of-scope items, document:**

```text
SKIPPED: [Check Name]
Reason: [External CI | Requires secrets | Infrastructure issue]
Details URL: [URL for manual investigation]
```

---

## Verification Checklist

Before claiming completion:

- [ ] All failing checks analyzed
- [ ] Fixable errors addressed
- [ ] Out-of-scope items documented
- [ ] Changes committed and pushed
- [ ] CI re-run triggered
- [ ] Final status reported

---

## Extension Points

1. **Additional Error Patterns:** Add to Phase 4 classification table
2. **Local Validation Commands:** Extend Phase 5 for new languages/frameworks
3. **External CI Integration:** Future support for Buildkite, CircleCI APIs
4. **Retry Logic:** Auto-retry infrastructure failures
5. **Learning Loop:** Store successful fix patterns for future reference

---

## Dependencies

| Dependency | Type | Stability |
|------------|------|-----------|
| `gh` CLI | External | Stable |
| `Get-PRChecks.ps1` | Internal | Stable |
| `Get-PRCheckLogs.ps1` | Internal | Stable |
| GitHub Actions API | External | Stable |
| PowerShell 7+ | External | Stable |

---

## Example Session

```text
User: fix ci

Agent: Checking PR status for current branch...
       PR #456 has 2 failing checks.

       Fetching failure logs...

       FAILURE 1: build (ubuntu-latest)
       Error: src/utils.ts(42,5): error TS2322: Type 'string' is not assignable to type 'number'

       FAILURE 2: test (ubuntu-latest)
       Error: FAIL src/__tests__/utils.test.ts
              Expected: 42
              Received: "42"

       Analyzing... Both failures stem from type mismatch in src/utils.ts:42

       Implementing fix...
       [Edit src/utils.ts - convert string to number]

       Running local validation: npm test -- utils.test.ts
       Tests pass locally.

       Committing and pushing...
       Waiting for CI...

       CI Status: All checks passing.
       Fix complete.
```

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| github | Parent skill with Get-PRCheckLogs.ps1 |
| pr-comment-responder | Handle CI failure comments on PRs |
| code-review | Review fixes before committing |
