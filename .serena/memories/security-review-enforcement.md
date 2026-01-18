# Security Review Enforcement

## Skill-Security-009: Domain-Adjusted Signal Quality (88%)

**Statement**: Security review comments from any reviewer have higher actionability than style suggestions - adjust triage priority accordingly.

**Context**: When triaging bot review comments on security-sensitive files

**Evidence**: PR #52 - CodeRabbit style suggestions ~30% actionable overall, but security suggestion on .githooks was 100% valid (TOCTOU vulnerability)

**Heuristic**:

| Comment Domain | Base Signal | Adjustment |
|----------------|-------------|------------|
| Bug report | Use base | No change |
| Style suggestion | Use base | No change |
| Security issue | +40% | Always investigate |
| .githooks file | +50% | ASSERTIVE enforcement |
| Workflow file | +30% | Check for injection |

**Triage Pattern**:

```text
1. Is comment about security? → Always investigate
2. Is file in .githooks/? → ASSERTIVE enforcement
3. Is file in .github/workflows/? → Check for injection patterns
4. Otherwise → Use base signal quality
```

**Source**: `.agents/retrospective/pr-52-symlink-retrospective.md`

## Skill-Security-010: Pre-Commit Bash Detection (95%)

**Statement**: Enforce ADR-005 with pre-commit hook rejecting bash in `.github/workflows/` and `.github/scripts/`.

**Context**: When implementing or reviewing workflow files

**Evidence**: PR #60 bash code caused CWE-20/CWE-78, would have been caught by grep-based hook

**Pattern**:

```bash
# .githooks/pre-commit
STAGED=$(git diff --cached --name-only)

# Check for bash in workflows
if echo "$STAGED" | grep -E '^\.github/(workflows|scripts)/.*\.(yml|yaml)$'; then
    if git diff --cached | grep -E '^\+.*shell: bash'; then
        echo "ERROR: Bash not allowed in workflows (ADR-005)"
        echo "Use PowerShell (pwsh) instead"
        exit 1
    fi
fi
```

**Why PowerShell over Bash**:

- Stronger type system prevents injection
- Better error handling with `$ErrorActionPreference`
- Cross-platform consistency (Windows, Linux, macOS)
- Avoids shell metacharacter vulnerabilities (CWE-78)

**Anti-Pattern**: Trusting manual review to catch ADR violations

**Source**: `.agents/retrospective/2025-12-20-pr-211-security-miss.md`

## Related

- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
- [security-004-security-event-logging](security-004-security-event-logging.md)
- [security-007-defense-in-depth-for-cross-process-security-checks](security-007-defense-in-depth-for-cross-process-security-checks.md)
- [security-008-first-run-gap-analysis](security-008-first-run-gap-analysis.md)
