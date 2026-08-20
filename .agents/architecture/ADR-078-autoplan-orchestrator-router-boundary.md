---
id: ADR-078
status: proposed
date: 2026-07-04
decision-makers: []
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-078: Autoplan and Orchestrator Router Boundary

## Status

Proposed

## Date

2026-07-04

## Context

The repo ships two request-routing surfaces with no documented precedence.
Contributors and agents cannot tell which one owns an incoming request. Issue
#2867 reports the overlap.

Ground truth in the current tree:

- `.claude/skills/autoplan/SKILL.md` is a skill (`metadata.type: router`,
  version 0.1.0). Its own description is "Route any request to the right skill,
  command, or agent chain with defaults." It fires on `/autoplan`, `do it`,
  `handle it`, `figure this out`, and implicitly on any concrete request that
  names no skill.
- `.claude/agents/orchestrator.md` (mirrored in `src/claude/orchestrator.md`)
  is a coordinator-role agent (`model: opus`, `metadata.role: coordinator`). It
  triages each request by complexity tier (Cynefin:
  clear/complicated/complex/chaotic),
  scope, urgency, and reversibility, then routes to specialist agents, manages
  handoffs, and synthesizes findings. Its own description scopes it to
  "multi-step tasks requiring coordination... end-to-end resolution."

Both classify a request and pick a downstream target. That is the overlap. The
force driving a decision: an agent reading the catalog cannot derive whether a
vague request like "figure this out" should enter through autoplan or
orchestrator, so routing is ambiguous and the two surfaces can invoke each
other or neither. Left unresolved, every workflow entry point is a coin flip,
and the duplicated classification logic drifts as each surface is edited
independently (autoplan was last changed in #2866, orchestrator on a different
cadence).

## Decision

Adopt an explicit two-layer boundary and document it in both routing surfaces:
the autoplan skill and the orchestrator shared source.

- `autoplan` is the outer front-door router at the skill tier. It classifies
  any request that names no skill and routes it to the single best
  destination: a skill, a lifecycle command, or an agent chain. It is
  lightweight and stops only for decisions that are genuinely the user's.
- `orchestrator` is one of the destinations autoplan can route to. It owns
  multi-agent, multi-domain execution: complexity classification across
  specialists, handoff management, and result synthesis. It carries the
  blocking session-start checklist and the opus reasoning tier that a skill
  must not own.

Rule: autoplan routes; orchestrator coordinates specialists. When autoplan
classifies a request as multi-domain or multi-agent execution, it hands off to
orchestrator. Orchestrator never invokes autoplan. This removes the ambiguity
without deleting either surface.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: two routers (autoplan skill,
  orchestrator agent) with independent, overlapping classification logic and no
  stated precedence.
- **When introduced**: orchestrator predates autoplan and is the established
  coordinator of the agent system. autoplan is newer
  (version 0.1.0), inspired by gstack `/autoplan`, and was refined in #2866
  ("recon target stack before routing in autoplan").
- **Original author and context**: orchestrator is the canonical multi-agent
  coordinator of the agent system. autoplan was added as a lazy single entry
  point so no one hand-picks from the full skill catalog.

### Historical Rationale

- **Why was it built this way?** orchestrator solved multi-agent coordination
  (route to analyst, architect, implementer, qa, synthesize). autoplan solved a
  different problem: catalog-wide entry when the request names no skill.
- **What alternatives were considered?** None recorded; autoplan shipped
  without an ADR reconciling it against orchestrator, which is why #2867 exists.
- **What constraints drove the design?** orchestrator needs the blocking
  session-start gate and agent-tier handoff/synthesis. autoplan needs to be
  cheap and fire implicitly on vague openers.

### Why Change Now

- **Has the original problem changed?** No. Both problems remain valid. What is
  missing is the boundary between them.
- **Is there a better solution now?** Yes: state the layering explicitly so the
  two surfaces compose instead of compete.
- **What are the risks of change?** Low. The change is documentation plus one
  explicit handoff clause. No routing code is deleted. Blast radius is the
  autoplan skill and the orchestrator shared source (plus its regenerated
  platform files).

## Rationale

