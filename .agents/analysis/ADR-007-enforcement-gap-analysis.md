# ADR-007 Enforcement Gap Analysis

**Date**: 2026-01-01
**Purpose**: Identify gaps in ADR-007 "Memory-First Architecture" enforcement and propose bulletproof solutions.

---

## Executive Summary

ADR-007 mandates: "Memory retrieval MUST precede reasoning in all agent workflows."

**Current enforcement is trust-based, not verification-based.** The system relies on agents self-reporting checklist completion rather than technical controls that block non-compliant behavior.

**Gaps identified**: 5 critical gaps across 4 enforcement layers
**Recommendation**: Expand Issue #584 scope OR create new Issue for enforcement mechanisms

---

## Current Enforcement Layers

### Layer 1: Documentation (CLAUDE.md, SESSION-PROTOCOL.md)

| Control | Status | Verification |
|---------|--------|--------------|
| CLAUDE.md blocking gate section | Exists | Trust-based |
| SESSION-PROTOCOL Phase 2 requirements | Exists | Trust-based |
| Memory-index routing table | Exists | Not enforced |

**Gap**: Documentation states requirements but has no technical enforcement.

### Layer 2: Session Validation (scripts/Validate-Session.ps1)

| Control | Status | Verification |
|---------|--------|--------------|
| Session Start checklist format | Enforced | Pre-commit blocks if missing |
| Session End checklist format | Enforced | Pre-commit blocks if missing |
| MUST rows must be checked | Enforced | Pre-commit blocks if unchecked |
| Evidence column content | **NOT VERIFIED** | Trust agent self-report |
| Memory names in Evidence | **NOT VERIFIED** | No cross-reference |

**Gap**: Validation checks the checkbox is marked [x] but does NOT verify Evidence column contains actual memory names or cross-reference against memory-index.

### Layer 3: Pre-commit Hook (.githooks/pre-commit)

| Control | Status | Verification |
|---------|--------|--------------|
| Session log exists | Enforced | Blocks if missing |
| Session log format valid | Enforced | Blocks if invalid |
| Memory index validation | Enforced | Blocks if index broken |
| Memory retrieval evidence | **NOT CHECKED** | No verification |

**Gap**: Hook validates session log format but not memory retrieval content.

### Layer 4: Claude Code Hooks

| Control | Status | Notes |
|---------|--------|-------|
| `.claude/hooks/` directory | ✅ **EXISTS** | Created 2026-01-01 |
| Session start hook | ✅ **IMPLEMENTED** | `session-start-memory-first.sh` |
| Pre-prompt hook | ✅ **IMPLEMENTED** | `user-prompt-memory-check.sh` |
| Hooks registered in settings | ✅ **CONFIGURED** | `.claude/settings.json` updated |

**Resolved**: Claude Code hooks now enforce ADR-007 at runtime. Session start injects Phase 1/2 requirements, user prompt hook provides ongoing reminders for planning/implementation tasks.

---

## Critical Gaps Summary

| # | Gap | Impact | Severity | Status |
|---|-----|--------|----------|--------|
| 1 | No Claude Code hooks | No runtime enforcement | P0 | ✅ **RESOLVED** |
| 2 | Evidence column not verified | Agents can self-report false completion | P0 | ⏳ Pending |
| 3 | skill-usage-mandatory memory missing | Referenced but doesn't exist | P1 | ✅ **RESOLVED** |
| 4 | Memory-index not cross-referenced | Task-memory mapping not enforced | P1 | ⏳ Pending |
| 5 | Forgetful not verified in workflows | copilot-setup-steps starts it but not verified | P2 | ⏳ Pending |

---

## Proposed Enforcement Mechanisms

### E1: Claude Code Hooks (P0) - ✅ IMPLEMENTED

**Status**: Completed 2026-01-01 (Updated to PowerShell per ADR-005)

Created `.claude/hooks/` with session enforcement:

```text
.claude/hooks/
├── Invoke-SessionStartMemoryFirst.ps1   # Injects Phase 1/2 requirements at session start
└── Invoke-UserPromptMemoryCheck.ps1     # Injects memory-first reminder for planning tasks
```

