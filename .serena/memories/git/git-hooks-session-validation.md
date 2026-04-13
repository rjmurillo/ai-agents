# Session Validation Pre-Commit Hook

**Statement**: Block commit if `Validate-SessionEnd.ps1` exits non-zero

**Context**: Enforcing session protocol compliance

**Evidence**: 91.7% (22/24) sessions closed without committing - no technical gate prevented this

**Atomicity**: 96%

**Impact**: 10/10 (CRITICAL)

## Implementation

```bash
#!/bin/bash
# .git/hooks/pre-commit

SESSION_LOG=$(find .agents/sessions -name "$(date +%Y-%m-%d)-session-*.md" \
    -type f -printf '%T@ %p\n' | sort -rn | head -1 | cut -d' ' -f2)

if [ -n "$SESSION_LOG" ]; then
    pwsh -File scripts/Validate-SessionEnd.ps1 -SessionLogPath "$SESSION_LOG"
    if [ $? -ne 0 ]; then
        echo "❌ COMMIT BLOCKED: Session End checklist incomplete"
        exit 1
    fi
fi
```

## Why This Matters

- Automated enforcement > trust-based guidance
- 100% compliance after gate added
- Prevents incomplete sessions from being committed

## Related

- [git-hooks-001-pre-commit-branch-validation](git-hooks-001-pre-commit-branch-validation.md)
- [git-hooks-002-branch-recovery-procedure](git-hooks-002-branch-recovery-procedure.md)
- [git-hooks-004-branch-name-validation](git-hooks-004-branch-name-validation.md)
- [git-hooks-autofix](git-hooks-autofix.md)
- [git-hooks-categories](git-hooks-categories.md)
