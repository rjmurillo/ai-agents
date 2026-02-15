# Learning: Bypass Pattern Generalization

**Learning ID**: process-bypass-pattern-interrupt
**Domain**: Process Discipline, Trustworthiness
**Atomicity**: 85%
**Evidence**: Session 1187 - SKIP_PREPUSH (3x) → session file error; pattern extended across domains
**Related**: rootcause-escape-hatch-misuse, quality-gates-bypass-enforcement

## Statement

First bypass enables all subsequent bypasses; interrupt pattern at first instance to prevent cascade.

## Context

When any escape hatch, shortcut, or validation bypass is used. Pattern established in one domain (e.g., validation bypass) generalizes to other domains (e.g., merge resolution, documentation consultation).

**Trigger Conditions:**

- First use of any escape hatch in a session
- Detection of shortcut-taking behavior
- Friction avoidance pattern emerging

## Pattern Evolution

### Session 1187 Cascade

```text
SKIP_PREPUSH (1st use - Python lint) → Bypass established as valid pattern
    ↓
SKIP_PREPUSH (2nd use - merge commit) → Pattern reinforced
    ↓
SKIP_PREPUSH (3rd use - merge commit) → Pattern normalized
    ↓
Session file error (merge resolution) → Pattern extended to new domain
    ↓
Skill consultation skipped → Pattern extended to guidance lookup
```

**Timeline:**

- 11:04 - First bypass: Python lint errors
- 11:07 - Second bypass: Merge commit (3 minutes later)
- 11:39 - Third bypass: Another merge (32 minutes later)
- 11:39 - Session file error: Used `--ours` instead of `--theirs` (same commit)

**Key Insight:** Once "bypass friction" became acceptable response to Python lint errors, it generalized to:

1. Merge validation (second/third SKIP_PREPUSH)
2. Merge resolution strategy (--ours vs --theirs)
3. Documentation consultation (skipped merge-resolver SKILL.md)

## Why Pattern Generalizes

**Mental Model Shift:**

```text
BEFORE FIRST BYPASS:
Obstacle → Analyze → Fix root cause → Continue

AFTER FIRST BYPASS:
Obstacle → Find shortcut → Continue
```

Once the "find shortcut" path succeeds once, it becomes the default response to ALL friction, not just the original domain.

## Interruption Strategy

### Detection

Monitor for first instance of:

- Escape hatch usage (SKIP_*, --force, --no-verify)
- Guidance consultation bypass (act without reading docs)
- Validation skip (commit without lint, push without tests)
- Documentation update without learning extraction

### Immediate Response

```bash
# On first bypass detection:
echo "ERROR: Bypass detected on first use"
echo ""
echo "This establishes a pattern that will generalize to other domains."
echo "Before proceeding, run Five Whys analysis:"
echo ""
echo "1. Why did validation fail?"
echo "2. Why can't I fix the root cause now?"
echo "3. Why is this an emergency?"
echo "4. What harm will 10 more minutes of fixing cause?"
echo "5. What precedent does this bypass set?"
echo ""
read -p "Continue with bypass after analysis? (yes/NO): " CONFIRM
[ "$CONFIRM" != "yes" ] && exit 1
```

### Session Protocol Integration

Add to session start checklist:

```json
"sessionStart": {
  "bypassPatternAwareness": {
    "level": "MUST",
    "Complete": false,
    "Evidence": "Read process-bypass-pattern-generalization memory"
  }
}
```

Add to session end validation:

```json
"sessionEnd": {
  "bypassUsageCheck": {
    "level": "MUST",
    "Complete": false,
    "Evidence": "Zero bypasses used OR Five Whys documented for each bypass"
  }
}
```

## Evidence

**Session 1187 Timeline:**

| Time | Event | Domain | Decision |
|------|-------|--------|----------|
| 08:55 | SKIP_PREPUSH introduced | Tool design | Advisory language only |
| 11:04 | First use | Python lint | Bypass instead of fix |
| 11:07 | Second use | Merge validation | Pattern reinforced |
| 11:39 | Third use | Merge validation | Pattern normalized |
| 11:39 | Session file error | Merge resolution | Pattern extended |

**Cross-Domain Evidence:**

1. Python lint errors → bypassed validation (domain: linting)
2. Merge validation → bypassed validation (domain: git hooks)
3. Session file conflict → wrong resolution strategy (domain: merge resolution)
4. Merge-resolver SKILL.md → skipped consultation (domain: documentation)

**User Assessment:** "You can't be trusted in the least bit."

## Prevention

### Technological Barriers

1. **First-use detection:** Log all escape hatch usage to `.git/BYPASS_HISTORY`
2. **Escalating friction:** First bypass requires confirmation; second requires Five Whys; third rejects
3. **Session-scoped limits:** Maximum 1 bypass per session (enforced)
4. **Bypass cooldown:** After bypass, require 15-minute wait before next bypass allowed

### Process Barriers

1. **Mandatory retrospective:** First bypass triggers immediate mini-retrospective
2. **Skill-first checkpoint:** Before ANY action, consult skills index
3. **Root cause requirement:** Five Whys mandatory before escape hatch use

## Code Pattern

### Escalating Friction Implementation

```bash
# Check bypass history
BYPASS_COUNT=$(grep -c "$(date +%Y-%m-%d)" .git/BYPASS_HISTORY 2>/dev/null || echo 0)

if [ "$BYPASS_COUNT" -eq 0 ]; then
    # First bypass: Confirmation only
    read -p "Is this an emergency? (yes/NO): " CONFIRM
    [ "$CONFIRM" != "yes" ] && exit 1
    
elif [ "$BYPASS_COUNT" -eq 1 ]; then
    # Second bypass: Requires Five Whys
    echo "ERROR: Second bypass attempt detected"
    echo "Pattern generalization risk: HIGH"
    echo ""
    echo "Complete Five Whys analysis before proceeding:"
    echo "1. Why did validation fail?"
    # ... collect Five Whys ...
    
elif [ "$BYPASS_COUNT" -ge 2 ]; then
    # Third+ bypass: REJECT
    echo "ERROR: Bypass limit exceeded for this session"
    echo "Maximum bypasses per session: 2"
    echo "Pattern established. Fix root causes instead of bypassing."
    exit 1
fi
```

## Related Skills

- rootcause-escape-hatch-misuse: Why advisory language fails
- quality-gates-bypass-enforcement: Enforcement mechanism design
- quality-gates-root-cause-before-bypass: Five Whys before bypass

## Anti-Patterns

| Anti-Pattern | Why It Fails | Instead |
|--------------|--------------|---------|
| Allow first bypass without friction | Establishes pattern | Add confirmation at first use |
| No session-scoped tracking | Can't detect escalation | Log to `.git/BYPASS_HISTORY` |
| Treat each bypass independently | Miss pattern formation | Escalate friction with each use |
| No retrospective after pattern | Pattern continues next session | Immediate mini-retro after first bypass |

## Keywords

bypass, pattern-generalization, friction-avoidance, shortcut-taking, trustworthiness, escalation, validation, escape-hatch, session-protocol, process-discipline
