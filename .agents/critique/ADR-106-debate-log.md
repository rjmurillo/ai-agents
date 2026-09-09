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
The bullet is now split, and cites ADR-063:123-124 "Storage backends are out of
scope" as that record's own evidence that its decision survives whole.

**Corrected in Round 3.** The "cites ADR-037 twice" half of this finding is
false. ADR-063 cites ADR-037 six times and every one is the router pattern; the
store-topology clause cites ADR-007. The bullet's conclusion holds, its stated
basis did not.

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

**Corrected in Round 3.** Only two of the three are dead. The pre-commit hook is
live; ADR-042 renamed it. The seat, and this log, reasoned from a missing
filename rather than from the call path.

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

## Round 2: external review after the debate closed

Devin Review ran on `ca69c7d28` once the PR left draft and reported four
findings against ADR-106 and ADR-007. Recorded here because one of them
falsified a sentence six seats had read and passed.

### Confirmed and fixed

**ADR-106 Decision item 2 asserted an absolute the live code refutes.** The
sentence read "There is no supplementary tier and no second store to consult,
augment from, or fall back to." A second store is consulted on every search:
`.claude/skills/memory/scripts/search_memory.py:296` runs
`results += search_episodes(query, episodes_path, max_results)` over
`.agents/memory/episodes`. Item 2 also contradicted item 3 of the same ADR,
which already called the episode store surviving and ADR-038-governed. Item 2
now scopes "backend" to a store retrieval can route between and states the
episode tier explicitly.

**ADR-106 Decision item 3 attributed episode reading to the wrong module.** It
said the unified entry point is what "also reads" the episode store. `grep -i
episode` over `.claude/skills/memory/memory_core/memory_router.py` returns
nothing; `search_episodes` is defined and called in
`.claude/skills/memory/scripts/search_memory.py`. Corrected, with the grep and
the call site named.

This is the same failure mode the round-1 debate caught once already, when four
seats falsified "Every memory instruction an agent reads now names a store it
can actually reach." An unbounded quantifier about live behavior survived a
second time. The lesson for the next ADR of this shape: every sentence claiming
a store is not consulted needs a call-path check, not a design argument.

### Reviewed and not actioned, with reasons

**"Status edit adds substantive interpretation" (ADR-007:16-20).** Refuted by
repository precedent and by the criterion's own wording. #5574 requires that no
superseded ADR *body* is rewritten; `git diff origin/main...HEAD` on both
records touches only frontmatter `status` and `superseded-by` plus the Status
block, leaving Decision, Context and Consequences untouched. A Status block that
says what survives is the house convention: ADR-056 records that "the
schema-consistency principle ADR-028 established for PowerShell output objects
continues here", ADR-004 that "the body below is retained as historical
rationale", and ADR-036 carries an entire "Still operative as procedure"
paragraph.

**"Retired decisions remain live dependencies" (8 skills bound to ADR-007 or
ADR-037).** Real, already measured, and already disclosed in this ADR's Impact
on Dependent Components table with the count and the note that no validator
checks a declared ADR against its status. Fixing it here would widen an
architecture record into a repository-wide sweep, so it stays out, tracked under
#5574 and listed in Next Steps above.

**Corrected in Round 3.** An earlier wording called this "Stage 2 prose and
frontmatter work". Stage 2 merged on 2026-09-05 and its scope could not have
reached these files; see Round 3.

**"Amendments lack reverse pointers".** Already stated by the ADR itself, in
the paragraph recording that an amendment by reference leaves no trace in the
amended record and that `git grep "ADR-089"` across ADR-038 and ADR-063 returns
nothing six weeks on. It is the recorded dissent of the architect and
high-level-advisor seats, carried deliberately rather than discovered late.

## Round 3: pre-merge audit, 2026-09-09

Run before merge, after Round 2, at head `3e95632bb`. Fourteen agents: seven
file auditors over the diff, six lenses over the two review threads left open,
one completeness critic. Three false statements were confirmed against the tree
and are corrected in this push. All three are absence claims inferred from a
name rather than from a call path, which is the failure mode Round 2 named and
the retrospective in this PR classifies as failure mode 9.

**1. "None is live" about ADR-007's three confirmation mechanisms.** False for
the third. ADR-007:206 names a "Pre-commit hook: Validates session log
compliance (`scripts/Validate-SessionJson.ps1`)". The PowerShell file is gone,
but ADR-042 ported it: `scripts/validate_session_json.py` exists, and
`lefthook.yml:101-103` runs it on every commit as the `session-policy` job via
`scripts/validation/git_hook_policy.py session`. `git ls-files` matching no
`Validate-SessionJson` was treated as the mechanism being dead. It was renamed,
not retired. Corrected in the Confirmation section of ADR-106.

**2. "ADR-063 cites ADR-037 twice."** False on both the count and the
attribution. `grep -n "ADR-037"` over ADR-063 returns six lines: :63, :104,
:117, :122, :145, :284. All six are the router pattern. The store-topology
clause is a different sentence citing a different record, at ADR-063:118-119:
"Serena remains the / canonical store and Forgetful the supplementary store
(ADR-007)". Three seats converged on the paired-citation reading in Round 1 and
none opened ADR-063 to check which record the clause names. The Neutral bullet's
conclusion survives, because the clause is withdrawn either way; its stated
basis does not.

**3. "The rule binds memory files. Nothing extended it to ADR prose."** False,
in the retrospective this PR adds. `.claude/rules/universal.md` frontmatter is
`paths: ["**"]` with `priority: critical`, above the line "These rules apply to
every change in this repository". MUST NOT 9 at :89-95 names no artifact class.
`.claude/rules/knowledge-persistence.md:70` records that items 7, 8 and 9 were
moved into Universal Rules precisely "because they bind before you open any of
these trees". The absence-claim rule already bound this ADR while it was being
written. That makes the miss worse rather than differently scoped, and it
changes the remediation from extending a rule to enforcing one that already
binds.

**Also corrected, without having been false.** The Impact table understated the
agent tree at 44 lines across two trees; the real figure is 110 across six,
because `src/claude` (38), `.github/agents` (10), `src/copilot-cli/agents` (9)
and `src/vs-code-agents` (9) also carry it, and `.claude/agents` is
hand-maintained rather than generated from `templates/agents`
(`build/scripts/detect_agent_drift.py:33-34`, naming "the hand-maintained /
.claude/agents vs .github/agents" comparison). A new row discloses
`.serena/memories/adr/adr-037-accepted.md`, whose `**Status**: Accepted` line
and "Forgetful augmentation" decision this merge falsifies.

**The two open threads keep their conclusions and lose two false grounds.**
Neither finding blocks the merge: no validator reads `metadata.adr`, no
validator models amendments, and `.agents/architecture/README.md` regenerates
byte-identical on the merged tree, verified by running `build_all.py` inside a
worktree holding the actual merge result. But two grounds offered for deferring
them were wrong. Deferring because "Stage 2 owns it" fails on the merge date.
Deferring the reverse pointers because they would need an ADR schema change
fails twice: the convention already exists at body level in seven ADRs, with
`ADR-005:255-259` showing the exact `**Amended by**:` shape, and three of the
five amended records (ADR-038, ADR-064, ADR-070) are `proposed` rather than
"five accepted bodies". The replies were corrected before the threads were
resolved.

**Measurement.** Round 1: 6 seats, 0 P0, 19 P1, 14 P2; missed all three of the
above. Round 2: 1 external reviewer, caught 2 of the 2 sentences it examined,
did not examine these. Round 3: 14 agents, 3 blockers, each re-verified by hand
before any edit was made.
