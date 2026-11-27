# A draft ADR called the causal graph a lossless derived cache, and the data said otherwise

**Atomicity**: 90%
**Category**: ADR review, derived data
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E053. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a documented rebuild flag prove that deleting a derived cache loses nothing?

## Conventional answer

A draft ADR (numbered 088 in the session) said deleting the causal graph destroys zero information. The graph could be rebuilt from surviving episodes.

## First-principles position

A cross-model review checked the deleted file instead of trusting the flag. Much of the graph held anonymous legacy contributions that no episode could regenerate. The flag was also named `--reset-graph`, not `--rebuild`. A documented rebuild path shows design intent. It does not show the rebuild matches the committed file.

## Evidence with limits

- The deleted graph held anonymous legacy contributions on 46 of 79 edges and 5 of 6 patterns (2026-07-28). Four edges had no contribution map.
- Those contributions cannot be reproduced from surviving episodes.
- The "rewrites every commit" claim failed too. The writer returned when no episode was staged, and only 104 of 1,834 commits touched the graph (2026-07-28).
- Limits: Counts come from one reviewer's read of the pre-removal file and were repeated in ADR-089 and its debate log. They were not re-run against the deleted graph. The draft ADR carried number 088 in the session, and main numbers it ADR-089.
- State on main at 1be533c496 (2026-11-26): fixed. ADR-089:59 records that provenance was anonymized with a synthetic placeholder key, and ADR-089:65 rewrites the claim to "not zero bytes that exist nowhere else".

## Decision

Treat a documented rebuild path as intent until a from-scratch rebuild is diffed against the committed file. State a derivability claim as "derivable except X", with X measured.

## Related

- `.serena/memories/adr/adr-038-reflexion-memory-schema.md`
- `.serena/memories/knowledge/chestertons-fence.md`
