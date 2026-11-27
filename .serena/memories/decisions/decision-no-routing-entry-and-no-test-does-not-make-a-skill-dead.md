# Skills with no routing entry and no test were mostly not dead

**Atomicity**: 90%
**Category**: Skill inventory
**Source**: Agent session sweep, sessions dated 2026-09. Sweep ids E090. State checked on main at 1be533c496 (2026-11-26).

## Question

Is a skill with no routing table entry and no test dead weight?

## Conventional answer

A skill with no routing table entry and no test is dead weight and a deletion candidate.

## First-principles position

On 2026-09-17, a baseline listed 72 skills as neither routed nor tested. The wider audit counted mentions across session logs, episodes and recent PRs. Only two of the 111 audited skills had no hits (2026-09-17). The static check missed a routing entry in a plain table cell. Zero hits sets an upper bound on how many skills went unused.

## Evidence with limits

- A baseline listed 72 skills as neither routed nor tested (2026-09-17).
- Method: mentions in 1,467 session logs, 750 episodes and the last 200 PRs (2026-09-17).
- Of 111 audited skills, 2 had zero hits, 21 had one or two, and 88 had more (2026-09-17).
- security-review looked dead because autoplan routes it in a plain table cell the strict-form proxy missed.
- Limits: The strict-form proxy undercounts prose mentions, so zero hits is an upper bound on dead weight. Single-user corpus, 2026-09-17.
- State on main at 1be533c496 (2026-11-26): no repo artifact. A search for this finding on main found no match.

## Decision

Check activation history across logs, episodes and PRs before listing a skill for deletion. Do not delete on a static routing-plus-test check.
