# ADR-063: Decompose the Memory Skill Into Focused Sub-Skills

## Status

Proposed

status: proposed

## Date

2026-06-01

## Context

`.claude/skills/memory/SKILL.md` is the entry point for a four-tier memory
system (Tier 1 Semantic, Tier 2 Episodic, Tier 3 Causal, plus the BLOCKING
Memory-First Gate). The SKILL.md body is 12 KB, but the skill ships 11
reference files under `.claude/skills/memory/references/` that total roughly
141 KB. The skill-triage analysis measured the combined surface at 143.6 KB
(`.agents/analysis/skill-triage-2026-05-09.md`, finding F2).

That is the largest skill in the catalog and roughly 18 times the typical
8 KB skill ceiling the triage analysis cites. The SKILL.md itself is under the
500-line `taste-lints` ceiling, so the violation is not a single oversized
file. The violation is the aggregate context a model pays when the skill and
its reference set are loaded for any one of several unrelated operations
(search, episode extraction, causal-graph update, the Memory-First Gate, graph
density improvement, cross-referencing, token counting).

### What Currently Exists

- `.claude/skills/memory/SKILL.md` (12 KB) declares the four tiers, the
  Memory-First Gate (BLOCKING), the progressive-disclosure architecture, a
  decision tree, and a script catalog of seven scripts.
- `.claude/skills/memory/references/` holds 11 files: `agent-integration.md`
  (19 KB), `api-reference.md` (18 KB), `benchmarking.md` (14 KB),
  `memory-router.md` (14 KB), `quick-start.md` (14 KB), `reflexion-memory.md`
  (27 KB), `skill-reference.md` (10 KB), `troubleshooting.md` (16 KB),
  `tier-selection-guide.md` (3 KB), `codebase-knowledge-graph.md` (3 KB), and
  `zettelkasten-memory-agents.md` (3 KB). These reference files are the bulk of
  the 143 KB.
- The skill is referenced by `.claude/commands/spec.md` Step 0.5 (the
  Memory-First Gate), and the triage analysis names additional downstream
  callers across `/build`, `/review`, the retrospective skill, and agent
  prompts.
- `ADR-007-memory-first-architecture.md` declares the memory-first principle
  and the Serena-first / Forgetful-fallback layering.
- `ADR-037-memory-router-architecture.md` defines the router pattern the
  current skill implements.
- `ADR-038-reflexion-memory-schema.md` defines the episode and causal schemas
  for Tiers 2 and 3.
- `ADR-056-skill-output-format-standardization.md` defines the skill output
  envelope every skill (including any decomposed sibling) must emit.

### Why Change Now

