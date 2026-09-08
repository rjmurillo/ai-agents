# ADR Debate Log: Serena-Only Memory Architecture

Record under review: `.agents/architecture/ADR-106-serena-only-memory-architecture.md`,
which supersedes ADR-007 (Memory-First Architecture) and ADR-037 (Memory Router
Architecture). Filed under issue #5574 Stage 3.

## Summary

- **Rounds**: 1
- **Outcome**: Consensus
- **Final Status**: accepted
- **Seats reporting**: 6 of 6
- **Votes**: 3 ACCEPT (independent-thinker, security, analyst), 3 DISAGREE_AND_COMMIT
  (architect, critic, high-level-advisor), 0 BLOCK
- **Findings**: 0 P0, 19 P1, 14 P2. All 19 P1 resolved in the record before commit.

## Round 1 Summary

### Key Issues Addressed

Four seats independently falsified the same sentence. The draft's first Positive
consequence read "Every memory instruction an agent reads now names a store it
can actually reach." The critic, independent-thinker, analyst and
high-level-advisor each disproved it separately: acceptance criterion 1 of
#5574 matches 45 files on this branch, 10 of them under `.claude/skills/`, and
`world-model-diagnostic/SKILL.md:97` and `:209` are live instructions rather
than history. The universal quantifier is gone and the residue is now recorded
as a Neutral consequence.

Three seats found that ADR-007's Security Considerations were orphaned. ADR-063
is accepted and implemented, and its Decision item 4 at :119-121 instructs every
memory sub-skill to inherit "ADR-007 Security Considerations, including memory
data classification and storage security rules". The draft carried no security
text at all, so on merge that inheritance would have pointed into a record the
index marks Do Not Cite. ADR-106 now carries those rules forward in a Security
Considerations section, dropping only the storage row made moot by the removal.

Three seats found the Neutral bullet about dependent records was true for
ADR-070 and false for ADR-063. ADR-063 cites ADR-037 twice for two different
things that share the word router: a skill-surface router that is alive, and a
store-topology clause that is withdrawn. The independent-thinker further
contradicted the Phase 0 research on which of the two breaks, and was right.
The bullet is now split, and cites ADR-063:123 "Storage backends are out of
scope" as that record's own evidence that its decision survives whole.

The analyst audited every quotation and every commit SHA. All quotations from
ADR-007, ADR-037 and ADR-089 verified character for character. Three factual
errors did not: the stage list omitted #5575, the pull request that actually
removed the server, and #5616; and the episode count was off by one because
`.agents/memory/episodes/` contains a `CLAUDE.md` alongside 750 episode files.
All three are corrected.

The architect required an `## Impact on Dependent Components` section, which
this repository's ADRs carry and the draft omitted, for a decision with 35
dependent instruction lines in `.claude/agents` and 9 more in
`templates/agents`. The high-level-advisor supplied the surface the draft was
silent on: 8 SKILL.md files bind ADR-007 or ADR-037 in `metadata.adr`, and no
validator checks a declared ADR against that ADR's status, so the drift is
silent. The section now exists and names all of it, marking the unrepaired rows
as unrepaired.

The critic found the draft declared the memory-first rule binding while all
three of ADR-007's stated confirmation mechanisms at :202-206 are dead:
SESSION-PROTOCOL Phase 2 is gone, session-log creation is discontinued, and
`scripts/Validate-SessionJson.ps1` is absent from the tree. ADR-106 now has a
Confirmation section that says so plainly rather than leaving the gap implied.

The critic also found the draft's claim that "memory access is now a direct read
of Serena" falsified by the shipped artifact:
`.claude/skills/memory/memory_core/memory_router.py:2` reads "Unified memory
access layer over Serena, the only memory backend." ADR-037's unified entry
point survived the decommission; only the two-backend reconciliation died. The
Decision now separates the two.

### Major Changes Made

- First Positive consequence scoped to what shipped; residue recorded as Neutral
  with its measurement and a pointer to the open AC1 rescope on #5574.
