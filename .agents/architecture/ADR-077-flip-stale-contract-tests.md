---
id: ADR-077
status: proposed
date: 2026-06-29
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-077: Flip Stale Contract Tests

## Status

Proposed. This is a 90-day experimental governance rule. The review checkpoint is 2026-09-27.

## Date

2026-06-29

## Context

`TESTING-RIGOR.md` already requires positive, negative, and edge tests for new functions. That protects new behavior, but it does not make an author find tests that still assert an old observable contract.

A green suite can be a false pass when those stale assertions remain. The code changed, but the tests still encode the prior return value, exception type, public signature, output, side effect, or error message. Review then must catch a gap that the author could have found with a search before coding.

The repo evidence is issue #2791, which records this rule as the testing-rigor child of epic #2789. That issue traces the failure shape to the mirror-obligation synthesis in #2789. The raw graded sample that motivated #2789 is not present in this worktree, so this ADR does not rely on that uncommitted sample as independently verifiable evidence. It treats the rule as experimental and adds a review checkpoint.

## Decision

Add a governance rule to `.agents/governance/TESTING-RIGOR.md`: when a change alters an observable contract, the author must find and flip stale tests in the same diff.

The rule binds three actions:

1. Search the suite for the old behavior: old value, exception type, message string, public method name, output literal, side-effect assertion, or fixture field.
2. Update each stale assertion to the new contract.
3. Say in the commit body why the assertion changed.

Failing tests that assert the old contract are evidence. Authors must flip them, not delete them.

An observable contract means behavior a caller, operator, integration test, or downstream maintainer can observe without reading private implementation. The rule includes return values, exception types, public signatures, error messages, side effects, external calls, output ordering, and serialized fields. It excludes pure internal refactors where caller-visible behavior is unchanged.

## Prior Art Investigation

### What Currently Exists

- **Structure/pattern being changed**: `.agents/governance/TESTING-RIGOR.md` defines per-function test cases, coverage targets, and verification steps.
- **When introduced**: Created 2026-04-26 from PR #1756 review lessons.
- **Original author and context**: The rule was created after happy-path-only tests missed edge cases that bots later found.

### Historical Rationale

- **Why was it built this way?** The original rule focused on test absence and branch coverage. That matched the observed PR #1756 failure.
- **What alternatives were considered?** No recorded alternative covered stale assertions for old contracts.
- **What constraints drove the design?** The rule needed to be simple enough for pre-implementation use and review checks.

### Why Change Now

- **Has the original problem changed?** Yes. Issue #2791 records a separate failure mode: tests can exist while still encoding the old contract.
- **Is there a better solution now?** Yes. A required grep for the old behavior is cheap and directly targets stale assertions.
- **What are the risks of change?** Authors may update tests mechanically without proving the new contract. The rule mitigates that by requiring the commit body to explain why assertions changed.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep existing test rigor only | No new process; existing coverage rules stay stable | Does not catch tests that still assert old behavior | Leaves the #2791 failure mode open |
| Rely on reviewers to spot stale assertions | No author burden before coding | Reviewers see the diff after the miss; detection depends on memory and luck | Pushes a cheap author grep into late review |
| Require a grep and flipped stale assertions in the same diff | Directly targets the failure mode; low cost; creates commit evidence | Adds one more author step for contract changes | Chosen because it prevents a known false-pass shape before review |
| Mutation testing, snapshot testing, or consumer-driven contract tests | Tooling can find behavioral drift without relying on author memory | Higher setup cost; does not cover every language in this repo; snapshot churn can hide intent | Too large for this PR; the grep rule is the low-cost author gate |

### Trade-offs

The chosen option trades a small search step for fewer false green suites. It does not require new tooling. It does require authors to understand which observable contract changed.

## Consequences

### Positive

- Contract-changing fixes must update the tests that guard the old contract.
- Reviewers get commit-body evidence for why stale assertions changed.
- A green suite becomes stronger evidence because old-contract tests cannot silently remain.

### Negative

- Authors must spend time finding old assertions even when the change looks small.
- The rule can be misapplied to pure refactors with no observable contract change.
- Some old behavior may be implied by helpers or fixtures, so the grep target is not always obvious. Authors must name the search terms in the commit body when no stale tests are found.
- The rule is not CI-enforced. It relies on author discipline and reviewer checks during the 90-day trial.

### Neutral

- The rule changes author workflow, not runtime behavior.
- Existing coverage thresholds remain unchanged.

## Confirmation

Reviewers verify three items on contract-changing diffs:

1. The changed behavior is caller-visible.
2. The author searched for the old contract using relevant values, exception names, public method names, error strings, side-effect assertions, or fixture fields.
3. Any tests that asserted the old contract were flipped, not deleted, and the commit body explains why.

The critic agent template flags missing inverse tests and generated mirror drift. The implementer template names the inverse before coding. CI does not parse commit bodies for this rule in the first 90 days.

## Legacy Migration Strategy

**Migration Pattern**: Not Applicable.

**Rationale**: The rule applies to new contract-changing PRs after this ADR. Existing merged PRs are not backfilled. PRs already in review should apply the rule when they next change tests for an observable contract.

## Review Checkpoint

Reevaluate this rule on 2026-09-27. Keep it if it catches at least one stale old-contract assertion or prevents at least one review round. Remove or narrow it if it produces only ceremony.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.agents/governance/TESTING-RIGOR.md` | Direct | Add the stale-contract rule and evidence | Medium |
| `templates/agents/implementer.shared.md` and mirrors | Direct | Teach implementer to name inverse cases before coding | Medium |
| `templates/agents/critic.shared.md` and mirrors | Direct | Teach critic to flag missing inverse tests | Medium |
| PR review bots and maintainers | Indirect | Enforce the rule during review | Low |

## Implementation Notes

- Limit the rule to observable contract changes: return value, exception type, signature, error message, or equivalent externally observed behavior.
- Do not apply it to pure internal refactors when public behavior is unchanged.
- Keep the commit-body requirement. It distinguishes intentional assertion flips from mechanical test rewrites.
- Security-sensitive contract flips require security review before merge.

## Related Decisions

- ADR-023: quality gate prompt testing.
- ADR-057: prompt behavioral evaluation methodology.

## References

- `.agents/governance/TESTING-RIGOR.md`
- Issue #2789, mirror-obligation cognition epic.
- Issue #2791, testing-rigor child issue for stale old-contract tests.
