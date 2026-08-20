# ADR-078 debate log: tier-to-role vocabulary clarification

## Scope

Six-agent `adr-review` debate on the 2026-08-20 clarification to
`.agents/architecture/ADR-078-autoplan-orchestrator-router-boundary.md`, run
against branch `claude/pr-5174-merge-review-gvrype` at head `ecf597cc2`
(PR #5177, issue #5130).

**This is ADR-078's first independent review.** The record was authored
2026-07-04 and shipped without one. Read the verdict as covering the
clarification and whatever the six lenses found while reading the whole
document; it is not a retrospective ratification of the July decision.

## Why this debate ran

PR #5177 deletes the repository's four-tier agent hierarchy and replaces
`tier:` frontmatter with a functional `role:` field across 186 agent files.
ADR-078 described orchestrator as `metadata.tier: manager`, so the rename left
the record naming a field that no longer exists in any tree. Four reviewers
flagged it. The repository owner chose correction inside this PR over a
follow-up, which re-armed the `adr-review` trigger at `AGENTS.md:44`.

Before this run, the criterion sat unmet and disclosed rather than hidden. The
disclosure is preserved at
`.agents/critique/5130-tier-hierarchy-removal-debate-log.md:219-276`.

## Phase 0: detection

`uv run python .claude/skills/adr-review/scripts/detect_adr_changes.py --since-commit origin/main`
returns `Modified: [".agents/architecture/ADR-078-..."]`, `HasChanges: true`,
`RecommendedAction: "review"`, exit 0.

## Phase 1: independent review

Six agents reviewed in parallel, each against the Zimmermann 7-question
checklist and self-checked against the seven review anti-patterns.

| Agent | Vote | Headline finding |
|-------|------|------------------|
| architect | DISAGREE-AND-COMMIT | Implementation Notes named a script that does not write the file it claims to regenerate |
| critic | DISAGREE-AND-COMMIT | The Rationale cited `role:` as evidence for a routing constraint that this same PR declares non-enforcing |
| independent-thinker | DISAGREE-AND-COMMIT | The edit skipped the `date` bump the repository's own mutability rule requires, and left no in-file amendment trace |
| security | ACCEPT | Verified by search that nothing ever enforced the tier hierarchy: no control was removed |
| analyst | ACCEPT | Independently reproduced the 186/186 and six-tree role claims; both hold |
| high-level-advisor | ACCEPT | Correcting here was right; the gate that let the uncorrected version through is the real defect |

**Consensus: 3 ACCEPT, 3 DISAGREE-AND-COMMIT, 0 BLOCK.** One round.

## Phase 2: consolidation

### Where the lenses converged

**Four agents independently found the same defect in the correction itself.**
The first pass converted the skill-versus-agent axis from "tier" to "layer" in
two places and left it as "tier" in five. Line 212 ended up reading
"at skill tier ... at the agent layer" inside one sentence, six lines below
"skill-tier router". architect, critic, independent-thinker, and security each
found it separately. The document was consistently wrong before the edit and
half-converted after it, which is worse.

The independent-thinker supplied the constraint the others missed:
`.claude/skills/autoplan/SKILL.md:111` quotes ADR-078 and cites it by number,
and it said "skill tier". Converting the ADR alone would have desynced the
governing record from the governed surface, which is the exact failure class
issue #5130 exists to close.

**Two agents independently found the Rationale overclaiming.** critic (F1) and
security (finding 5) reached the same place from different directions: the
pre-edit sentence had a real mechanism behind it, since
`docs/orchestrator-routing-algorithm.md` carried `TIER_HIERARCHY`,
`AGENT_TIERS`, and a `validate_tier_sequence` that raised on upward delegation.
This PR deletes that function. The substitution kept the sentence's shape and
pointed it at `role:`, which `.agents/AGENT-SYSTEM.md:836-840`, added by this
same PR, defines as granting and withholding nothing at runtime. The record
would have shipped a Rationale its own PR contradicts.

**Three agents found the same missing guard.** Nothing scans `.agents/architecture/`
for stale references to renamed agent metadata. `tests/test_agent_role_metadata_migration.py`
pins the vocabulary in agent frontmatter, `.agents/AGENT-SYSTEM.md`, and
`docs/orchestrator-routing-algorithm.md`, and in none of the ADRs. CI catching
line 111 once was luck, not a standing gate.

### Where the lenses disagreed

**`status: proposed` with `implemented: true`.** critic called it a completeness
gap and said this debate is the moment to flip to `accepted`. architect read
ADR-073:54 as making the two fields orthogonal and ADR-073:61 as forbidding the
flip without debate evidence, concluding `proposed` is the only legal value.
high-level-advisor said track separately, do not fix here.

Resolved against critic, 2 to 1, on the text: ADR-073:61 binds a transition to
`accepted` to debate-log evidence under `.agents/critique/`. That evidence is
this file, which did not exist when the reviews ran. The flip is now
mechanically available and is deliberately **not** taken here, because a debate
authorizing its own subject's acceptance is the self-asserted approval ADR-073
was written to prevent. It is the owner's call.

**Which word wins for the skill-versus-agent axis.** architect, critic, and
security said "layer" throughout ADR-078. independent-thinker said either word
is defensible but the implementation surfaces must move with it. Resolved to
"layer", applied to ADR-078 and to both autoplan skill copies.

### A finding corrected during consolidation

security raised as P1 that `validate_copilot_agent_frontmatter.py` never
reaches `.claude/agents` or `src/claude`, proven by executing it against
`.claude/agents` for `[PASS] All 0 ... file(s)`, and that a mutated
`role: strategoc` exports as `support` with exit 0.

The execution evidence is correct and the conclusion overstates it. The closed
set **is** enforced across all six trees, by
`tests/test_agent_role_metadata_migration.py::test_every_agent_definition_declares_a_known_role`,
which resolves both frontmatter shapes and rejects any value outside
`{strategic, coordinator, executor, support}`. A `strategoc` typo fails that
test. The real finding is narrower and still worth carrying: the property is
enforced in one gate and not the other, and `_frontmatter_error` reads only a
top-level `role`, so it would misreport a nested-shape file as missing a role if
one ever landed in a tree it globs. Filed as follow-up, not fixed here.

Recording the correction rather than the original claim, because a debate log
that launders an overstated finding into the record is the failure this whole
PR is about.

## Phase 3: resolution

Applied to ADR-078 in this change:

| # | Finding | Raised by | Resolution |
|---|---------|-----------|------------|
| 1 | Skill-versus-agent axis half-converted; line 212 self-contradicting | architect, critic, independent-thinker, security | "layer" throughout (lines 56, 94, 110, 123 x2, 130, 206, 212) plus both autoplan `SKILL.md` copies. "tier" now means only Cynefin complexity and the opus model tier |
| 2 | Rationale cited `role:` as evidence for a routing constraint | critic, security | Rewritten: the layering is the record's own contract, `role` is descriptive and confers no invocation authority, containment comes from the platform |
| 3 | Option C's rejection became circular and duplicated its verdict cell | critic, architect | Replaced with the external, checkable consequence: the blocking session-start checklist cannot live in a surface that fires implicitly |
| 4 | Implementation Notes named `generate_agents.py` for `docs/agent-catalog.md`, which it does not write | architect | Both generators named correctly; the wrong-trigger row fixed. Verified: `generate_agents.py` has zero catalog references, `generate_agent_catalog.py:51` owns the path |
| 5 | Line 79's "coordinating hub" was unsourced and unfalsifiable | critic, architect, independent-thinker | Anchored to ADR-009's own words |
| 6 | Impact table omitted `docs/orchestrator-routing-algorithm.md`, which this PR rewrote | critic | Row added |
| 7 | `date` not updated, against `adr-best-practices.md:37` rule 1 | independent-thinker | Bumped to 2026-08-20, original decision date preserved in prose |
| 8 | No in-file trace of the correction | independent-thinker | Dated clarification note in `## Status`, on the `ADR-068:17` precedent, plus Related Decisions entries for ADR-009, ADR-030, issue #5130, and this log |
| 9 | "Six phrases" stated above a seven-row table | analyst, critic, independent-thinker | Corrected to seven across six hunks, here and in the PR body. The commit message at `d5453ca8a` says "sixth" and is immutable, so the git history and this log disagree by one; that is recorded rather than hidden |

Deferred, with reasons:

| Finding | Raised by | Why deferred |
|---------|-----------|--------------|
| `check_adr_review_policy` accepts any staged critique file mentioning the ADR ID anywhere. A live false positive exists: `ADR-084-debate-log.md:16` mentions ADR-078 in passing and would clear the gate on an ADR-078 edit | high-level-advisor, security | Needs an ADR-073 Phase 3 amendment, not a patch. Follow-up |
| No gate scans `.agents/architecture/` for references to renamed agent metadata | analyst, critic, high-level-advisor | New test surface; generalizes the issue #3399 / PR #3488 pattern. Follow-up |
| `validate_copilot_agent_frontmatter.py` shape blindness and tree coverage | security | Property is enforced by the migration test today. Follow-up |
| `status: proposed` with `implemented: true` | architect, critic, independent-thinker | Owner's call; see the disagreement above |
| `.agents/prototypes/agents/orchestrator.compressed.md` still carries `tier: manager`, breaking its README parity contract | architect | Frozen issue #1738 measurement artifacts, disclosed exemption. Follow-up |
| ADR-078 has no decision-drivers section and no review date | architect, critic | Pre-existing, not caused by this diff |
| Neither routing surface states that a routed request's content is data, not instructions | security | Pre-existing prompt-injection surface, unchanged by this diff |
| The escalation-by-decision-nature row deleted from AGENT-SYSTEM.md ("Any to Expert: critical security decisions") has no replacement | security | `AGENTS.md:25` "Ask First: Architecture, New ADRs, Breaking, Security" remains binding, so the deleted row duplicated a live constraint |

## Phase 4: convergence

**Consensus reached in one round: 3 ACCEPT, 3 DISAGREE-AND-COMMIT, 0 BLOCK.**

Every DISAGREE-AND-COMMIT named its condition, and all nine in-file conditions
are resolved above. The three dissents were:

- **architect**: would not hold the change, but required the vocabulary,
  ADR-030 citation, and generator fixes before `status` is ever flipped to
  `accepted`. All three applied.
- **critic**: required F1 fixed before merge, because the record would
  otherwise ship a Rationale contradicted by `.agents/AGENT-SYSTEM.md:836-840`
  in the same PR. Applied.
- **independent-thinker**: argued the strongest version of the append-only case
  (an ADR is a dated record of what deciders believed, and silently rewriting it
  erases the frame), then explicitly declined to hold it, on four checkable
  grounds: the repository adopted the GDS bounded rule whose boundary is
  decision change, ADR-078's Decision section is byte-identical in the diff, the
  record is `proposed` rather than `accepted`, and the rank claim was
  decorative. Its recommendation, the dated in-place amendment, is applied.

**Dissent carried forward, unresolved by design.** high-level-advisor argued
that a six-agent debate is disproportionate for a vocabulary clarification and
that `AGENTS.md:44` should route by severity: full debate when a diff touches
`status`, `supersedes`, `superseded-by`, or hunks inside Decision, Consequences,
or decision drivers; single-pass conformance review otherwise. It declined to
propose a vocabulary-only opt-out, on the grounds that a self-declared severity
field is the same forgeable signal ADR-073 was written about. Recorded, not
acted on: changing the trigger is a governance decision that needs its own ADR,
and this debate should not narrow the gate that summoned it.

## What this log does not establish

The gate that admits it, `check_adr_review_policy`
(`scripts/validation/git_hook_policy.py:1367-1419`), checks that a staged file
under `.agents/critique/` whose filename contains `debate` mentions a matching
ADR ID. It verifies nothing about who reviewed, whether six lenses ran, or what
they concluded. Two agents independently identified it as a forgeable approval
signal, and ADR-073:130 already called the unbound version security theater.

This log's authority rests on the six reviews actually having run and on their
findings being checkable, not on the gate going green. Every claim above cites a
file, a line, or a command. The strongest evidence that the debate was real is
that it produced nine changes to the record under review, four of them in the
correction that summoned it.
