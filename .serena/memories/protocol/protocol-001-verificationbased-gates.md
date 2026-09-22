<!-- placement: evidence; reason: dated compliance measurements that explain why the repository enforces gates in lefthook rather than in prose -->

# Protocol: Verification-Based Gates Beat Trust-Based Guidance

Authoritative owner: `.claude/rules/push-lock.md` and `lefthook.yml` carry the
live gates. This file keeps only the measurements that motivated them.

## Measurement (2025-12, session protocol era)

| Signal | Trust-based guidance | Verification-based blocking gate |
|---|---|---|
| Compliance | 0%, 5+ violations in Session 15 | 100%, never violated in Sessions 19-21 |
| User interventions per session | 5+ | 0 to 1 after gates landed |
| Violations requiring rework | 4 | 0 |
| Time lost to rework | 30 to 45 minutes | 0 to 5 minutes |
| Clean-outcome rate | 42% | 95% target |

The gate that held at 100% was the one whose evidence appeared in the
transcript as tool output. The guidance that failed was phrased as "agents
should remember to".

Two finer-grained counts from Session 15, both against trust-based wording:

- 3+ raw `gh` invocations in 10 minutes, with the skill that wraps them
  available and documented.
- 5+ user interventions for violations of preferences that were scattered
  across several memories rather than stated in one binding place.

## Why it still matters

The session protocol these numbers came from is retired (PR #5179). The
finding transfers: a requirement with no machine-checkable artifact is not
enforced, whatever its wording. The repository now expresses the same
conclusion as pre-commit and pre-push jobs instead of prose.

## Related

- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