**Configuration** (`.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "pwsh -NoProfile -File ..." }] }],
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "pwsh -NoProfile -File ..." }] }]
  }
}
```

**Behavior**:

- **SessionStart**: Injects blocking gate requirements (Serena init + context retrieval)
- **UserPromptSubmit**: Detects planning/implementation keywords and injects memory-first reminder
- **Cross-platform**: PowerShell Core works on Windows, macOS, and Linux

### E2: Enhanced Session Validation (P0) - UPDATE

Update `scripts/Validate-Session.ps1` to:

1. **Extract Evidence column content** for memory-related rows
2. **Parse memory names** from Evidence (e.g., "memory-index, skills-pr-review-index")
3. **Verify memories exist** in `.serena/memories/`
4. **Cross-reference against task keywords** in session description

Example validation logic:
```powershell
# Extract memory evidence
$memoryRow = $sessionStartRows | Where-Object { $_.Step -match 'memory-index' }
$evidenceMemories = $memoryRow.Evidence -split ',' | ForEach-Object { $_.Trim() }

# Verify each memory exists
foreach ($mem in $evidenceMemories) {
    if (-not (Test-Path ".serena/memories/$mem.md")) {
        Fail 'E_MEMORY_NOT_FOUND' "Evidence claims memory '$mem' but file not found"
    }
}
```

### E3: Create skill-usage-mandatory Memory (P1) - ✅ IMPLEMENTED

**Status**: Completed 2026-01-01

Created `skill-usage-mandatory` memory in Serena (`.serena/memories/usage-mandatory.md`):

**Content Summary**:

- **Trigger**: Before ANY GitHub operation (PR, issue, comment, etc.)
- **Requirement**: Check `.claude/skills/github/scripts/` for existing skills before writing inline code
- **Enforcement**: MUST be read during Session Start per SESSION-PROTOCOL Phase 2

This resolves the gap where CLAUDE.md referenced a memory that didn't exist.

### E4: Pre-commit Memory Evidence Check (P1) - UPDATE

Add to `.githooks/pre-commit`:

```bash
#
# Memory Evidence Validation (ADR-007)
#
# Validates that Session Start checklist contains actual memory names
# in the Evidence column, not just checked boxes.
#

if [ -n "$STAGED_SESSION_LOG" ]; then
    echo_info "Validating memory retrieval evidence (ADR-007)..."

    # Check Evidence column contains memory names
    if ! grep -E '\|\s*MUST\s*\|.*memory-index.*\|\s*\[x\]\s*\|.*[a-z]+-[a-z]+-' "$STAGED_SESSION_LOG" > /dev/null; then
        echo_warning "Memory retrieval evidence may be incomplete"
        echo_info "  Ensure Evidence column lists actual memory names read"
    fi
fi
```

### E5: Forgetful Verification in Workflows (P2)

Update `copilot-setup-steps.yml` to verify Forgetful is actually working:

```yaml
- name: Verify Forgetful MCP operational
  run: |
    # Query Forgetful to verify it responds
    RESPONSE=$(curl -s -X POST http://localhost:8020/mcp \
      -H "Content-Type: application/json" \
      -d '{"method":"list_tools"}' 2>&1 || echo '{}')

    if echo "$RESPONSE" | grep -q "error"; then
      echo "::warning::Forgetful MCP not responding correctly"
    else
      echo "Forgetful MCP verified operational"
    fi
```

---

## Relationship to Issue #584

**Issue #584 Scope** (unchanged - Serena Integration Layer):

- Serena MCP client wrapper
- State persistence to session-current-state memory
- State recovery on MCP restart
- Graceful fallback when Serena unavailable

**Issue #729 Created** (ADR-007 Enforcement - linked to #584):

- <https://github.com/rjmurillo/ai-agents/issues/729>
- Tracks all enforcement mechanisms (E1-E5)
- Linked as related work to Issue #584

| Task | Status | Tracked In |
|------|--------|------------|
| E1: Claude Code Hooks | ✅ Complete | Issue #729 |
| E2: Enhanced Session Validation | ⏳ Pending | Issue #729 |
| E3: skill-usage-mandatory Memory | ✅ Complete | Issue #729 |
| E4: Pre-commit Evidence Check | ⏳ Pending | Issue #729 |
| E5: Forgetful Workflow Verification | ⏳ Pending | Issue #729 |

---

## Implementation Priority

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 | E1: Claude Code Hooks | 2h | Prevents all violations at runtime |
| P0 | E2: Enhanced Session Validation | 2h | Catches violations at commit time |
| P1 | E3: skill-usage-mandatory | 0.5h | Fills documentation gap |
| P1 | E4: Pre-commit Evidence Check | 1h | Early warning system |
| P2 | E5: Forgetful Verification | 1h | CI reliability |

**Total effort**: ~6.5 hours

---

## Success Criteria

ADR-007 is bulletproof when:

1. [x] Claude Code hooks inject memory-first requirements (E1) ✅
2. [ ] Session validation fails if Evidence column lacks memory names (E2)
3. [ ] Pre-commit warns on suspicious evidence patterns (E4)
4. [x] skill-usage-mandatory memory exists and is referenced (E3) ✅
5. [ ] Forgetful startup is verified in CI (E5)

---

## Related Documents

- ADR-007: Memory-First Architecture
- SESSION-PROTOCOL.md
- Issue #584: Serena Integration Layer
- Issue #729: ADR-007 Bulletproof Enforcement
- .githooks/pre-commit
- scripts/Validate-Session.ps1
- .claude/hooks/ (E1 implementation)
- .claude/settings.json (hooks configuration)
