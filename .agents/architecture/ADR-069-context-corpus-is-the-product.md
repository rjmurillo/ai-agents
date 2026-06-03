---
status: proposed
date: 2026-05-02
decision-makers: ["architect", "user"]
consulted: ["analyst", "critic", "qa"]
informed: ["implementer", "devops", "security", "roadmap"]
---

# ADR-069: The Curated Context Corpus IS the Product, Orchestration Is Plumbing

## Context and Problem Statement

The competitive value of this repository over a generic Copilot or Claude prompt is **not** the agent abstractions, the orchestration scripts, or the lifecycle commands. Those are all reproducible, off-the-shelf, or rapidly commoditizing. What actually shapes model output across runs is the **curated set of artifacts that get assembled into model context**: baselines, memory files, agent definitions, prior decisions, `CLAUDE.md`, `HANDOFF.md`, ADRs, skills, instruction files, governance documents, and the cross-references between them.

Today these artifacts live across many locations with no unified theory of why they exist together or what role each plays at inference time:

- `.serena/memories/` — learned patterns, skills (Zettelkasten atomic notes, tiered)
- `.agents/architecture/` — ADRs and architectural decisions
- `.agents/governance/` — constraints and policies
- `.agents/HANDOFF.md`, `.agents/SESSION-PROTOCOL.md` — session bridge / protocol
- `templates/agents/` — agent definitions (YAML frontmatter + Markdown)
- `.claude/skills/*/SKILL.md` — skill definitions
- `.github/instructions/` — platform-specific rules with `applyTo` globs
- `.github/prompts/` — quality gate prompts
- `.baseline/` — coverage thresholds (JSON with schema)
- `CLAUDE.md`, `AGENTS.md`, root entry-point context
- `scripts/memory/`, `scripts/memory_sync/` — index maintenance

This catalog is descriptive, not prescriptive — it names the territory as it currently exists. **This ADR does not propose reorganizing any of it.**

## Frame: LLMs as Ghosts, Not Animals

