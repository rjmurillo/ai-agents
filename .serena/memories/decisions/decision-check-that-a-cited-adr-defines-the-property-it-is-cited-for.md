# ADR-107 cited ADR-080 for owner and expiry rules that it does not define

**Atomicity**: 90%
**Category**: ADR citations
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E150. State checked on main at 1be533c496 (2026-11-26).

## Question

Does ADR-080 define owner and expiry requirements for adapter decisions?

## Conventional answer

ADR-107 credited ADR-080 with defining owner and expiry rules for adapter decisions.

## First-principles position

ADR-080 sets the evidence bar for those decisions. Its manifest fields do not cover ownership or expiry. ADR-107 itself sets those requirements in conditions 5 and 6.

## Evidence with limits

- A review of ADR-080:71-136 found only evidence requirements in rules 1 through 6 (2026-11-20).
- The manifest fields were unit, model id, artifact path, `fixtures_sha`, and date (2026-11-20).
- Limits: One citation checked on 2026-11-20. The result does not cover other references to ADR-080.
- State on main at 1be533c496 (2026-11-26): fixed. `.project-toolkit/architecture/ADR-107-canonical-skill-contracts-and-harness-projections.md:712-714` assigns owner and expiry to ADR-107 itself.

## Decision

Open the cited ADR and verify that it defines the rule claimed by the citation.

## Related

- `.serena/memories/tasks/issue-2840-model-pin-migration.md`
