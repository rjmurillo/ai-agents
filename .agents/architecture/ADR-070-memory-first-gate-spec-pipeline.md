# ADR-070: Memory-First Gate Is a BLOCKING Step in the Spec Pipeline

## Status

Proposed

## Date

2026-05-31

## Context

`.claude/commands/spec.md` runs a multi-step pipeline that turns a problem
statement into testable requirements. Step 0 (First Principles Gate) is a
forward-looking gate: it asks whether the work is demanded. It does not ask
whether the proposer has read the backward-looking context that explains why
the current state exists.

REQ-017 (`.agents/specs/requirements/REQ-017-spec-memory-first-gate.md`, issue
#1951) added Step 0.5, the Memory-First Gate, between Step 0 and Step 1. Step
0.5 is a new BLOCKING gate. It composes three skills in sequence
(`chestertons-fence`, `memory`, `exploring-knowledge-graph`), defines a
machine-readable halt-block schema (`step0_5-halt` with five fields and six
trigger IDs H6 through H11), introduces a metrics file
(`.agents/sessions/STEP-0.5-METRICS.md`), and adds a cross-step state-passing
protocol (the Step 3 supplemental traversal hook that may append a
`### Supplemental (Phase N)` sub-block to the Prior Art block).

Step 0 had a similar shape and was justified by retrospective citation
(`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`). Step 0.5's
rationale in `.claude/commands/spec.md` references the memory skill at
`.claude/skills/memory/SKILL.md` but no ADR authorizes the specific gate.

Per `.claude/rules/governance.md`:

> **ADR required**. Significant governance changes (new rules, policy
> reversals, removed constraints) MUST be accompanied by an Architecture
> Decision Record in `.agents/architecture/`.

`ADR-007-memory-first-architecture.md` declares the memory-first principle
("Memory retrieval MUST precede reasoning in all agent workflows"). It does not
authorize wiring that principle into `/spec` as a BLOCKING gate with halt
triggers that stop a spec from reaching Step 1. This ADR closes that gap.

### What Currently Exists

- `.claude/skills/memory/SKILL.md` declares the Memory-First Gate as BLOCKING
  under the `### Memory-First Gate (BLOCKING)` section ("Before changing
  existing systems, you MUST..."). It states the rationale verbatim:

  > **Why BLOCKING**: <50% compliance with "check memory first" guidance.
  > Making it BLOCKING achieves 100% compliance (same pattern as session
  > protocol gates).
- `.claude/commands/spec.md` Step 0.5 wires that BLOCKING declaration into the
  spec pipeline. The gate, its halt schema, its metrics tally, and its
  supplemental traversal hook are fully specified in `.claude/commands/spec.md` lines 142
  through 354.
- REQ-017 is the requirement of record for the gate behavior. It carries 13
  acceptance criteria (AC-01 through AC-13) and is the source of truth for what
  the gate does.
- `.agents/architecture/ADR-007-memory-first-architecture.md` declares the
  principle but does not authorize the `/spec` gate specifically.

### Why Change Now

Issue #1971 raised this during `/review` Architecture Axis F2 on the PR for
#1951. The gate landed without an ADR. The adr-review debate gate is BLOCKING
and adds multi-agent cost, so the ADR was deferred during M5. This ADR is the
written decision that the governance rule requires. It documents the why; it
does not change the how. REQ-017 remains the source of truth for the gate
behavior.

## Decision

The Memory-First Gate is a BLOCKING step (Step 0.5) in the `/spec` pipeline,
running after Step 0 and before Step 1. This ADR codifies four binding points.

1. **The gate is BLOCKING, not advisory.** When any halt trigger (H6 through
   H11) fires, the gate emits a `step0_5-halt` block and STOPs. The pipeline
   does not proceed to Step 1. This mirrors the BLOCKING declaration in
   `.claude/skills/memory/SKILL.md` and the precedent set by Step 0
   (H1 through H5) and the session protocol gates.

2. **The gate composes three skills, one per prior-art failure mode.**
   `chestertons-fence` answers "why does the current state exist" (git
   archaeology). `memory` answers "what prior decision did the proposer not
   recall" (point search). `exploring-knowledge-graph` answers "what connected
   entity did the proposer not name in Step 0" (multi-hop traversal). The three
   layered together produce the `## Prior Art / Constraints` block that Step 6
   carries into the PRD as its first section.

3. **Halt triggers split into two families.** H6 through H9 encode the
   memory-search BLOCKING change types from the Investigation Protocol table
   in `.claude/skills/memory/SKILL.md` (remove an ADR constraint, bypass a
   protocol, delete more than 100 lines, refactor a complex component): each
   fires when memory search returns no prior art for the change. H10 is a
   separate `.claude/commands/spec.md` halt that fires when a validator,
   linter, hook, or shared-infrastructure component is changed without a
   prior-art citation in the PriorArtBlock. H11 fires when adjudicated
   blast-radius entities meet the threshold (2 in human mode, 3 in auto mode).
   Auto-mode raises the H11 threshold to reduce false halts on automated
   pipelines.

4. **The gate degrades, never silently skips.** When Forgetful MCP or a skill
   is unavailable, the gate records a coverage note and continues. It does not
   halt on infrastructure failure and it does not claim compliance without
   recording what ran. Step 9 check 9d distinguishes "search ran and found
   nothing" from "search did not run" by reading those coverage notes.

## Prior Art Investigation

- `.claude/skills/memory/SKILL.md`, `### Memory-First Gate (BLOCKING)` section:
  the direct decision driver. It declares the gate BLOCKING and states the
  compliance evidence (<50% without BLOCKING; 100% with). This ADR
  operationalizes that declaration in the spec pipeline.
- `.agents/architecture/ADR-007-memory-first-architecture.md`: declares
  "memory retrieval MUST precede reasoning." Step 0.5 is the spec-pipeline
  instance of that rule. ADR-007 also documents the Forgetful dependency and
  the Serena-first fallback this ADR relies on for graceful degradation.
- `.agents/specs/requirements/REQ-017-spec-memory-first-gate.md`: the
  requirement of record. AC-01 through AC-13 are the behavioral contract. This
  ADR cites REQ-017 rather than restating it, to avoid a second source of truth
  for the gate behavior.
- `.claude/commands/spec.md` Step 0 (First Principles Gate): structural precedent. Step 0 is a
  BLOCKING gate with its own halt triggers (H1 through H5), its own halt block
  (`step0-halt`), and its own metrics file (`STEP-0-METRICS.md`). Step 0.5
  follows the same shape, which is why the `step0_5-halt` block is structurally
  identical to `step0-halt` except for the info-string and the `check` field.
- `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`: the cost
  evidence. PR #1887 spent 69 commits and 11-plus review rounds because the M4
  evidence rule was designed against an imagined contract instead of the
  canonical `scripts/validate_session_json.py:CONTRADICTION_PATTERNS` regex. That is
  precisely the failure Step 0.5 prevents: the proposer did not search for the
  canonical source before writing the spec.
- `.claude/rules/canonical-source-mirror.md`: the rule that the M4 episode
  produced. It binds claims of "matches" or "mirrors" to verbatim citation.
  Step 0.5 is the spec-time complement: it forces the search that surfaces the
  canonical source before the claim is written.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Post-hoc check (validate prior-art after Step 1) | No gate friction before clarification; proposer drafts freely | Discovers ADR collisions after design work is sunk; same late-feedback cost ADR-054 cites for CI-only security findings | A backward-looking check is worthless if it runs after the design is committed; the PR #1887 cost was incurred precisely because the search ran (if at all) too late |
| Merge into Step 0 (one combined gate) | Single gate, less prose, one metrics file | Conflates forward-looking demand ("is this wanted") with backward-looking prior art ("do we know why the current state exists"); a proposer can pass demand and still skip recall | The two questions are distinct and fail independently; merging them hides which gate a halt came from and breaks the clean H1-H5 vs H6-H11 split |
| Centralized middleware (one memory-first gate for all lifecycle commands) | DRY; `/plan`, `/build`, `/test` would inherit the gate for free | No second consumer exists yet; premature abstraction (per `.claude/rules/philosophy-of-software-design.md`); the per-command halt schema and tier-gated depth are tuned to `/spec`'s Step 0 inputs | YAGNI; promoting the gate to other commands is explicitly out of scope for REQ-017; build the seam when the second consumer appears, not before |
| Advisory gate (warn, do not halt) | Zero blast radius; proposer keeps control | The memory skill measured <50% compliance with advisory "check memory first" guidance; advisory reproduces the exact failure the BLOCKING declaration was written to fix | The whole point of the gate is 100% compliance; advisory is the status quo the gate replaces |

### Trade-offs

- BLOCKING gates add friction. A spec that genuinely has no prior art still
  pays the three-skill search cost. Mitigation: tier-gated depth keeps shallow
  traversals cheap for Tier 1-2 work, and zero-result topics produce a coverage
  note rather than a halt.
- The H11 blast-radius threshold is judgment-loaded in human mode (2 entities)
  and conservative in auto mode (3 entities). A conservative auto threshold
  trades some missed blast-radius detection for fewer false halts on automated
  pipelines. This is the intended bias: a false halt costs a re-run; a missed
  blast-radius entity costs a downstream surprise, but Step 9 check 9d still
  catches a missing Prior Art block.
- The gate depends on Forgetful MCP for two of its three skills (`memory`
  semantic search and `exploring-knowledge-graph`). Forgetful is local-only and
  not present on all platforms. See "Vendor Lock-In" below.

## Reversibility and Kill Criteria

The gate is reversible. It is prose in `.claude/commands/spec.md`; removing the
Step 0.5 block and the Step 9 check 9d clause reverts to the Step 0-only
pipeline. No data migration is required; the metrics file is review-only and its
absence does not block `/spec`.

Step 0's kill criteria (documented as
`REQ-016-13` in
`.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md`)
extend to Step 0.5. At 30 invocations, the gate is reviewed
against four criteria:

1. False-positive rate at or above 30 percent (halts followed by re-invocation
   with cosmetic changes).
2. Bypass rate at or above 20 percent.
3. Author abandonment of 3 or more sessions in 7 days.
4. 30 consecutive passes with zero halts (recalibration trigger, not a kill).

If any kill criterion fires, the gate is loosened or removed in a follow-on PR.
The `STEP-0.5-METRICS.md` tally (one line per invocation: timestamp, pass/fail,
halt reason) is the data source for criteria 1 and 4, which are derivable from
the per-invocation pass/fail and halt records. Criteria 2 (bypass rate) and 3
(author abandonment) are defined in `REQ-016-13` against Step 0 and are not
captured by the Step 0.5 tally format; measuring them for Step 0.5 requires
separate instrumentation. REQ-017 defers the Step 0.5 kill-criteria review
schedule, and that Step 0.5-specific instrumentation, to a named owner. Until
that lands, the Step 0 criteria are the interim standard and criteria 2 and 3
are tracked at the Step 0 level.

## Vendor Lock-In

Two of the three gate skills depend on Forgetful MCP:

- `memory` uses Forgetful for semantic search and falls back to Serena-only
  lexical search via `search_memory.py --lexical-only` when Forgetful is
  unavailable (per ADR-007's fallback table).
- `exploring-knowledge-graph` depends on Forgetful's knowledge graph and has no
  fallback; when Forgetful is unavailable the skill is skipped and a coverage
  note is recorded.

ADR-007 already classifies Forgetful as supplementary and local-only, with
Serena as the canonical layer that travels with the repository. The gate
inherits that posture: it never blocks on Forgetful availability. The lock-in
risk is bounded because the BLOCKING change-type triggers run against memory
search, which degrades to Serena: H6 through H9 fire on a no-result memory
search, and H10 checks for a prior-art citation in the PriorArtBlock that
memory search produces. Both paths degrade to Serena-only lexical search rather
than failing. Only the blast-radius discovery (H11) and the deep traversal lose
coverage when Forgetful is absent, and both degrade to coverage notes rather
than false passes.

If Forgetful is replaced or retired, the gate continues to function on Serena
alone with reduced traversal depth. The exit cost is the loss of multi-hop
entity discovery, not a broken pipeline. This is the same trade ADR-007 already
accepted for the broader memory-first architecture.

## Consequences

### Positive

- The BLOCKING declaration in `.claude/skills/memory/SKILL.md` is now
  operative in the spec pipeline with a written decision behind it.
- The governance requirement (significant change needs an ADR) is satisfied for
  Step 0.5.
- A proposer cannot reach Step 1 having proposed a BLOCKING change type without
  searching memory for the prior art that explains it.
- Step 9 check 9d has a written rationale to cite when it rejects a spec with a
  missing Prior Art block.

### Negative

- The adr-review debate gate fires on this ADR (BLOCKING, multi-agent). That
  cost is the reason #1971 deferred the ADR during M5; it is paid now.
- The gate adds search latency to every `/spec` run, including specs with no
  prior art.
- The two-tier H11 threshold (human 2, auto 3) is a documented asymmetry that
  reviewers must understand to reason about auto-mode halts.

### Neutral

- The gate does not change Step 0, Step 1, or any later step's behavior. It
  inserts between Step 0 and Step 1 and emits one new PRD section.
- REQ-017 remains the source of truth for gate behavior. This ADR is the source
  of truth for why the gate is BLOCKING and where it lives.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/commands/spec.md` Step 0.5 prose | Direct | Cross-reference this ADR (separate work-item; not this PR) | Low |
| `.agents/specs/requirements/REQ-017-spec-memory-first-gate.md` Dependencies | Direct | Cite this ADR (separate work-item; not this PR) | Low |
| `src/copilot-cli/skills/spec/SKILL.md` | Direct | Mirror must stay byte-identical per existing test invariant; no new edit from this ADR | Low |
| Forgetful MCP | Indirect | None; gate degrades to Serena when absent | Low |

## Implementation Notes

This ADR is the unit of decision. It documents an already-landed gate; it does
not change the gate. The two cross-reference edits (Step 0.5 prose pointing at
this ADR, and REQ-017 Dependencies citing this ADR) are tracked separately so
this PR stays a pure ADR draft for the adr-review debate gate. Modifying the
gate behavior is explicitly out of scope (REQ-017 is the source of truth for
behavior).

## Related Decisions

- ADR-007: Memory-First Architecture (declares the principle this ADR wires
  into `/spec`; documents the Forgetful dependency and Serena-first fallback)
- ADR-054: Local Security Scanning (precedent for the shift-left, fail-early
  argument used against the post-hoc-check alternative)
- ADR-065: Orchestrator Is a Deterministic Router (adjacent; same move from
  advisory prompt guidance to a deterministic gate with visible failure)

## References

- Issue #1971: this ADR's source of record (deferred from `/review` Arch Axis F2)
- Issue #1951: REQ-017 source issue (added Step 0.5 to `.claude/commands/spec.md`)
- Epic #1952: parent epic listing Step 0.5 as Phase 1 child
- `.claude/skills/memory/SKILL.md`: `### Memory-First Gate (BLOCKING)` section
  (the decision driver)
- `.claude/commands/spec.md`: Step 0.5 specification (lines 142 through 354)
- `.agents/specs/requirements/REQ-016-spec-step0-first-principles-gate.md`
  (`REQ-016-13`): Step 0 kill criteria, canonical source
- `.agents/specs/requirements/REQ-017-spec-memory-first-gate.md`: gate behavior
  source of truth (AC-01 through AC-13)
- `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`: cost evidence
  for the failure the gate prevents
- `.claude/rules/governance.md`: the rule requiring this ADR
- `.claude/rules/canonical-source-mirror.md`: the rule the M4 episode produced
