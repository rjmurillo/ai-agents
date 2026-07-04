---
id: ADR-078
status: proposed
date: 2026-07-04
decision-makers: []
supersedes: []
superseded-by: null
explainer: null
implemented: false
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
  is a manager-tier agent (`model: opus`). It classifies complexity (9 task
  types, 8 domains), routes to specialist agents, manages handoffs, and
  synthesizes results. `AGENTS.md` names it the ROOT agent for multi-step work.

Both classify a request and pick a downstream target. That is the overlap. The
force driving a decision: an agent reading the catalog cannot derive whether a
vague request like "figure this out" should enter through autoplan or
orchestrator, so routing is ambiguous and the two surfaces can invoke each
other or neither. Left unresolved, every workflow entry point is a coin flip,
and the duplicated classification logic drifts as each surface is edited
independently (autoplan was last changed in #2866, orchestrator on a different
cadence).

## Decision

Adopt an explicit two-layer boundary and document it in both surfaces plus
`AGENTS.md`.

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
- **When introduced**: orchestrator predates autoplan and is the long-standing
  ROOT agent in `AGENTS.md`. autoplan is newer (version 0.1.0), inspired by
  gstack `/autoplan`, and was refined in #2866 ("recon target stack before
  routing in autoplan").
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
  explicit handoff clause. No routing code is deleted. Blast radius is the two
  agent/skill files and the `AGENTS.md` routing section.

## Rationale

The two surfaces already operate at different tiers. autoplan is a skill that
can route to anything, including orchestrator. orchestrator is a manager agent
that routes only among specialist agents. Naming this layering matches the
built reality and needs the least change. It also preserves autoplan's cheap
implicit firing and orchestrator's heavy session gate, which do not belong in
the same surface.

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| A. Explicit layering: autoplan = front-door router, orchestrator = routed-to multi-agent coordinator (chosen) | Matches actual design; smallest change; keeps both entry ergonomics; removes ambiguity with one handoff clause | Two surfaces still exist, so contributors must learn the boundary; relies on docs being read | Chosen: lowest risk, no capability loss, honest to how the code already behaves |
| B. Fold autoplan into orchestrator (single router) | One router, zero overlap | orchestrator's blocking session-start gate and opus tier are too heavy for trivial routing; loses implicit cheap entry; large blast radius across `AGENTS.md` and every agent handoff | Rejected: makes the common lightweight path pay the multi-agent tax |
| C. Fold orchestrator into autoplan | One entry point at skill tier | A skill would own agent-tier handoff and synthesis, breaking the manager-tier boundary; loses opus reasoning tier for complex work | Rejected: pushes agent-tier responsibility into a skill |
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
| `.claude/skills/autoplan/SKILL.md` | Direct | Add a clause: route multi-domain/multi-agent execution to orchestrator; never claim to coordinate specialists itself | Low |
| `.claude/agents/orchestrator.md` and `src/claude/orchestrator.md` | Direct | Add a clause: orchestrator is a routed-to destination; it does not invoke autoplan | Low |
| `AGENTS.md` routing section | Direct | State the two-layer boundary and the autoplan to orchestrator handoff | Low |
| `src/copilot-cli` / `src/vs-code-agents` generated agents | Indirect | Regenerate if orchestrator text changes (`python3 build/generate_agents.py`) | Low |

## Implementation Notes

1. Edit the three source docs (autoplan skill, orchestrator agent, `AGENTS.md`)
   to state the boundary and the one-way handoff.
2. Regenerate platform agent files with `python3 build/generate_agents.py` and
   commit the generated output in the same change (generated artifacts ship
   with the source change).
3. Consider a follow-up mechanical check that flags a routing surface claiming
   the other's responsibility, so the boundary does not drift. Track separately.

## Related Decisions

- Issue #2867 (this ADR resolves it)
- Issue #2859 (eval orchestrator and autoplan on end-to-end delivery); gate any
  future decision to delete a surface on that end-to-end evidence, not on
  routing-only benchmarks.

## References

- `.claude/skills/autoplan/SKILL.md`
- `.claude/agents/orchestrator.md`, `src/claude/orchestrator.md`
- `AGENTS.md` (agent catalog and routing)

---

## Agent-Specific Fields (Required for Agent ADRs)

### Agent Name

autoplan (skill-tier router) and orchestrator (manager-tier agent)

### Overlap Analysis

| Existing Agent | Capability Overlap | Overlap % | Differentiation |
|----------------|-------------------|-----------|-----------------|
| orchestrator vs autoplan | Both classify a request and select a downstream target | ~40% (classification and routing) | autoplan routes across the whole catalog at skill tier and fires implicitly; orchestrator coordinates specialist agents end-to-end at manager tier with a blocking session gate and synthesis |

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
