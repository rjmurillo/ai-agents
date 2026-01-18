# Skill: CI-002 Explicit Retry Timing

**Atomicity Score**: 88%
**Source**: Session 04 retrospective - Issue #338 implementation
**Date**: 2025-12-24
**Validation Count**: 1 (Commit 888cc39)
**Tag**: helpful
**Impact**: 7/10 (Improves debuggability, reduces timing uncertainty)

## Statement

Use explicit timing arrays (0 10 30) instead of backoff formulas for retry logic.

## Context

When implementing retry mechanisms with specific timing requirements (especially in CI where timing is critical).

## Evidence

Commit 888cc39 - Issue #338 retry implementation:

```bash
# Explicit timing array (RECOMMENDED)
RETRY_DELAYS=(0 10 30)  # seconds before each attempt

# Timing breakdown:
# Attempt 1: Wait 0s  (total elapsed: 0s)
# Attempt 2: Wait 10s (total elapsed: 10s)
# Attempt 3: Wait 30s (total elapsed: 40s)

for ATTEMPT in "${!RETRY_DELAYS[@]}"; do
    if [[ $ATTEMPT -gt 0 ]]; then
        DELAY=${RETRY_DELAYS[$ATTEMPT]}
        echo "::warning::Retrying in ${DELAY}s..."
        sleep "$DELAY"
    fi
    # ... attempt logic ...
done
```

## Why Explicit Timing Wins

### Anti-pattern: Computed Backoff

```bash
# AVOID: Backoff formula obscures timing
MAX_RETRIES=3
for ATTEMPT in $(seq 1 $MAX_RETRIES); do
    DELAY=$((2 ** ATTEMPT))  # What are the actual delays?
    sleep "$DELAY"
done
```

**Problems:**
- Timing not obvious from reading code
- Requires mental math to understand timing
- Hard to verify in CI logs
- Difficult to tune for specific requirements

### Correct Pattern: Explicit Array

```bash
# RECOMMENDED: Timing visible at declaration
RETRY_DELAYS=(0 10 30)  # Clear: 0s, 10s, 30s
```

**Benefits:**
- Timing requirements visible in code
- No mental math required
- Easy to verify in CI logs
- Simple to adjust for different contexts

## When to Use

Apply when:
- CI timing budgets matter (GitHub Actions minutes)
- Timing requirements are specific (per issue spec)
- Debugging retry behavior
- Communicating timing to stakeholders

Consider formula when:
- Large number of retries (10+)
- Exponential backoff required by API
- Timing is secondary concern

## Related Skills

- skill-ci-001-fail-fast-infrastructure-failures: When to stop retrying
- ci-quality-gates: Timeout budgets for different checks
- ci-ai-integration: API-specific retry requirements

## Success Criteria

- Retry timing visible in code without calculation
- CI logs show expected delays
- Easy to verify compliance with timing specs
- Simple to adjust timing based on feedback