The skill-catalog triage
(`.agents/plans/active/PLAN-skill-catalog-triage-action-slate.md`, Tier 2
DECOMPOSE row 6) classifies `memory` as DECOMPOSE and marks M3 implementation
blocked on this ADR. AGENTS.md lists architecture changes and new ADRs under
"Ask First" and marks ADR Review as BLOCKING for ADR edits. A decomposition of
this magnitude touches multiple downstream callers and admits several materially
different shapes. Choosing a shape without a recorded decision means the choice
rots silently, which is the exact failure mode the ADR Review gate exists to
prevent. This ADR records the decision; it does not implement it (implementation
is issue #1948 / M3).

## Decision

Decompose the monolithic `memory` skill into focused sub-skills split by
operation, keep `memory` as a thin router that delegates, and preserve the
`memory` skill name so existing callers do not break.

This ADR codifies five binding points. It is a DRAFT (Proposed) and triggers
the adr-review debate gate; the multi-agent debate and the human decision
select among the alternatives below and may revise these points before the ADR
moves to Accepted.

1. **Split by operation, not by tier.** The recommended primary axis is the
   operation a caller invokes (search, episode extraction, causal-graph update,
   the Memory-First Gate, maintenance). Operation is the axis along which
   callers differ: `/spec` Step 0.5 needs only the gate and search; a
   session-end flow needs only episode extraction. Splitting by tier (semantic
   / episodic / causal) would still bundle read and write paths for each tier
   and would not reduce the per-call context for the hot path.

2. **`memory` survives as a thin router.** The `memory` name is not deleted.
   It becomes a small router skill that names the sub-skills, carries the
   decision tree and the When-to-Use matrix, and delegates. This honors
   ADR-037 (the router pattern already exists) and keeps the activation
   vocabulary (`search memory`, `check memory health`) pointed at a live skill.

3. **The Memory-First Gate moves to its own sub-skill or stays in the router.**
   The BLOCKING gate (`### Memory-First Gate (BLOCKING)` in the current
   SKILL.md) is invoked by `/spec` Step 0.5 and is the highest-frequency entry
   point. It must remain cheap to load. The debate selects whether it lives in
   the router (cheapest to reach, but couples the router to gate prose) or in a
   dedicated `memory-gate` sibling (cleaner boundary, one more hop). Either way
   the gate keeps its current BLOCKING semantics from
   `ADR-070-memory-first-gate-spec-pipeline.md` (renumbered from the former
   ADR-062 collision per #2228).

4. **Boundaries from ADR-007, ADR-037, ADR-038, and ADR-056 are preserved.**
   The decomposition is a SKILL-surface change only. Serena remains the
   canonical store and Forgetful the supplementary store (ADR-007). Each
   sub-skill inherits ADR-007 Security Considerations, including memory data
   classification and storage security rules. The router pattern is preserved
   (ADR-037). The episode and causal schemas are unchanged (ADR-038). Every
   sub-skill emits the standard output envelope (ADR-056). Storage backends are
   out of scope.

5. **No behavior change for callers.** Migration is name-preserving. Callers
   that invoke `memory` today continue to work because `memory` still resolves
   to a skill. New callers may target a sub-skill directly for a smaller
   context footprint. The decomposition does not change what any operation
   returns.

## Prior Art Investigation

- `.agents/analysis/skill-triage-2026-05-09.md`, finding F2 and the F4 memory
  cluster table: the direct measurement driver. F2 records the 143.6 KB size,
  the +2.83 eval delta (the highest in the catalog), and the recommendation to
  decompose into per-tier skills or move bulk to passive context with a thin
  router. This ADR adopts the thin-router half of that recommendation and
  selects operation as the split axis over tier.
- `.agents/plans/active/PLAN-skill-catalog-triage-action-slate.md`, Tier 2
  DECOMPOSE row 6 and the M3 milestone: records that M3 implementation is
  blocked on this ADR and that the ADR must precede the spec.
- `ADR-007-memory-first-architecture.md`: declares memory-first and the
  Serena-first / Forgetful-fallback layering this ADR must not disturb.
- `ADR-037-memory-router-architecture.md`: defines the router pattern. The
  thin-router decision in point 2 is a continuation of this ADR, not a new
  shape.
- `ADR-038-reflexion-memory-schema.md`: defines the episode (Tier 2) and causal
  (Tier 3) schemas. Any episode-extraction or causal sub-skill inherits these
  schemas unchanged.
- `ADR-056-skill-output-format-standardization.md`: defines the output envelope
  every decomposed sibling must emit. (Issue #1947 cites "ADR-051: response
  envelope schema"; ADR-051 is actually the Synthesis Panel Frontmatter
  Standard. The response-envelope / output-format constraint is ADR-056. This
  ADR cites ADR-056 and flags the stale reference for issue cleanup.)
- `.claude/rules/philosophy-of-software-design.md`: the deep-vs-shallow module
  test informs the split. A sub-skill is justified only if it hides real
  complexity behind a small interface; a sub-skill that is one script behind a
  one-line router call is a shallow pass-through and should not be created.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen (pending debate) |
|-------------|------|------|----------------|
| Split by tier (semantic / episodic / causal per ADR-007) | Maps to the conceptual model in ADR-007; three clean siblings | Each tier still bundles read and write paths; the hot path (search plus gate) is all Tier 1, so per-call context for the common case barely shrinks; tier is not the axis callers differ on | Tier is the data model, not the call shape; splitting by tier optimizes the wrong axis |
| Split by source-of-truth ownership (Serena vs Forgetful vs in-tree) | Aligns sub-skills with store ownership and the ADR-007 fallback boundary | Issue #1947 puts storage backends out of scope; couples the skill surface to backend identity, which ADR-007 deliberately hides behind the router; a backend swap would force a skill rename | Leaks a hidden decision (which store) into the interface, violating information hiding |
| Split by call frequency (hot path vs cold path) | Smallest possible context for the highest-frequency entry point (gate plus search) | Only two buckets; "cold path" becomes a grab-bag with low cohesion; frequency is a runtime property that drifts, so the boundary is unstable | Low cohesion in the cold bucket; unstable boundary |
| Move all bulk to passive context (CLAUDE.md @import), keep no skill | Zero skill-load cost; everything is ambient | Memory operations need tool access and run scripts; passive context cannot invoke `search_memory.py`; loses the skill activation vocabulary | Memory is an action surface, not knowledge; it cannot be passive (per the Context Type Decision in AGENTS.md) |
| Do nothing (keep the monolith) | No migration cost; no adr-review cost | 143 KB context persists; the highest-delta skill keeps overwhelming the budget on every load; the triage finding stands unaddressed | The triage finding and the ceiling violation are the reason this work exists |

### Trade-offs

- A decomposition adds skill files and a router hop. The router hop costs one
  extra delegation per call. Mitigation: the router stays thin (decision tree
  plus delegation only), so the hop is cheap and the per-operation context drops
  far below 143 KB. The M3 spec sets the exact context budget; the initial
  target is router plus hot-path sub-skill under 20 KB unless measurement shows
  the split needs a different bound.
- Splitting by operation means a caller that needs two operations
  (search then extract) loads two sub-skills. For the common case (`/spec`
  Step 0.5 needs gate plus search) the two are co-located on the hot path, so
  this is rare.
- The adr-review debate gate fires on this DRAFT ADR (BLOCKING, multi-agent).
  That cost is intended: the decomposition shape is a one-way-ish door for
  downstream callers, so the debate is the point.

## Reversibility and Kill Criteria

The decomposition is reversible at the SKILL-surface level. Because `memory`
survives as a router and the sub-skills delegate to the same scripts that the
monolith calls today, re-merging the siblings back into one SKILL.md is a
file-move, not a behavior change. No data migration is required; storage
backends are untouched.

Kill criteria for the decomposition (evaluated after M3 lands, against the same
eval harness that produced the F2 delta):

1. The decomposed router plus hot-path sub-skill measures a higher per-call
   context than a budget target set in the M3 spec (decomposition failed to
   shrink the hot path).
2. The eval-knowledge-integration baseline regresses beyond the M3 spec
   tolerance (decomposition changed behavior despite the no-behavior-change
   commitment).
3. A downstream caller breaks because the `memory` name no longer resolves the
   way it expected (the name-preservation commitment failed).

If any kill criterion fires, the decomposition is reverted to the monolith in a
follow-on PR and the shape is reconsidered. The M3 spec (issue #1948) owns the
concrete budget target and tolerance numbers; this ADR fixes the criteria, not
the thresholds.

## Vendor Lock-In

The decomposition does not change the Forgetful dependency posture. ADR-007
already classifies Forgetful as supplementary and local-only, with Serena as
the canonical layer that travels with the repository. Each sub-skill inherits
that posture: a search sub-skill degrades to Serena-only lexical search when
Forgetful is absent (the existing `--lexical-only` fallback), and a
graph-traversal operation degrades to a coverage note. No new lock-in is
introduced because no new backend is added; this is a surface refactor.

## Consequences

### Positive

- The 143 KB monolith stops loading in full for single-operation calls. The
  hot path (gate plus search) loads a fraction of the current context.
- The skill-triage F2 finding is addressed with a recorded decision behind it.
- The governance "Ask First" gate is satisfied for the M3 architecture change.
- Each sub-skill is independently testable, which raises coverage clarity over
  one umbrella skill.

### Negative

- The adr-review debate gate fires on this DRAFT ADR (BLOCKING, multi-agent
  cost), and a human decision is required before it moves to Accepted.
- More skill files to maintain and keep mirrored to the Copilot tree.
- A multi-operation caller pays for more than one sub-skill load.

### Neutral

- Storage backends (Serena, Forgetful) are unchanged. The decomposition is a
  SKILL-surface change.
- The episode and causal schemas (ADR-038) and the output envelope (ADR-056)
  are unchanged.
- The split axis (operation) is the recommendation; the adr-review debate may
  select a different axis from the alternatives table before Accepted.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/skills/memory/SKILL.md` | Direct | Becomes the thin router; reference files redistributed (M3 / issue #1948, not this PR) | Medium |
| `.claude/commands/spec.md` Step 0.5 | Direct | Gate invocation must still resolve; name-preserved (M3, not this PR) | Medium |
| `/build`, `/review`, retrospective skill, agent prompts | Direct | Verify `memory` name still resolves; no edit if router preserves the name (M3, not this PR) | Low |
| `src/copilot-cli/skills/memory/` mirror | Direct | Mirror must stay in sync after M3 split; no edit from this ADR | Low |
| Issue #1947 body | Indirect | Cite ADR-056 instead of the stale "ADR-051 response envelope" reference (issue cleanup, not this PR) | Low |
| Serena, Forgetful stores | Indirect | None; backends out of scope | Low |

## Implementation Notes

This ADR is the unit of decision. It records the decomposition decision; it does
not implement the decomposition. Implementation is issue #1948 / M3, which owns
the concrete migration plan, the per-call budget target, the eval tolerance, and
the redistribution of the 11 reference files across the sub-skills. The target
shape is 3 to 5 sub-skills; if M3 needs more, revisit the split axis before
adding shallow pass-through skills. Each reference file travels with the
sub-skill that invokes it. Shared references stay with the router only when the
router uses them directly.

Each sub-skill that depends on Forgetful must implement the graceful degradation
table from ADR-007. Sub-skills that handle file paths must preserve the existing
path traversal checks or import a shared validation utility. The cross-reference
edit that adds this ADR to the `memory` SKILL.md frontmatter or top-of-body
(issue #1947 AC6) is tracked separately so this PR stays a pure ADR DRAFT for
the adr-review debate gate.

## Related Decisions

- ADR-007: Memory-First Architecture (declares the principle and the
  Serena-first / Forgetful-fallback layering this ADR preserves)
- ADR-037: Memory Router Architecture (the router pattern the thin-router
  decision continues)
- ADR-038: Reflexion Memory Schema (the episode and causal schemas the
  decomposed siblings inherit unchanged)
- ADR-056: Skill Output Format Standardization (the output envelope every
  sub-skill must emit)
- `ADR-070-memory-first-gate-spec-pipeline.md`: Memory-First Gate Is a
  BLOCKING Step in the Spec Pipeline (the gate semantics the decomposition must
  keep). Renumbered from the former ADR-062 collision per #2228.

## References

- Issue #1947: this ADR's source of record (M3-prereq: ADR for memory skill
  decomposition)
- Issue #1948: M3 implementation (the decomposition this ADR authorizes but
  does not perform)
- Epic #1944: parent epic
- Issue #2228: resolved the pre-existing ADR-058 and ADR-062 numbering
  collisions surfaced during adr-review (the gate ADR is now ADR-070)
- `.agents/analysis/skill-triage-2026-05-09.md`: finding F2 (143.6 KB size,
  +2.83 eval delta) and F4 (memory cluster table), the measurement driver
- `.agents/plans/active/PLAN-skill-catalog-triage-action-slate.md`: Tier 2
  DECOMPOSE row 6 and the M3 milestone (blocked on this ADR)
- `.claude/skills/memory/SKILL.md`: the skill being decomposed
- AGENTS.md: the "Ask First" rule for architecture changes and new ADRs, plus
  the ADR Review BLOCKING gate for ADR edits
- `.claude/rules/philosophy-of-software-design.md`: the deep-vs-shallow module
  test that bounds which sub-skills are worth creating
