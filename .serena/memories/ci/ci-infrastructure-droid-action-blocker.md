# Factory-AI/droid-action: Incompatible with Repository Security Constraints

**Date**: 2026-01-16 (Updated: 2026-01-17)
**Category**: CI Infrastructure
**Status**: BLOCKING (Upstream issue filed)
**Upstream Issue**: https://github.com/Factory-AI/droid-action/issues/20
**Related**: ci-infrastructure-codeql-ruleset-friction, security-practices

## Problem

Factory-AI/droid-action cannot be used in repositories with "all actions must be pinned to full-length commit SHA" security constraints because it internally uses non-SHA-pinned action references.

**Error Message**:
```
The action actions/upload-artifact@v4 is not allowed in rjmurillo/ai-agents 
because all actions must be pinned to a full-length commit SHA.
```

## Root Cause

The Factory-AI/droid-action (both v1 tag and latest commit) internally uses:
```yaml
uses: actions/upload-artifact@v4
```

Repository rulesets that require SHA pinning apply recursively to ALL action dependencies, including:
1. Actions referenced directly in workflow files
2. Actions referenced by composite actions
3. Actions referenced by Docker container actions

## Investigation Evidence

### Current Repository Usage

.github/workflows/droid-review.yml (removed) and .github/workflows/droid.yml (removed):
```yaml
- uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
- uses: Factory-AI/droid-action@e3f8be9f34bb41b11e852e836cb64e81f13fba59 # v1
```

**Direct references are SHA-pinned** ✅

### Factory-AI/droid-action Internal Implementation

From https://raw.githubusercontent.com/Factory-AI/droid-action/v1/action.yml:
```yaml
- uses: actions/upload-artifact@v4  # NOT SHA-pinned ❌
  with:
    name: droid-review-debug-${{ github.run_id }}
    path: |
      ~/.factory/logs/droid-log-single.log
      ~/.factory/logs/console.log
```

### Version Analysis

| Identifier | SHA | Date | Status |
|------------|-----|------|--------|
| v1 tag | 65dab2847e1b4a8a24332cfdef116e4ac3777789 | 2026-01-09 | Contains non-pinned references |
| Latest commit | e3f8be9f34bb41b11e852e836cb64e81f13fba59 | 2026-01-12 | Contains non-pinned references |

**Conclusion**: No available version of Factory-AI/droid-action is compatible with SHA-pinning constraints.

## Security Constraint Context

**Repository Ruleset Configuration**:
- Rule: "Require actions to be pinned to full-length commit SHA"
- Scope: ALL actions (transitive dependencies included)
- Enforcement: Blocking (workflow fails at setup phase)

**Rationale** (per security-practices memory):
- Prevents supply chain attacks via tag manipulation
- Ensures immutable action versions
- Complies with SLSA Level 2+ requirements

## Attempted Resolutions

### ❌ Update to Latest Version
**Result**: Latest version still violates constraint

### ❌ Relax Security Constraint
**Result**: Rejected - constraint is intentional and aligned with industry best practices

### ❌ Fork and Fix
**Result**: Out of scope - requires maintaining fork and coordinating with Factory-AI updates

## Impact

**Workflows Affected**:
- .github/workflows/droid-review.yml (removed) - Auto-review on PR open
- .github/workflows/droid.yml (removed) - Manual @droid invocation

**Severity**: BLOCKING - Workflows fail at setup phase before any steps execute

**Workaround**: None available without modifying third-party action or security constraints

## Recommended Actions

### Short-term
1. Disable droid workflows on branches requiring SHA-pinned actions
2. Document this limitation in ADR or operational runbook
3. ✅ **DONE**: Filed upstream issue: https://github.com/Factory-AI/droid-action/issues/20

### Long-term
1. Evaluate alternative PR review automation tools:
   - GitHub Copilot (native GitHub integration)
   - Reviewable.io (external service, no action dependencies)
   - Custom review workflow using SHA-pinned actions
2. Consider conditional workflow execution based on ruleset configuration
3. Investigate GitHub Enterprise security policy inheritance vs. repository rules

## References

- Factory-AI droid-action repo: https://github.com/Factory-AI/droid-action
- GitHub Actions security hardening: https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions
- SLSA requirements: https://slsa.dev/spec/v1.0/requirements

## Related Memories

- `security-practices`: Repository security standards
- [ci-infrastructure-codeql-ruleset-friction](ci-infrastructure-codeql-ruleset-friction.md): Similar security constraint analysis
- [slsa-supply-chain](slsa-supply-chain.md): Supply chain security framework
