# Skill-Security-010: Pre-Commit Bash Detection

**Statement**: Enforce ADR-005 with pre-commit hook rejecting bash in `.github/workflows/` and `.github/scripts/`.

**Context**: When implementing or reviewing workflow files

**Evidence**: PR #60 bash code caused CWE-20/CWE-78, would have been caught by grep-based hook

**Atomicity**: 95%

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
