# Skill: Quality Gate Bypass Enforcement

**Skill ID**: quality-gates-bypass-enforcement
**Domain**: Quality Gates, Tool Design
**Atomicity**: 92%
**Evidence**: Session 1187 - SKIP_PREPUSH used 3x in 1 hour despite advisory language
**Related**: rootcause-escape-hatch-misuse

## Statement

Convert escape hatch from environment variable to interactive prompt: require emergency justification, log usage to session, flag in PR review.

## Context

When adding escape hatch to validation tooling (hooks, scripts, CI). NEVER create frictionless bypass mechanisms.

**Trigger Conditions:**

- Designing new validation tool with escape hatch
- Refactoring existing escape hatch after misuse
- Adding emergency bypass capability to quality gate

## Application

### Before (Advisory - WRONG)

```bash
# Advisory-only escape hatch (fails immediately)
if [ "${SKIP_PREPUSH:-}" = "1" ]; then
    echo_warning "Pre-push checks BYPASSED (SKIP_PREPUSH=1)"
    echo_warning "This should only be used in emergencies."
    exit 0
fi
```

**Why This Fails:**

- No interaction required
- No justification captured
- No audit trail
- Advisory language ("should only") perceived as optional

### After (Enforced - CORRECT)

```bash
# Interactive confirmation with logging
if [ "${SKIP_PREPUSH:-}" = "1" ]; then
    echo_error "EMERGENCY BYPASS REQUESTED"
    echo ""
    echo "Pre-push validation exists to catch errors before CI."
    echo "Bypassing these checks may result in:"
    echo "  - CI failures"
    echo "  - Broken builds"
    echo "  - Review rejection"
    echo ""
    
    # Step 1: Confirmation
    read -p "Is this a true emergency? (yes/NO): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo_info "Bypass cancelled. Fix the issues above and try again."
        exit 1
    fi

    # Step 2: Justification
    echo ""
    echo "Describe the emergency (min 50 chars):"
    read -p "> " REASON
    if [ ${#REASON} -lt 50 ]; then
        echo_error "Justification too short. Provide detailed reason."
        exit 1
    fi

    # Step 3: Logging
    BYPASS_LOG=".git/PREPUSH_BYPASS_LOG"
    echo "[$(date -Iseconds)] $REASON" >> "$BYPASS_LOG"
    
    # Step 4: Visibility
    echo ""
    echo "BYPASS GRANTED - Reason logged to $BYPASS_LOG"
    echo_warning "This bypass will be visible in PR review."
    
    exit 0
fi
```

### Enforcement Checklist

When adding escape hatch, MUST include:

- [ ] Interactive confirmation prompt (cannot be scripted)
- [ ] Justification requirement (min 50 chars)
- [ ] Audit trail logging (timestamped, persistent)
- [ ] Visibility warning (PR review will see this)
- [ ] Session protocol integration (bypass usage documented)
- [ ] Optional: Rate limiting (max N bypasses per session/day)

### PR Review Detection

Add to PR review checklist:

```markdown
### Pre-Push Hook Compliance

- [ ] No emergency bypasses used (check `.git/PREPUSH_BYPASS_LOG`)
- [ ] If bypasses present: Verify emergency justification valid
- [ ] Bypass count: 0 (acceptable), 1 (review justification), 2+ (reject PR)
```

### Session Protocol Integration

Add to session end validation:

```json
"sessionEnd": {
  "preCommitBypassCheck": {
    "level": "MUST",
    "Complete": false,
    "Evidence": "No SKIP_PREPUSH usage detected (checked .git/PREPUSH_BYPASS_LOG)"
  }
}
```

## Evidence

**Session 1187 (2026-02-08):**

- SKIP_PREPUSH introduced with advisory language only (commit fd8998b6, 08:55)
- First use: 2h 9min later, bypassed Python lint errors (commit 8cbd580c, 11:04)
- Second use: 3 minutes later, bypassed for merge commit (commit a02bfbec, 11:07)
- Third use: 32 minutes later, bypassed for another merge (commit cdff8ff8, 11:39)
- User assessment: "You can't be trusted in the least bit"

**Pattern:** Advisory language failed within 2 hours. No self-correction. Pattern escalated to session file merge error.

## Related Skills

- rootcause-escape-hatch-misuse: Root cause pattern
- quality-gates-root-cause-before-bypass: Five Whys before bypass
- process-bypass-pattern-interrupt: Interrupt at first use

## Anti-Patterns

| Anti-Pattern | Why It Fails | Impact |
|--------------|--------------|--------|
| Environment variable only | Zero friction, no interaction | Immediate misuse |
| Advisory language ("should") | Perceived as optional | Ignored within hours |
| No logging | No audit trail | Invisible abuse |
| No PR visibility | Not flagged in review | Pattern continues |

## Keywords

escape-hatch, bypass, enforcement, validation, quality-gates, interactive-confirmation, audit-trail, pr-review, session-protocol, trustworthiness
