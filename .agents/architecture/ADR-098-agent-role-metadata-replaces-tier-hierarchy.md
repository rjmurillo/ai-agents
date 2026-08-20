---
id: ADR-098
status: proposed
date: 2026-08-20
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-098: Agent Role Metadata Replaces the Tier Hierarchy

## Status

Proposed

## Date

2026-08-20

## Context

`.agents/AGENT-SYSTEM.md` section 2.5 documented a four-tier agent hierarchy
(Expert, Manager, Builder, Integration) across 149 lines: a delegation graph, a
per-tier agent table, escalation rules, and worked scenarios. Every agent file
in six trees carried a `tier:` frontmatter key naming its rank. Its first
sentence of prose, under an `### Overview` heading, read: "The agent system
implements a 4-tier hierarchy enabling clear escalation paths and delegation
patterns per ADR-009 (Parallel-Safe Multi-Agent Design)."

Three forces made the hierarchy a liability rather than documentation.

**It was unenforced.** No hook, validator, generator, or workflow read a rank to
decide who may delegate to whom. Measured: `grep -riE "\btier\b" .claude/hooks/`
returns zero on `origin/main`. The only consumers of `tier:` were
`build/generate_agent_catalog.py` (a docs table cell),
`scripts/openclaw_bridge.py` (a string mapped into an export), and
`scripts/validation/validate_copilot_agent_frontmatter.py` (a stringness check
that accepted any value).

**It was false.** ADR-009, the source it cited, contains **zero** occurrences of
the word "tier" (`grep -c -i tier` returns 0). ADR-009 defines parallel
dispatch, three aggregation strategies, and a consensus protocol. It never
defined a rank. The hierarchy borrowed an accepted ADR's name for a structure
that ADR is not about.

