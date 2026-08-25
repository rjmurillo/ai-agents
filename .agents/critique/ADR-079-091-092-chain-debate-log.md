# Debate Log: ADR-079, ADR-091, ADR-092 Supersession Chain

Change-set CS-2 of the corpus-repair batch. The batch-level record, roster, and
the transcription-versus-decision analysis are at
`.agents/critique/ADR-corpus-repair-5189-5201-debate-log.md`. This log carries
the chain-specific findings so the change-set stands on its own evidence.

## The defect

Three records disagreed about who superseded whom.

- ADR-091 declared `supersedes: [ADR-079]` and `superseded-by: ADR-092`.
- ADR-079 declared `superseded-by: ADR-092`, skipping ADR-091 entirely.
- ADR-092 declared `supersedes: [ADR-079, ADR-091]`.

ADR-091 said it retired ADR-079; ADR-079 named a different successor. Both
readings cannot hold. `check_adr_lifecycle.py` reported it as the corpus's
single `supersession-reciprocal` violation.

## The change

ADR-079 `superseded-by` moves to ADR-091. ADR-092 `supersedes` narrows to
`[ADR-091]`. ADR-091 is untouched; it was already correct.

`superseded-by` names the **immediate** successor, not a transitive one, so the
chain is ADR-079 to ADR-091 to ADR-092.

## Evidence

Verified from committed file content, not from history. This matters: the local
checkout is a shallow 50-commit clone, so `git log` cannot reach the original
commits and an absence there proves nothing.

1. ADR-091's own accepted Status prose reads "Supersedes ADR-079 (Plugin Version
   Bump Stays at PR Time)". No later record retracts it.
2. ADR-091's Status also reads "Superseded by ADR-092 (2026-08-01)", and ADR-092
   carries a section headed "Why ADR-091 is superseded within hours of landing".
3. The three `## Date` values order the records consistently: 2026-07-08,
   2026-07-31, 2026-08-01.
4. The only field inconsistent with all of the above was ADR-079's
   `superseded-by`.

Measured effect: `supersession-reciprocal` goes 1 to 0.

## Objections raised and answered

**"This is date-plus-prose archaeology in a shallow clone."** Raised by the
independent-thinker, then withdrawn by the same reviewer on inspection: ADR-091's
**committed and untouched** frontmatter already carried `supersedes: [ADR-079]`.
The direction was read off an existing committed field, not inferred from dates.

**"ADR-091 has `implemented: false`, so its mechanism never ran. Can a record
that never shipped supersede anything?"** Yes. Supersession is a governance edge,
not an implementation claim. ADR-091's `implemented: false` is precisely why
ADR-092 exists one day later, and the two-hop chain is what preserves that
history. Collapsing to ADR-079 to ADR-092 would erase the fact that ADR-091 was
accepted and then immediately replaced.

**"The alternative fix was never named."** Correct, and recorded here: the other
valid repair is to drop `supersedes: [ADR-079]` from ADR-091 and keep ADR-079
pointing at ADR-092. It was rejected because it contradicts ADR-091's own
accepted prose, which no record retracts.

**"The ratchet baseline now encodes this reconstruction."** True. With HEAD
versions of ADR-079 and ADR-092 restored into a scratch tree,
`supersession-reciprocal` measures 1; the committed baseline is 0. Correcting the
chain later would require a baseline edit and would read as a regression. Noted
rather than resolved.

## Verdicts

ACCEPT from all six roles. This was the least contested change-set in the batch:
it is the one repair where a committed field, not a prose reading, decided the
direction.

## Rendering consequence, deferred

`.agents/architecture/README.md`'s Retired table sends a reader from ADR-079 to
ADR-091, which is itself retired three rows below. Correct per the
immediate-successor rule, unhelpful at the corpus front door. The index generator
should walk `superseded-by` to the terminal live record. Raised by the architect
as P1-4; tracked separately.
