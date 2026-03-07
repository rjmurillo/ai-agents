# ADR-049: Pre-PR Validation Gates

## Status

Proposed

## Date

2026-02-24

## Context

PR #908 demonstrated the cost of creating pull requests without pre-submission validation:

- 228+ review comments generated
- 59 commits (exceeding the project atomic commit standard)
- 95 files changed in a single PR
- Blocking architect review findings ignored before submission

Current governance relies on advisory limits documented in PROJECT-CONSTRAINTS.md and SESSION-PROTOCOL.md. These limits are not enforced programmatically before PR creation. Post-PR enforcement through CI and code review catches violations too late. The PR is already created, reviewers are notified, and remediation requires additional commits that compound the problem.

### Forces

1. **Late feedback is expensive.** Review comments on an oversized PR generate rework cycles.
2. **Advisory limits are insufficient.** PR #908 proves agents ignore soft guidance under pressure.
3. **CI gates run after PR creation.** By that point, the damage (notification noise, reviewer burden) is done.
4. **Urgent fixes need an escape hatch.** A hard block with no bypass would impede incident response.

## Decision

All PRs MUST pass a local validation gate before creation. The gate checks:

| Check | Threshold | Source |
|-------|-----------|--------|
| Commit count vs. base branch | <=20 | Project atomic commit standard |
| Files changed | <=10 | Best practice for reviewable PRs |
| Lines added | <=500 | Best practice for reviewable PRs |
| No BLOCKING synthesis issues | 0 blocking | ADR review process |
| ADR compliance | All referenced ADRs valid | Architecture governance |

### Bypass Mechanism

A documented bypass flag (e.g., `--force` with a justification argument) allows overriding the gate. The bypass MUST:

1. Log the justification to the session log.
2. Add a `bypass:pre-pr-gate` label to the resulting PR.
3. Trigger a post-merge review of the bypass justification.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Status quo (advisory limits) | No friction | Proven ineffective (PR #908) | Agents ignore soft limits |
| Post-PR CI validation only | No local tooling needed | Late feedback, PR already polluted | Notification noise, reviewer burden |
| Soft warnings (non-blocking) | Low friction | Warnings ignored (session evidence) | Same failure mode as advisory |
| Hard block (no bypass) | Strict enforcement | Blocks urgent fixes | Impedes incident response |

### Trade-offs

- **Friction vs. quality.** The gate adds a step before PR creation. This friction is intentional. It prevents the higher cost of oversized PR review cycles.
- **Bypass risk.** The escape hatch could be abused. Mitigation: label tracking and post-merge review.
- **Maintenance burden.** The validation script requires upkeep as thresholds evolve. Mitigation: thresholds are configurable, not hardcoded.

## Consequences

### Positive

- Prevents scope explosion before PR creation (shift-left)
- Enforces governance automatically rather than relying on agent discipline
- Reduces reviewer burden by ensuring PRs meet size constraints
- Catches ADR compliance issues before review

### Negative

- Adds a required step to the PR creation workflow
- Requires maintenance of the validation script
- Bypass mechanism could be misused if not monitored

### Neutral

- Existing CI gates remain in place as a second layer of defense
- Session protocol updates needed to reference the new gate

## Implementation Notes

1. Create `scripts/validate_pr_readiness.py` implementing the checks above (ADR-042: Python for new scripts).
2. Update SESSION-PROTOCOL.md to add a MUST gate: "Run pre-PR validation before creating PR."
3. Integrate into the `push-pr` skill so the gate runs automatically.
4. Document the bypass process in PROJECT-CONSTRAINTS.md.

## Related Decisions

- ADR-008: Protocol Automation Lifecycle Hooks (hook infrastructure)
- ADR-035: Exit Code Standardization (script exit codes)
- ADR-042: Python-First Enforcement (scripting language choice)
- ADR-043: Scoped Markdownlint (linting before commit)

## References

- Issue #945: [ADR] Pre-PR Validation Gates
- Issue #934: Validation script implementation
- Issue #935: Protocol updates
- PR #908: Evidence of advisory limit failure
- `.agents/governance/PROJECT-CONSTRAINTS.md`: Current advisory limits

---

*Template Version: 1.0*
*GitHub Issue: #945*