The framing this ADR adopts is summarized in the *LLMs as Ghosts not Animals* concept (referenced in the originating issue #1859): there is **no learning between runs**. Each invocation is a fresh ghost summoning. Weights do not update from session to session, and the model has no persistent memory of prior interactions in this repository. The only thing that persists across runs is **what we explicitly put back into the next ghost's context**.

That property has a sharp consequence: every architectural improvement that does not change what enters the context window is, at best, plumbing. The orchestration layer schedules ghosts. The corpus *constitutes* what the ghost knows. The corpus is therefore the durable artifact and the durable competitive surface.

## Decision Drivers

1. **Durability of value**: Corpus content survives model upgrades, framework rewrites, and orchestration pivots; orchestration code does not.
2. **Reproducibility of behavior**: Behavior on a given task is dominated by what's in context, not by which agent dispatched the call.
3. **Engineering opportunity cost**: Effort spent inventing novel agent abstractions is effort not spent curating, indexing, and observing the corpus.
4. **Risk of premature schema lock-in**: A canonical schema imposed top-down would force the corpus into a shape it wasn't designed for and trigger revolt before the principle even lands.
5. **Need for shared vocabulary**: Without a stated principle, contributors will continue to optimize the wrong layer.

## Decision

Adopt the following architectural principle:

> **The curated context corpus IS the product. Orchestration is plumbing.**

Concretely, this ADR:

1. **Establishes the principle** as a first-class architectural commitment, on equal footing with ADR-007 (memory-first architecture) and ADR-017 (tiered memory index).
2. **Catalogs the existing context sources** (see Context section above) as a snapshot of the territory, without reorganizing them.
3. **Names — but explicitly does not answer — the open questions** that downstream work will address:
   - **Corpus catalog**: What is the authoritative, machine-readable inventory of all context artifacts the system can assemble?
   - **Schema spike**: Should there be a canonical schema for context artifacts, or a family of per-type schemas, or none at all? (Schema-first risks killing the corpus this principle is trying to protect.)
   - **Assembly-layer prototype**: What does a context-assembly layer look like in practice — RAG, rule-based, agent-mediated, hybrid? Likely needs prototyping before deciding.
   - **Telemetry-of-influence**: What signal would prove a given artifact actually influenced output, beyond "it was in the prompt window"?
   - **Curation cadence**: What is the cadence and ownership for pruning stale artifacts, refreshing summaries, and retiring obsolete patterns?
4. **Does not prescribe** answers to any of the above. Each becomes a separate, appropriately-sized issue **after** this ADR merges.

### What This ADR Is NOT

- **Not** a reorganization of `.serena/memories/`, `.agents/`, `.claude/skills/`, or any other context source.
- **Not** a new schema. ADR-069 does not define field requirements, frontmatter standards, or validation rules.
- **Not** a deprecation of any existing agent, orchestration command, lifecycle hook, or workflow.
- **Not** a commitment to build telemetry, an assembly layer, or a unified catalog as part of this ADR. Those are downstream issues.

## Prior Art Investigation

### What Currently Exists

- **Structure/pattern being changed**: Implicit, distributed treatment of context artifacts across multiple directories with no unified architectural narrative.
- **When introduced**: Incrementally over the project's history — `.serena/memories/` (ADR-007 era), `.agents/` (ADR-008 era), `.claude/skills/` (ADR-030), governance and instructions added piecemeal.
- **Original author and context**: Multiple authors; each subsystem solved a local problem (memory retrieval, session handoff, agent definitions, skill discovery) without a unifying principle for *why context lives where it lives*.

### Historical Rationale

- **Why was it built this way?** Each context surface was added to solve an immediate problem: ADR-007 to make retrieval mandatory, ADR-017 to make retrieval precise, ADR-030 to standardize skill encoding, etc. No one ADR claimed authority over "context as a product."
- **What alternatives were considered?** Bottom-up additions were preferred over a top-down information architecture because (a) the right shape was unknown and (b) prematurely imposing schema risked killing contributor velocity.
- **What constraints drove the design?** Heterogeneous tooling (Claude, Copilot, Serena MCP), heterogeneous artifact lifetimes (durable ADRs vs. ephemeral session logs), and the need for human readability alongside machine indexing.

### Why Change Now

- **Has the original problem changed?** Yes. The corpus has grown to 459+ memory files, 50+ ADRs, dozens of skills and instruction files. Without a principle, contributors continue to optimize orchestration (the cheap, visible layer) instead of curation (the durable, valuable layer).
- **Is there a better solution now?** Stating the principle is the better solution. Building the catalog/schema/assembly/telemetry stack *without* the principle would be premature; building it *with* the principle aligns downstream effort.
- **What are the risks of change?** Low. This ADR adds a principle and a vocabulary. It does not move files, change schemas, or break workflows.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Status quo (no ADR) | Zero cost; nothing breaks | Contributors continue investing in the wrong layer; no shared vocabulary for "context is the product" | Status quo is the problem this ADR addresses |
| ADR + immediate canonical schema | Forces consistency; enables tooling | Schema-first kills the corpus before the principle lands; existing artifacts revolt against retrofit | Premature; better to prototype assembly before locking schema |
| ADR + immediate catalog + schema + assembly + telemetry + cadence (the original issue scope) | Comprehensive | A 12-month roadmap dressed as one decision; high blast radius; mixes principle with implementation | Per the issue's edit log, this scope was explicitly stripped |
| Principle-only ADR with named open questions (this ADR) | Establishes vocabulary; preserves optionality; downstream issues can be sized appropriately | Doesn't deliver any tooling itself | Chosen — matches the issue's deliverable scope and protects the corpus from premature schema |

### Trade-offs

- **Clarity vs. action**: This ADR delivers clarity, not capability. That is intentional. Acting without the principle was the failure mode being corrected.
- **Open questions vs. decisions**: Naming questions without answering them is, deliberately, less satisfying than a complete proposal. It is also the only honest move when the right answers require prototyping (assembly layer) or empirical evidence (telemetry, cadence).
- **Reorganization restraint**: Not touching the existing layout is the most important constraint. Any ADR that *moves* corpus artifacts must come later, justify itself against this principle, and pass through `.claude/skills/chestertons-fence/`.

## Consequences

### Positive

- Shared, citable vocabulary for prioritizing curation work over orchestration work.
- Downstream issues (catalog, schema spike, assembly prototype, telemetry, curation cadence) can be sized and sequenced with a coherent rationale.
- New ADRs and skills can be evaluated against "does this strengthen or dilute the corpus?"
- Aligns with and complements ADR-007 (memory-first) and ADR-017 (tiered index) without superseding either.

### Negative

- Risk of misuse as a rhetorical cudgel against legitimate orchestration improvements. Mitigation: the principle says orchestration is plumbing, not that plumbing is worthless — plumbing failures still ship broken software.
- Risk that "principle without implementation" reads as procedural overhead. Mitigation: the downstream issues are real work, not paperwork; they are deferred precisely so they can be sized properly.

### Neutral

- Existing files do not move. Existing workflows do not change.
- Agent and skill authors continue working as before; the principle informs *future* prioritization, not current artifacts.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.serena/memories/` | Indirect | None in this ADR; future ADRs may reference this principle when proposing memory-corpus changes | Low |
| `.agents/architecture/` (other ADRs) | Indirect | None now; ADRs that touch context sources should cite ADR-069 | Low |
| `.claude/skills/` | Indirect | None now; skill authors may cite the principle when justifying corpus-shaping skills | Low |
| Lifecycle commands (`/spec`, `/plan`, `/build`, `/test`, `/review`, `/ship`) | None | No change | None |
| CI workflows | None | No change | None |

## Implementation Notes

This ADR is documentation-only. There is no code change, no schema change, no migration, and no validation gate associated with it.

**Post-merge follow-ups** (to be filed as separate issues, per the originating issue's Deliverable section):

1. Corpus catalog — authoritative inventory of context artifacts.
2. Schema spike — investigate whether a canonical or per-type schema is desirable, with explicit attention to the schema-first risk.
3. Assembly-layer prototype — explore RAG / rule-based / hybrid context assembly.
4. Telemetry-of-influence — define signal that an artifact actually influenced output.
5. Curation cadence — define ownership and cadence for pruning, refreshing, retiring.

None of the above are part of this ADR's acceptance criteria.

## Related Decisions

- **ADR-007** (Memory-First Architecture): establishes that retrieval precedes reasoning; ADR-069 generalizes the principle from "memory" to "the entire curated corpus."
- **ADR-017** (Tiered Memory Index Architecture) — provides one concrete realization of corpus organization within `.serena/memories/`.
- **ADR-030** (Skills Pattern Superiority) — skills are one corpus surface among several.
- **ADR-050** (ADR Protocol Sync) — governs how this ADR is propagated and discovered.
- **ADR-053** (ADR Exception Criteria) — clarifies when ADRs are required; this ADR is in-scope.

## References

- Issue [#1859](https://github.com/rjmurillo/ai-agents/issues/1859) — originating issue and edit log.
- Related issues: [#1769](https://github.com/rjmurillo/ai-agents/issues/1769) (refactor: extract monolith `.agents/*.md` — this ADR reframes the *why*), [#1728](https://github.com/rjmurillo/ai-agents/issues/1728) (context pressure detection — measurement complement), [#1854](https://github.com/rjmurillo/ai-agents/issues/1854), [#1855](https://github.com/rjmurillo/ai-agents/issues/1855), [#1857](https://github.com/rjmurillo/ai-agents/issues/1857) (eval/gate/router companions).
- Frame: *LLMs as Ghosts not Animals* (`wiki/concepts/AI Strategy/LLMs as Ghosts not Animals.md`, as cited in the originating issue) — no learning between runs; the corpus is what persists.
- ADR-TEMPLATE.md — `.agents/architecture/ADR-TEMPLATE.md`.
