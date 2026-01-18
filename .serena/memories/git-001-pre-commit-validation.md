# Skill-Git-001: Pre-Commit Validation

## Statement

Block git commit if Validate-SessionEnd.ps1 exits non-zero; prevents incomplete session closures

## Context

Install pre-commit git hook at `.git/hooks/pre-commit` that validates session log checklist before allowing commit

## Evidence

**Mass failure (2025-12-20)**: 22 of 24 sessions (91.7%) closed without committing changes - no technical gate prevented this

**No validation tool**: Git commit succeeded even with incomplete Session End checklist

**Session 44**: Only compliant session committed changes correctly (manual compliance, no automated enforcement)

## Metrics

- **Atomicity**: 96%
- **Impact**: 10/10
- **Category**: git, validation, enforcement
- **Created**: 2025-12-20
- **Tag**: CRITICAL
- **Validated**: 1 (24-session analysis)

## Pattern

### Pre-Commit Hook Implementation

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Find most recent session log from today
SESSION_LOG=$(find .agents/sessions -name "$(date +%Y-%m-%d)-session-*.md" -type f -printf '%T@ %p\n' | sort -rn | head -1 | cut -d' ' -f2)

if [ -z "$SESSION_LOG" ]; then
    echo "Warning: No session log found for today. Skipping validation."
    exit 0
fi

# Validate Session End checklist
pwsh -File scripts/Validate-SessionEnd.ps1 -SessionLogPath "$SESSION_LOG"

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ COMMIT BLOCKED: Session End checklist incomplete"
    echo "   Session log: $SESSION_LOG"
    echo "   Fix: Complete all [x] checkboxes in Session End section"
    echo ""
    exit 1
fi

exit 0
```

### Validation Script Requirements

```powershell
# scripts/Validate-SessionEnd.ps1
# Exit code 0 = PASS (allow commit)
# Exit code 1 = FAIL (block commit)

# MUST check:
# - Session End section exists with correct format
# - All MUST requirements marked [x] (not [ ])
# - HANDOFF.md checkbox checked
# - Markdown lint checkbox checked
# - Commit SHA present or checkbox checked
```

## Verification

**Test on known-good session:**

```bash
.\scripts\Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/2025-12-20-session-44.md"
# Expected: Exit 0 (PASS)
```

**Test on known-bad session:**

```bash
.\scripts\Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/2025-12-20-session-46.md"
# Expected: Exit 1 (FAIL)
```

**Test commit blocking:**

```bash
# With incomplete checklist
git add .
git commit -m "test"
# Expected: BLOCKED with error message pointing to session log
```

## Success Criteria

- [x] Validate-SessionEnd.ps1 script exists
- [x] Pre-commit hook installed at `.git/hooks/pre-commit`
- [x] Hook executable (`chmod +x .git/hooks/pre-commit`)
- [x] Tested on session-44 (PASS expected)
- [x] Tested on session-46 (FAIL expected)
- [x] Commit blocked when checklist incomplete
- [x] Commit allowed when checklist complete

## Related Skills

- Skill-Protocol-005 (Template Enforcement)
- Skill-Protocol-002 (Verification-Based Gate Effectiveness)
- Skill-Orchestration-003 (Orchestrator Handoff Validation)

## Source

`.agents/retrospective/2025-12-20-session-protocol-mass-failure.md` (Learning 3, lines 680-697)