The two surfaces are different kinds of thing. autoplan is a skill that
can route to anything, including orchestrator. orchestrator is an agent
that routes only among specialist agents. Naming this layering matches the
built reality and needs the least change. It also preserves autoplan's cheap
implicit firing and orchestrator's heavy session gate, which do not belong in
the same surface.

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| A. Explicit layering: autoplan = front-door router, orchestrator = routed-to multi-agent coordinator (chosen) | Matches actual design; smallest change; keeps both entry ergonomics; removes ambiguity with one handoff clause | Two surfaces still exist, so contributors must learn the boundary; relies on docs being read | Chosen: lowest risk, no capability loss, honest to how the code already behaves |
| B. Fold autoplan into orchestrator (single router) | One router, zero overlap | orchestrator's blocking session-start gate and opus tier are too heavy for trivial routing; loses implicit cheap entry; large blast radius across the shared agent source and every agent handoff | Rejected: makes the common lightweight path pay the multi-agent tax |
| C. Fold orchestrator into autoplan | One entry point at the skill surface | A skill would own agent handoff and synthesis, which is a different kind of surface with a different lifecycle; loses the opus reasoning tier for complex work, and loses orchestrator's blocking session-start gate | Rejected: pushes agent-surface responsibility into a skill |
| D. Keep both, document nothing | No work | The #2867 ambiguity persists; duplicated classification logic keeps drifting | Rejected: does not solve the reported problem |

### Trade-offs

The chosen option trades a small ongoing learning cost (contributors must know
the two-layer boundary) for zero capability loss and minimal blast radius.
Options B and C each remove one surface but force one tier to absorb
responsibilities that do not fit it.

## Consequences

### Positive

- Routing ambiguity in #2867 is resolved: autoplan owns the front door,
  orchestrator owns multi-agent execution.
- No routing capability is deleted; both entry ergonomics survive.
- The explicit handoff clause gives a single, testable contract for where a
  vague multi-domain request ends up.

### Negative

- Two routing surfaces still coexist, so a contributor must learn the boundary.
- The layering is enforced by documentation and review, not yet by a
  mechanical gate, so drift is still possible until such a gate exists.

### Neutral