- Security Considerations section added, carrying ADR-007's Memory Integrity,
  Data Classification, Access Control and Storage Security forward.
- Confirmation section added, stating that ADR-007's three verification
  mechanisms are retired and that enforcement is thinner than ADR-007 described.
- Impact on Dependent Components section added, with measured counts per surface.
- Decision item 1 expanded to dispose of ADR-007's four Decision sub-items
  individually, two carried forward and two withdrawn.
- Decision item 3 rewritten: four two-backend specifications withdrawn, the
  unified entry point preserved and re-governed.
- Neutral bullet split between ADR-070 (inherited) and ADR-063 (withdrawn clause,
  surviving decision).
- Amended-by-reference list extended with ADR-064 and ADR-086 per the
  independent-thinker.
- Stage list corrected to nine pull requests including #5575 and #5616; episode
  count corrected from 751 to 750.
- Status section now names this debate log as the basis for `accepted` and
  records both lifecycle constraints that pin it.

### Agent Positions

| Agent | Position | Basis |
|-------|----------|-------|
| architect | DISAGREE_AND_COMMIT | Lineage machine-verified: reciprocal frontmatter on all three records, `check_adr_lifecycle.py` 0 violations across 106 records, index rows agree. Dissents on amend-by-reference discoverability. |
| critic | DISAGREE_AND_COMMIT | Method correct; draft asymmetric between what it withdraws and what survives. All four P1s fixable in ADR-106's own prose. |
| independent-thinker | ACCEPT | Built the amend-not-supersede case and it loses on ADR-037's totality. Contradicted the Phase 0 report on which ADR-063 citation breaks, and was right. |
| security | ACCEPT | Superseding is the safer move: leaving both accepted would leave live-looking security prose pointing at a decommissioned store. No live control removed. |
| analyst | ACCEPT | Every quotation and all merge SHAs verify. Filed the three factual corrections. |
| high-level-advisor | DISAGREE_AND_COMMIT | Decision and one-successor scoping both correct. AC1 is unsatisfiable by construction and must not block this ADR. |

### Recorded Dissent

**architect.** Would require a one-line Status pointer in ADR-038, ADR-063 and
ADR-070 rather than amend-by-reference alone. The mechanism has run six weeks
under ADR-089 and produced no discoverable pointer: `git grep "ADR-089"` across
ADR-038 and ADR-063 returns nothing, while ADR-038 still carries 24 lines
describing the tier ADR-089 deleted. Not blocking, because the supersession
lineage is correct and the gap is repairable later without unwinding this
change. ADR-106 now states the limitation in Decision item 7 rather than
inheriting it silently, which is the fallback the architect named.

**critic.** Would not accept the record as drafted; all four P1s were gaps of
omission with one root cause, an asymmetry between stated withdrawals and
unstated survivals. Not blocking because the decision itself is correct, and
the seat independently verified the contested piece of the method in its favor:
ADR-063 Decision item 4 is a scope declaration, not a decision about the router.

**high-level-advisor.** Would have enumerated the surface an agent loads before
the surface a human audits: eight SKILL.md files binding the retired records,
two naming the withdrawn router in prose. Not blocking; all three P1s were
fixable in ADR-106's prose. Now enumerated in Impact on Dependent Components.

### Next Steps

Unrepaired and deliberately out of scope for this record, which is an
architecture decision rather than a prose sweep:

1. Repoint the 35 `Memory Router` lines in `.claude/agents` and 9 in
   `templates/agents`, editing the template source rather than the mirror.
2. Repoint the 8 SKILL.md files whose `metadata.adr` names ADR-007 or ADR-037.
3. Decide the AC1 rescope on #5574. The criterion asks a grep to return nothing
   and cannot be satisfied while decommission guards must contain the token.

Items 1 and 2 belong to the Stage 2 prose surface under #5574. Item 3 is an
owner decision and is independent of this ADR.