**It contradicted the agent prompts it claimed to govern.** The section ranked
24 agents. Nine of them, the Expert and Manager tiers, were granted authority to
delegate downward. **Seven of those nine carry an explicit delegation denial**
in their own Handoff Protocol, including all four Expert-tier agents
(`architect`, `high-level-advisor`, `independent-thinker`, `roadmap`) and three
of the five Manager-tier agents (`milestone-planner`, `critic`,
`issue-feature-review`). Only `orchestrator` and `pr-comment-responder` lack the
line, and `pr-comment-responder` delegates in its own body
(`.claude/agents/pr-comment-responder.md:81`, "**Task**: Delegate to
orchestrator (primary)").

**The contradiction was there on day one.** The commit that introduced the
hierarchy, `525490fae`, shipped `src/claude/architect.md` carrying
`tier: expert` at frontmatter line 5 and "**As a subagent, you CANNOT
delegate**" at line 486. Same file, same commit. That rules out the charitable
reading, that this was aspirational documentation for a system not yet
finished: the hierarchy did not precede the contradiction and then wait to be
reconciled. It was authored on top of one, and
`test_tier_compatibility.py`'s own `AGENT_TIERS` listed `"architect": "expert"`
on the day it shipped.

The concrete cost is on record. PR #5127 attempted this same removal and was
reverted after independent review found its replacement prose said escalate to
"the orchestrator" when `ADR-009:81` and `:91` say `high-level-advisor`. A rank
vocabulary that nothing reads generates confident, wrong prose about routing.
The governance-overhead review in
`.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`
was filed to catch exactly this failure mode: documented constraints that
nothing checks drift from behavior silently.

## Decision

**Retire the four-tier agent hierarchy. Replace the `tier:` frontmatter key
with a descriptive `role:` key drawn from a closed four-value vocabulary.**

- `.agents/AGENT-SYSTEM.md` section 2.5 becomes "Agent Coordination". It quotes
  ADR-009's aggregation table and consensus protocol verbatim, per
  `.claude/rules/canonical-source-mirror.md`, rather than paraphrasing them.
- Every agent definition declares `role:` with one of `strategic`,
  `coordinator`, `executor`, or `support`. The migration mapping is
  `expert -> strategic`, `manager -> coordinator`, `builder -> executor`,
  `integration -> support`.
- `role` is **descriptive metadata**. It grants and withholds nothing at
  runtime **in this repository**: no hook, validator, generator, or workflow
  reads it to allow or deny an action, and both fallback paths in
  `scripts/openclaw_bridge.py` degrade to `support`, the configured fallback
  value. Naming that fallback "least-authority" would contradict the sentence it
  sits in and re-introduce the rank this decision removes.
  Delegation is decided by the orchestrator against the task, per ADR-009, not
  by comparing two agents' role values.

  The scope qualifier is deliberate. `openclaw_bridge.py` writes `role` into an
  external OpenClaw manifest, and OpenClaw owns what its role names mean there.
  This repository cannot certify that, so the inertness claim is made where it
  can be checked and no further. See Re-evaluation Triggers.
- Coordination authority lives in ADR-009. Conflicts escalate to
  `high-level-advisor`. ADR-009 grants the three strategies and the one vote
  ordering; it does not define what makes a conflict hard, so any document that
  supplies that trigger is adding operational detail and must label it as its
  own rather than attribute it to ADR-009. See
  `docs/orchestrator-routing-algorithm.md`, which now does.

The distinction that survives is between an **aggregation weight** and an
**invocation rank**. ADR-009 does rank two agents, `architect > implementer`,
but only as vote weight when a soft conflict goes to a vote. That is a weighting
on a result already produced. It confers no authority to delegate, to override,
or to be consulted first, and it extends to no agent ADR-009 does not name.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure being changed**: a four-tier rank on 186 agent files across six
  trees, plus 149 lines of hierarchy documentation and a tier-based conflict
  algorithm in `docs/orchestrator-routing-algorithm.md`.
- **When introduced**: PR #1426 (commit `525490fae`, 2026-03-23), implementing
  issue #1002. Traces further back to the PRD in commit `0e2a588d1` (#740),
  whose requirement TR-2 "Agent Tier Metadata" survives at
  `.agents/archive/planning/prd-workflow-orchestration-enhancement.md:258`.

### Historical Rationale

- **Why was it built this way?** PR #1426's stated goals were tier metadata on
  18 agents, escalation paths, "tier compatibility validation logic in
  orchestrator routing", and "tier-aware delegation rules to orchestrator agent
  prompt."
- **The fence had a gatekeeper.** `.claude/skills/workflow/scripts/test_tier_compatibility.py`
  shipped in the same commit with `TIER_HIERARCHY`, `AGENT_TIERS`, and real CLI
  exit codes. Review comments on that PR patched the `AGENT_TIERS` dictionary
  twice for missing agents, so it was live enough to break.
- **The gatekeeper was removed by accident.** Commit `5c4729345` ("M1 catalog
  prune, delete doc-coverage, doc-sync, workflow + adversarial fix-loop",
  #1942) deleted the checker as collateral of a skill-catalog size prune, not
  by a decision that ranks should stop being checked.

This matters for honesty about the argument. "Nothing enforces it, therefore
delete it" is an unsound inference in this repository, where `.claude/rules/*.md`
and `AGENTS.md` bind behavior with no validator behind them. If lack of
enforcement were sufficient grounds, most of `.claude/rules/` would qualify for
deletion. The hierarchy is being retired because it was **wrong**, not because
it was unwatched.

### Why Change Now

- **Has the original problem changed?** The problem ADR-009 addresses
  (sequential execution, no conflict resolution, manual aggregation) still
  exists, and this decision keeps ADR-009's answer to it intact. The problem the
  *tier ranking* addressed, deciding who may delegate to whom, is answered
  per-agent in Handoff Protocol sections that predate and contradict the
  ranking.
- **Is there a better solution now?** Yes. `role` is enforced where `tier` was
  not: a closed enum in three consumers plus a test sweep over the six agent
  trees. Note the reach honestly: two of the three consumers scan one tree each
  by default (`validate_copilot_agent_frontmatter.py` takes `.github/agents`,
  `openclaw_bridge.py` takes `src/claude`), so the thing actually gating all
  186 files is the pytest sweep, not production code.
- **What are the risks?** Documented under Consequences. The largest is that
  the delegation constraint has no normative owner, and that 14 of 31 agent
  templates already carry no statement of it.

## Rationale

Restoring `test_tier_compatibility.py` would restore a checker that encoded a
rule the agent prompts contradict, which is restoring a bug. Keeping the
hierarchy as non-normative prose keeps a false document. Deleting the field
outright breaks two live consumers that require it and discards information the
OpenClaw export already wanted in functional form: `_TIER_TO_OPENCLAW_ROLE`
existed solely to translate ranks into the role names OpenClaw uses. Adopting
that vocabulary directly removes the indirection.

The rename also closed a live defect. `scripts/openclaw_bridge.py` read only a
top-level key, so every nested-shape agent resolved to the fallback:
`.claude/agents/architect.md` declared `strategic` and exported as `support`.
Three numbers, kept apart because collapsing any two of them overstates the
damage:

- **50 files carried the latent read** (25 in `.claude/agents`, 25 in
  `src/claude`). That is the exposure.
- **32 of them exported a wrong role** (16 per tree). The other 18 declared
  `integration`, which the old `_TIER_TO_OPENCLAW_ROLE` mapped to `support`, so
  the bug's output coincided with the right answer by accident.
- **A default export run emitted 16 wrong roles**, because `--agents-dir`
  defaults to `src/claude`. That is what one manifest actually shipped.

Measured by replaying the pre-fix resolver
(`e6de14b39^:scripts/openclaw_bridge.py:116`, `metadata.get("tier",
"integration")`) over the pre-fix trees, not inferred from the file counts. An
earlier revision of this paragraph put the exposure-shaped number 25 in the
impact slot, which understated nothing but named the wrong quantity; the
`critic` pass caught it on re-review. A wrong-output bug that predates this
change and that no test caught.

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| A. Retire the hierarchy, repurpose `tier:` as descriptive `role:` (chosen) | Removes a false document; keeps the two live consumers working; adopts the vocabulary OpenClaw already wanted; enum-enforced in three places plus a repo-wide sweep | Keeps a four-value taxonomy that grants nothing, which a future reader may re-derive a rank from; 186-file mechanical diff | Chosen: deletes a wrong rule, keeps every consumer working, and adds the enforcement `tier:` never had |
| B. Restore `test_tier_compatibility.py` and enforce the hierarchy | Makes the documented constraint real; honors the original #1426 intent | Enforces a rule seven of the nine empowered agent prompts explicitly contradict, and the contradiction shipped in the same commit as the checker; would have to either rewrite those prompts or codify a delegation graph nothing has validated | Rejected: restores a checker for a rule that is false |
| C. Keep the hierarchy as explicitly non-normative documentation | Zero migration cost; no churn on 186 files | Leaves prose that cites ADR-009 for a structure ADR-009 does not contain; PR #5127 shows this prose generates wrong routing claims | Rejected: the document is factually wrong, and labelling it non-normative does not make it true |
| D. Delete `tier:` outright with no replacement | Smallest possible vocabulary; nothing left to re-derive a rank from | Breaks `build/generate_agent_catalog.py`, which requires the field; forces `openclaw_bridge.py` to invent a default for every agent; loses the functional information OpenClaw consumes | Rejected: breaks two live consumers to avoid a risk that a single sentence mitigates |

### Trade-offs

Option A trades a residual re-derivation risk for a correct record and working
consumers. See Standing Dissent for that risk, its mitigation, and its trigger.

**A separate choice inside option A, recorded because it was nearly silent**:
how much of ADR-009 the replacement section should carry. The alternative was
an eight-line pointer to ADR-009 with no quoted blocks and no algorithm, which
buys zero drift surface at zero test cost, because a pointer makes no mirror
claim and `.claude/rules/canonical-source-mirror.md` therefore does not reach
it. Verbatim quoting was chosen anyway on one piece of local evidence:
`.agents/SESSION-PROTOCOL.md` **was** such a pointer, and it had already eroded
into a summary that stated ADR-009's escalation target loosely enough to need
correcting. Pointers rot into paraphrase, and paraphrase is what got PR #5127
reverted. The cost of the choice is 70 lines and one maintenance test.

## Consequences

### Positive

- The repository no longer documents a delegation rank that nothing enforces and
  that seven of the nine agent prompts it empowered explicitly contradict.
- Coordination has one source. `.agents/AGENT-SYSTEM.md` and
  `docs/orchestrator-routing-algorithm.md` quote ADR-009 byte for byte, pinned
  by `test_adr_009_blocks_are_quoted_byte_for_byte`. The pin covers the
  aggregation table in both documents and the consensus protocol in
  `AGENT-SYSTEM.md`; the routing document carries the table only, by design, so
  the protocol is unpinned there and the guard's parametrization says so.
- `role` is enforced where `tier` was not: a closed enum in
  `build/generate_agent_catalog.py`,
  `scripts/validation/validate_copilot_agent_frontmatter.py`, and
  `scripts/openclaw_bridge.py`, plus a sweep over the six configured agent
  trees asserting zero `tier:` keys in either frontmatter shape. The sweep is
  tree-scoped, not repository-wide: `tier:` legitimately survives elsewhere in
  other vocabularies (`.claude/skills/cva-analysis/SKILL.md`, a Serena memory,
  the archived PRD), which the sweep excludes by matching the four retired
  values rather than the key name.
- A latent wrong-output defect is fixed: 50 nested-shape agents now have their
  declared role read at all, and **32 of them export a different role than
  before**. The remaining 18 declared `integration`, whose old mapping already
  landed on `support`, so their output is unchanged.
- A typo in the field now fails validation. Previously `buidler` parsed as a
  string, passed, and became `support` downstream.
- All three enforcement gaps found during review were closed in this same
  change, each verified against a planted violation rather than from a passing
  run: `test_role_vocabulary_agrees_across_consumers` pins the three production
  copies of the role vocabulary against a test-tree witness,
  `test_agents_present_in_several_trees_declare_one_role` catches an agent whose
  copies disagree across trees, and
  `test_every_agent_file_in_a_configured_tree_is_a_readable_definition`
  (`tests/test_agent_tree_discovery.py`) fails a file that carries a configured
  tree's suffix but does not parse, instead of letting it drop out of the
  corpus. That third guard covers the flat form only, because `_agent_files`
  globs each tree non-recursively, so a fourth was added to
  `nested_agent_definitions` in `build/scripts/validate_agent_matrix_refs.py`:
  a file in a subdirectory that opens a frontmatter fence and then fails to
  parse is now reported. Both the `critic` and `independent-thinker` re-review
  passes found that escape independently, from opposite directions, and it was
  real: a planted `.claude/agents/probe/zzbad.md` with unbalanced YAML and
  `role: strategc` was invisible to this guard, to tree discovery, and to all
  three consumers at once, with the matrix validator exiting 0. It now exits 2
  and names the file. A nested note whose frontmatter parses cleanly but
  carries no `description` stays silent, because that is a sidecar and not a
  botched agent. Before the second, setting `.claude/agents/janitor.md` to
  `strategic` against the template's `support` left the suite green and
  `detect_agent_drift.py` silent. Before the third, a planted
  `.claude/agents/zzqaprobe.md` with unbalanced YAML and `role: strategc` passed
  the migration suite, `validate_agent_matrix_refs.py`, and
  `validate_copilot_agent_frontmatter.py`.

### Negative

- **The delegation constraint has no normative owner, and 14 agents are already
  outside it.** The hierarchy covered both delegation topology and conflict
  escalation. This decision keeps the second and removes the first without
  replacing it. What survives is prose in three places in
  `.agents/AGENT-SYSTEM.md`, all stating the one-level-deep pattern and that
  subagents cannot delegate to each other: the `**Reference**:` note naming
  `../../src/claude/orchestrator.md` as the canonical pattern source, the
  `**Note**: Orchestrator executes each consultation and aggregates` line, and
  the sentence beginning `The orchestrator manages all parallel execution
  coordination`. Cited by quoted phrase rather than by line number on the
  `critic` pass's advice, and it was right within the hour: a four-line edit to
  section 2.5 elsewhere in this same change moved all three, so the numbers
  this paragraph originally carried (`:862`, `:1047`, `:1311`) were stale
  before the PR merged. Issue #1769's relocation plan will move them again.
  Alongside that prose sits a per-agent line in **17 of 31 templates**. **The other 14 carry no
  constraint at all**: `code-reviewer`, `code-simplifier`, `comment-analyzer`,
  `debug`, `dependency-auditor`, `janitor`, `merge-resolver`, `negotiation`,
  `orchestrator`, `pr-comment-responder`, `pr-test-analyzer`,
  `quality-auditor`, `silent-failure-hunter`, `type-design-analyzer`. That is
  the present state, not a future risk, and this ADR does not create it: the
  tier hierarchy never granted or withheld a tool either. What it removes is
  the last document that *described* the topology, while claiming an authority
  the prompts denied.

  The real enforcement surface is the tool grant, not the prose: an agent that
  declares no `tools:` key inherits `Task` and can delegate whatever any
  document says. **Tracked as issue #5184**, whose acceptance criteria name an
  owner for the constraint and require a check that fails when a template's
  delegation statement disagrees with its tool grant. The issue number is here
  rather than the phrase "tracked as a follow-up" because the
  `independent-thinker` re-review pointed out that an untracked follow-up is
  the unpayable form of exactly the debt this bullet is about: a governance
  hole parked in a Consequences list is one that never gets paid, which is the
  pattern
  `.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`
  exists to name.
- **`role` is a four-value vocabulary that grants nothing.** See Standing
  Dissent, which is the canonical statement of this risk and its mitigation.
- **The vocabulary is duplicated across four modules.** An equality test now
  pins the three production consumers against a test-tree witness
  (`test_role_vocabulary_agrees_across_consumers`), so drift in one consumer
  fails. It does **not** catch coordinated drift: a search-and-replace editing
  all four consistently passes green and silently changes the vocabulary.
- **`role` is an overloaded key name.** `.claude/skills/review/references/*.md`
  uses `role:` for a different vocabulary (review axes such as `agent-safety`),
  handled by a path exclusion rather than a value check.
- The migration touched 186 files, which exceeded the repository's 50-file scope
  ceiling and required a maintainer-approved `SKIP_SCOPE_CHECK`.

### Neutral

- Four frozen issue #1738 measurement artifacts under `.agents/prototypes/` and
  `.agents/analysis/` keep `metadata.tier` deliberately, exempted by explicit
  file path so a fifth cannot inherit the exemption. Rewriting them would alter
  a recorded measurement.
- `docs/agent-catalog.md` gains a Role column in place of a Tier column.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.agents/AGENT-SYSTEM.md` section 2.5 | Direct | 149 lines of hierarchy replaced by a coordination section quoting ADR-009 | Low |
| 186 agent files across six trees | Direct | `tier:` to `role:` in both the top-level and `metadata:`-nested shapes | Low, mechanical, guarded by a repo-wide sweep |
| `build/generate_agent_catalog.py` | Direct | Requires `role`, constrains it to four values, renders a Role column | Low |
| `scripts/openclaw_bridge.py` | Direct | `_TIER_TO_OPENCLAW_ROLE` deleted; reads both frontmatter shapes; warns and falls back on an unknown value | Medium, changes exported roles for 32 agents, 16 of them in a default run |
| `scripts/validation/validate_copilot_agent_frontmatter.py` | Direct | `role` required and constrained; previously any string passed | Low |
| `docs/orchestrator-routing-algorithm.md` | Direct | `validate_tier_sequence`, `TIER_HIERARCHY`, `AGENT_TIERS` removed; implements ADR-009's three strategies; escalates to `high-level-advisor` | Medium |
| `build/scripts/detect_agent_drift.py` | Indirect | `merge-resolver` baseline comment corrected; re-measured at 20.7% on both comparisons, unchanged | Low |
| `.agents/architecture/ADR-078` | Indirect | Seven phrases moved off the retired vocabulary; the option-C rejection clause re-grounded on the skill/agent boundary. Decision untouched | Low |
| `.agents/prototypes/agents/README.md` | Indirect | Frontmatter-parity instruction named `metadata.tier`; updated to `metadata.role` | Low |

## Implementation Notes

Shipped in PR #5177 for issue #5130. The migration is mechanically atomic: a
partial application leaves the frontmatter validator rejecting files the
OpenClaw bridge still exports and the catalog generator cannot render, so it
cannot be split across PRs without shipping a known-broken intermediate.

Three enforcement gaps were found by planting a violation and observing the
suite stay green. **All three were closed in this same PR** and are recorded
under Consequences/Positive. The third, a malformed agent file dropping out of
the corpus before the known-role check saw it, closed last and is the narrowest
of the three, and it took two guards rather than one.
`test_every_agent_file_in_a_configured_tree_is_a_readable_definition` fails a
file that sits at the top level of a configured tree and carries that tree's
suffix but does not parse. Two of the six trees use a bare `.md` suffix, which
admits sibling documents, so `_NON_AGENT_SIBLINGS` allowlists the four that are
deliberately not agents and a separate test guards that allowlist. The
subdirectory case needed its own branch in `nested_agent_definitions`, since
that function skipped anything failing `is_agent_definition` and a malformed
file is not a definition. Three of the six trees already ship subdirectories
(`security/references/`), so the shape was live, not hypothetical.

Two residuals have no fix and are stated so they are not mistaken for
coverage:

- The equality test compares the three production consumers against a fourth
  literal in the test tree, which makes it a witness against drift in one
  consumer, not against **coordinated** drift: a search-and-replace editing all
  four consistently passes green.
- A new agent tree that uses a bare `.md` suffix **and** omits `role` entirely
  stays invisible to tree discovery. Closing it would mean treating every
  markdown file carrying a `description` as an agent, which pulls in skills,
  prompts, and analysis documents across the repository. Two of the six
  existing trees use that bare suffix, so a seventh following the same
  convention is not far-fetched.

## Standing Dissent

Recorded rather than resolved, per the `adr-review` debate that reviewed this
decision. Renaming rather than deleting keeps a taxonomy alive that nothing
enforces, and a future reader may re-derive delegation rules from the four role
values exactly as they were derived from the four tiers. The mitigation is the
explicit sentence in `.agents/AGENT-SYSTEM.md` section 2.5 **stating that
delegation is decided by the orchestrator against the task, not by comparing
two agents' role values**. If that sentence is ever dropped, this dissent
becomes live again.

Naming the sentence is deliberate: an earlier draft of this section said only
"the explicit sentence in section 2.5", which left a reader of the dissent
unable to check its own trigger.

## Re-evaluation Triggers

Any one of these puts this decision back on the table:

1. **The mitigation sentence is deleted or reworded** so it no longer denies
   that role values order agents. That is the Standing Dissent's own trigger,
   and it is now pinned by a test so the deletion cannot be silent.
2. **Anything begins reading `role` to allow or deny an action.** The decision
   rests on the field being inert. A hook, validator, or workflow that gates on
   it turns descriptive metadata into a privilege boundary, which is the
   property the tier hierarchy falsely claimed.
3. **A fifth role value is proposed.** Four values that describe what an agent
   does are a vocabulary; a growing set that starts encoding precedence is a
   rank returning under a new name.
4. **OpenClaw assigns authority to a role name.** The inertness claim is
   established inside this repository only. If the downstream consumer gates on
   `role`, the export becomes an authority-granting surface and needs its own
   review.
5. **A seventh agent tree is added with a bare `.md` suffix.** Consequences
   states that such a tree, if it also omits `role` entirely, stays invisible to
   tree discovery. That residual is stated rather than closed, so the event that
   would make it bite belongs here and not only in a prose list. Raised by the
   `critic` re-review, which pointed out that naming a residual "not
   far-fetched" and then leaving it out of the triggers is how a known hole goes
   unwatched.

## Review Provenance

Three rounds ran on 2026-08-20. All votes, findings, and the P0s fixed between
rounds are in `.agents/critique/5130-tier-hierarchy-removal-debate-log.md`.

| Round | Subject | Tally |
|-------|---------|-------|
| 1 | The change this ADR records, six `adr-review` roles plus a `qa` pass | 4 ACCEPT, 1 DISAGREE-AND-COMMIT, 2 BLOCK |
| 2 | ADR-098 itself, after it was written | 2 ACCEPT, 1 DISAGREE-AND-COMMIT, 3 BLOCK |
| 3 | ADR-098 after round 2's corrections, the three round-2 blockers re-run | 1 ACCEPT, 1 DISAGREE-AND-COMMIT, 1 BLOCK, then ACCEPT on the P0 fix |

The middle row is stated rather than folded into an average because a reader who
stops here should not conclude this artifact passed 4-1-2. Its own review was
2-1-3, with three P0s, one of which was a Context paragraph wrong three ways in
the self-flattering direction. Round 3 then found a fourth: the export-impact
number in Consequences named the exposure count, not the wrong-output count.

**This ADR exists because of round 1**: the `architect` pass blocked on the
absence of a decision record, holding that a critique log has no status field,
no supersession chain, and is not in the catalog a future architect greps.

Round 3 exists because the `adr-review` contract requires every final vote to be
ACCEPT or DISAGREE-AND-COMMIT, and round 2 ended on three standing BLOCKs whose
clearing conditions had been met by construction rather than re-verified by the
agents that set them. The log said so plainly at the time, but disclosure is not
convergence.

## Related Decisions

- `.agents/architecture/ADR-009-parallel-safe-multi-agent-design.md`. The
  canonical aggregation and escalation source. Unchanged by this decision and
  now quoted verbatim rather than paraphrased.
- `.agents/architecture/ADR-078-autoplan-orchestrator-router-boundary.md`.
  Described orchestrator in the retired vocabulary; corrected alongside this
  change, decision untouched. Its option-C rejection now rests on the
  skill-versus-agent surface distinction and the opus reasoning tier, not on
  the retired rank.

## References

- Issue #5130. The scoped follow-up this decision implements.
- Issue #1769. `.agents/analysis/1769-monolith-section-classification.md`, the
  monolith relocation plan this reconciles with. Read with the caveat the
  debate log records: this change edits that plan's section-2.5 row, so the row
  is not independent confirmation of the reconciliation.
- Issue #1002 and PR #1426 (`525490fae`). Introduced the hierarchy and its
  checker.
- PR #1942 (`5c4729345`). Deleted the checker as collateral of a catalog prune.
- PR #5127. The reverted first attempt, whose `critic` review produced #5130.
- `.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`.
- `.claude/rules/canonical-source-mirror.md`. Why ADR-009 is quoted, not
  paraphrased.