- autoplan keeps firing implicitly on vague openers; orchestrator keeps its
  blocking session-start checklist.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/skills/autoplan/SKILL.md` | Direct | Add a clause: route multi-domain/multi-agent execution to orchestrator; never claim to coordinate specialists itself. Hand-authored skill, not generated | Low |
| `templates/agents/orchestrator.shared.md` | Direct | Add a clause: orchestrator is a routed-to destination; it does not invoke autoplan. This shared source regenerates the platform agent files | Low |
| `src/copilot-cli/agents/orchestrator.agent.md`, `src/vs-code-agents/orchestrator.agent.md` | Indirect (generated) | Regenerate from the shared source with `python3 build/generate_agents.py`; do not hand-edit | Low |
| `.claude/agents/orchestrator.md`, `src/claude/orchestrator.md`, `.github/agents/orchestrator.agent.md` | Direct (hand-maintained) | Hand-apply the same boundary clause; no generator writes these (REQ-003-010 forbids generators under `.claude/`; Claude sources are not template-generated). Install parity requires `.claude/agents` and `.github/agents` copies move together | Low |
| `docs/agent-catalog.md` | Indirect (generated) | Regenerate if the orchestrator description changes | Low |

## Implementation Notes

1. Edit the two source docs: the autoplan skill
   (`.claude/skills/autoplan/SKILL.md`, hand-authored) and the orchestrator
   shared source (`templates/agents/orchestrator.shared.md`). State the boundary
   and the one-way handoff in each.
2. Regenerate the generated platform files (`src/copilot-cli`, `src/vs-code-agents`,
   `docs/agent-catalog.md`) with `python3 build/generate_agents.py` and commit the
   output in the same change (generated artifacts ship with the source change).
   Hand-apply the same boundary clause to the copies no generator writes:
   `src/claude/orchestrator.md`, `.claude/agents/orchestrator.md`, and
   `.github/agents/orchestrator.agent.md` (REQ-003-010). Verify with
   `validate_install_parity.py` and `detect_agent_drift.py`.
3. Consider a follow-up mechanical check that flags a routing surface claiming
   the other's responsibility, so the boundary does not drift. Track separately.

## Related Decisions

- Issue #2867 (this ADR resolves it)
- Issue #2859 (eval orchestrator and autoplan on end-to-end delivery); gate any
  future decision to delete a surface on that end-to-end evidence, not on
  routing-only benchmarks.

## References

- `.claude/skills/autoplan/SKILL.md`
- `templates/agents/orchestrator.shared.md` (shared source for the generated
  orchestrator agent files)
- `src/copilot-cli/agents/orchestrator.agent.md`,
  `src/vs-code-agents/orchestrator.agent.md` (generated from the shared source)
- `.claude/agents/orchestrator.md`, `.github/agents/orchestrator.agent.md`
  (hand-maintained install copies; no generator writes them, REQ-003-010)
- `src/claude/orchestrator.md` (hand-maintained vendored Claude source; Claude
  agents carry unique content and are not template-generated)
- `docs/agent-catalog.md` (generated agent catalog)

---

## Agent-Specific Fields (Required for Agent ADRs)

### Agent Name

autoplan (skill-surface router) and orchestrator (coordinator-role agent)

### Overlap Analysis

| Existing Agent | Capability Overlap | Overlap % | Differentiation |
|----------------|-------------------|-----------|-----------------|
| orchestrator vs autoplan | Both classify a request and select a downstream target | ~40% (classification and routing) | autoplan routes across the whole catalog from the skill surface and fires implicitly; orchestrator coordinates specialist agents end-to-end from the agent surface with a blocking session gate and synthesis |

### Entry Criteria

| Scenario | Priority | Confidence |
|----------|----------|------------|
| Vague request naming no skill ("do it", "figure this out") | P1 | High: enters through autoplan |
| Multi-domain or multi-agent execution needing handoffs and synthesis | P1 | High: autoplan routes to orchestrator |
| User names a specific skill or lifecycle command | P0 | High: neither router; invoke directly |

### Explicit Limitations

1. autoplan MUST NOT coordinate specialist agents or manage multi-agent
   handoffs; it routes and defers to orchestrator for that.
2. orchestrator MUST NOT invoke autoplan; it is a routed-to destination, not a
   front door.
3. This ADR documents the boundary; it does not add a mechanical gate to
   enforce it. Enforcement is a tracked follow-up.

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Routing ambiguity reports (issues like #2867) | 0 new after adoption | Issue tracker search over 90 days |
| Duplicated classification drift | No divergence between the two surfaces' documented boundary | Review at each edit of either surface |
| End-to-end delivery quality | No regression vs current | #2859 end-to-end eval fixtures |

## Correction, 2026-08-20: tier vocabulary retired (issue #5130)

Issue #5130 deleted the four-tier Expert/Manager/Builder/Integration agent
hierarchy and replaced the `tier:` frontmatter key with a descriptive `role:`
key. This ADR described orchestrator in that retired vocabulary, so the text
was corrected here in the same change. **The decision is untouched.** autoplan
remains the front-door router and orchestrator remains the routed-to
multi-agent coordinator; nothing in Decision or Explicit Limitations changed.

What changed, and it is not all one kind of edit:

1. **Ground-truth correction.** The prose said orchestrator carries
   `metadata.tier: manager`. Its shipped frontmatter is `metadata.role:
   coordinator` (`.claude/agents/orchestrator.md`, `src/claude/orchestrator.md`).
   The old text named a field that no longer exists.
2. **A rationale clause withdrawn, not renamed.** Option C was rejected on
   three grounds, one of which was "breaking the manager-tier boundary". That
   clause is **withdrawn**. It cannot be carried over as
   "coordinator-role boundary", because `.agents/AGENT-SYSTEM.md` section 2.5
   now states that `role` "grants and withholds nothing at runtime", and a
   boundary that grants nothing cannot be broken. Renaming it would have
   produced a clause that is false by the new section's own definition. The
   rejection of option C now rests on its two surviving grounds, the
   surface-kind difference and the loss of the opus reasoning tier, plus
   orchestrator's blocking session-start gate. **Option C is still rejected**
   and the vote is unchanged; it stands on two legs where it used to stand on
   three.
3. **Ordinary-word uses of "tier" were left alone**, because their meaning
   survives the change: the Cynefin complexity tier, the opus reasoning tier
   (ADR-080), and the skill-versus-agent surface distinction. Only uses that
   named the deleted rank were touched.

Lines corrected: 36, 79, 110, 123, 206, 212. PR #5177's own disclosure listed
36, 79, 111, 123, and 206 and **missed 212**, which carried the identical
defect; the omission was found by the `adr-review` analyst pass.

**Review provenance.** The six-agent `adr-review` debate ran against this
correction and the wider change on 2026-08-20. Votes, findings, and the two
`BLOCK`s that had to be cleared first are recorded in
`.agents/critique/5130-tier-hierarchy-removal-debate-log.md`. This note exists
because that debate's architect pass required the withdrawal in item 2 to be
auditable rather than silent: a rewritten rationale with no record of what was
retired is the failure mode the ADR log exists to prevent.
