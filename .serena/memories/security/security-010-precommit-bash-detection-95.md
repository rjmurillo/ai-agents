# Security: Precommit Bash Detection 95

> **IMPORTANT (2026-08-25, issue #5201)**: ADR-005 (PowerShell-only
> scripting) was superseded by ADR-042 (Python migration) on 2026-01-17.
> The pattern below, and its "Use PowerShell (pwsh) instead" message, are
> historical: current policy is Python for new scripts
> (`.claude/rules/universal.md` SHOULD-3), not PowerShell. The underlying
> security concern (CWE-78, shell-injection risk in generated CI code) is
> still valid and still worth a pre-commit hook; only the "PowerShell over
> Bash" prescription is stale. A current hook should reject unreviewed
> shell/bash in CI paths without mandating a specific replacement language.

## Skill-Security-010: Pre-Commit Bash Detection (95%)

**Statement (historical, see banner above)**: Enforce ADR-005 with pre-commit hook rejecting bash in `.github/workflows/` and `.github/scripts/`.

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

- [security-001-twophase-security-review](security-001-twophase-security-review.md)
- [security-002-input-validation-first-88](security-002-input-validation-first-88.md)
- [security-002-input-validation-first](security-002-input-validation-first.md)
- [security-003-secure-error-handling-90](security-003-secure-error-handling-90.md)
- [security-003-secure-error-handling](security-003-secure-error-handling.md)
