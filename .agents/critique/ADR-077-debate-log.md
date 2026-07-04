# ADR-077 Multi-Agent Debate Log

**ADR**: `.agents/architecture/ADR-077-flip-stale-contract-tests.md`
**Triggering context**: PR #2793 changes `.agents/governance/TESTING-RIGOR.md`; governance rules require an ADR for new governance rules.
**Date**: 2026-06-29
**Reviewers**: architect, critic, independent-thinker, security, analyst, high-level-advisor

---

## Round 1, Initial Review

### architect: DISAGREE-AND-COMMIT

P1 findings:

- Missing `## Confirmation` section. The ADR needed to state how compliance is verified.
- Missing `## Legacy Migration Strategy` section. Existing PRs and prior work needed a stated compatibility position.

P2 findings:

- `decision-makers: []` was empty.
- Strategic considerations were absent, but acceptable for a narrow process ADR if P1 items were fixed.

### critic: DISAGREE-AND-COMMIT

P1 findings:

- "Observable contract" was undefined, shifting burden back to reviewers.
- Commit-body evidence was not machine-enforceable and should not be represented as CI-enforced.

P2 findings:

- Pure-refactor misapplication risk needed a mitigation.
- The sample citation needed stronger evidence.

### independent-thinker: DISAGREE-AND-COMMIT

P1 findings:

- One uncommitted sample was too thin as the sole basis for a governance rule.
- Grep scope was not reliably defined and risked compliance theater.

P2 findings:

- Commit-body evidence is weak verification.
- Rule scope needed side effects, ordering, and other observable behavior.
- The rule needed a review or sunset point.

### security: DISAGREE-AND-COMMIT

P1 finding:

- Security-sensitive contracts were not distinguished from functional contracts. A security contract flip needed security review before merge.

P2 finding:

- The ADR should cross-reference security-review expectations.

### analyst: BLOCK

P1 findings:

- The cited sample #994 / `DefaultIfNotSingle` was not present in the worktree and could not be independently verified.
- Industry prior art was not surveyed.

P2 findings:

- Terminology differed between "signature" and "signature shape."
- Pure-refactor guidance needed a clearer mitigation.

### high-level-advisor: ACCEPT

P1 findings:

- `decision-makers: []` should be populated before merge.
- Empty grep results needed guidance so authors do not claim compliance from bad search terms.

P2 findings:

- Add a grep example in a follow-up if the rule stays after trial.

---

## Round 2, Resolution

The ADR was revised before convergence:

| Finding | Resolution |
|---|---|
| Unverifiable sample citation | Removed reliance on the raw graded sample. ADR now cites issues #2789 and #2791 and states the raw sample is not present in this worktree. |
| Thin evidence | Reframed the rule as a 90-day experimental governance rule with checkpoint `2026-09-27`. |
| Undefined observable contract | Added a definition: caller-visible behavior including return values, exception types, public signatures, error messages, side effects, external calls, output ordering, and serialized fields. |
| Grep scope undefined | Listed minimum search targets: old value, exception type, message string, public method name, output literal, side-effect assertion, or fixture field. |
| Commit-body enforcement ambiguity | Stated CI does not parse commit bodies during the first 90 days. Reviewer verification is the enforcement mechanism. |
| Missing confirmation | Added `## Confirmation` with three reviewer checks. |
| Missing legacy migration | Added `## Legacy Migration Strategy`; no backfill, forward-only rule. |
| Security contract flips | Added security review requirement for authentication, authorization, cryptography, error disclosure, and secret handling contract flips. |
| Prior art missing | Added mutation testing, snapshot testing, and consumer-driven contract testing as alternatives, with rejection rationale. |
| No exit criterion | Added keep/remove criteria at the 90-day checkpoint. |
| Empty decision-makers | Set `decision-makers: [rjmurillo]`. |

---

## Round 3, Convergence

| Reviewer | Final verdict | Notes |
|---|---|---|
| architect | ACCEPT | Confirmation, legacy migration, decision-makers, observable scope, and security clause are present. |
| critic | ACCEPT | Rule is now internally consistent, non-CI enforcement is explicit, and the 90-day trial bounds risk. |
| independent-thinker | ACCEPT | Evidence uncertainty is bounded by experimental framing; search scope and sunset conditions are defined. |
| security | ACCEPT | Security-sensitive contract flips now require security review; no remaining P0/P1 findings. |
| analyst | ACCEPT | Blocking evidence and prior-art findings are resolved. |
| high-level-advisor | ACCEPT | Rule is proportionate, bounded, and ready for merge after normal governance approval. |

**Consensus**: 6 ACCEPT, 0 BLOCK.

---

## Dissent and Known Limits

- The rule is not CI-enforced during the 90-day trial. Reviewers verify author evidence.
- The rule is supported by tracked issues and an experimental checkpoint, not by a committed full sample corpus.
- If the rule produces only ceremony by 2026-09-27, it should be removed or narrowed.
