# Engineering Knowledge Index

Comprehensive index of engineering knowledge across 5 experience tiers.

## How to Use This Index

1. **By Experience Level**: Find knowledge appropriate to your experience tier
2. **By Concept**: Look up specific mental models, frameworks, or patterns
3. **By Problem Domain**: Find relevant knowledge for specific challenges

## Knowledge by Experience Tier

### Tier 1: Foundational (<5 Years)

**Mental Models**:
- [knowledge/chestertons-fence](knowledge/chestertons-fence.md): Understand before removing
- [knowledge/conways-law](knowledge/conways-law.md): Org structure mirrors architecture
- [knowledge/hyrums-law](knowledge/hyrums-law.md): Observable behaviors become dependencies
- [knowledge/second-order-thinking](knowledge/second-order-thinking.md): Ask "And then what?"
- [knowledge/law-of-demeter](knowledge/law-of-demeter.md): Only talk to immediate friends
- [knowledge/galls-law](knowledge/galls-law.md): Complex systems evolve from simple ones
- `yagni`: You aren't gonna need it
- [knowledge/technical-debt-quadrant](knowledge/technical-debt-quadrant.md): Deliberate vs inadvertent, prudent vs reckless
- [knowledge/boy-scout-rule](knowledge/boy-scout-rule.md): Leave code better than you found it

**Principles**:
- `code-qualities`: Cohesion, coupling, encapsulation, testability, non-redundancy
- `solid-principles`: Single responsibility, open-closed, Liskov, interface segregation, dependency inversion
- `dry-principle`: Don't repeat yourself
- `kiss-principle`: Keep it simple
- `separation-of-concerns`: Decompose into non-overlapping parts
- `tell-dont-ask`: Bundle data with behavior
- `programming-by-intention`: Express intent over implementation (sergeant methods directing privates)
- `owasp-top-10`: Web vulnerabilities
- `principle-of-least-privilege`: Minimal permissions needed

**Practices**:
- `tdd-red-green-refactor`: Test-driven development cycle
- `clean-architecture`: Domain at center, dependencies point inward
- `twelve-factor-app`: Cloud-ready application methodology
- `trunk-based-development`: Frequent commits to shared trunk
- `observability-three-pillars`: Logs, metrics, traces

### Tier 2: Advanced (5-10 Years)

**Architectural Models**:
- [architecture/c4-model](architecture/c4-model.md): Context, container, component, code
- [knowledge/cap-theorem](knowledge/cap-theorem.md): Consistency, availability, partition tolerance
- [knowledge/resilience-patterns](knowledge/resilience-patterns.md): Circuit breaker, bulkheads, retries, timeouts
- `idempotency`: Operations safe to retry
- [knowledge/poka-yoke](knowledge/poka-yoke.md): Design to prevent errors

**Patterns**:
- `common-design-patterns`: Strategy, Factory, Bridge, Facade, Adapter
- `strategy-pattern`: Vary behavior at runtime
- `decorator-pattern`: Add behavior dynamically
- `null-object-pattern`: Avoid null checks
- `specification-pattern`: Encapsulate business rules
- `pattern-oriented-design`: Finding patterns in problems before coding

**Mental Models**:
- `welcome-to-the-room`: Understand why before sharing understanding

### Tier 3: Senior (10-15 Years)

**Trade-Off Thinking**:
- `coupling-vs-duplication`: When to copy vs share (Rule of Three, wrong abstraction, independent evolution)
- `speed-vs-safety`: Fast vs validated
- `complexity-vs-flexibility`: General vs specific

**Design Practices**:
- `cva-commonality-variability-analysis`: Discover natural abstractions by finding commonalities first
- `design-for-replaceability`: Favor replaceability over reuse
- [design/design-by-contract](design/design-by-contract.md): Preconditions, postconditions, invariants
- `policy-vs-mechanism`: Separate rules from execution
- `fallacies-of-distributed-computing`: Network assumptions that fail
- `wisdom-from-gof`: Design to interfaces, favor composition over inheritance, encapsulate what varies

**Evolution Patterns**:
- [knowledge/feature-toggles](knowledge/feature-toggles.md): Decouple deployment from release
- `branch-by-abstraction`: Large refactorings safely
- [knowledge/strangler-fig-pattern](knowledge/strangler-fig-pattern.md): Incremental legacy migration
- `expand-contract-migration`: Schema changes without downtime (expand functionality, run both, contract old)

**Thinking Models**:
- [knowledge/wardley-mapping](knowledge/wardley-mapping.md): Capability evolution and strategy
- [knowledge/cynefin-framework](knowledge/cynefin-framework.md): Problem classification (clear, complicated, complex, chaotic)
- [knowledge/antifragility](knowledge/antifragility.md): Systems that improve from stress
- [knowledge/rumsfeld-matrix](knowledge/rumsfeld-matrix.md): Known/unknown knowns/unknowns

**Operability**:
- [knowledge/slo-sli-sla](knowledge/slo-sli-sla.md): Service level objectives, indicators, agreements
- `error-budgets`: Acceptable unreliability enabling innovation
- `mttr-optimization`: Mean time to recovery
- `blameless-postmortems`: Learning from failures

### Tier 4: Principal (15-25 Years)

**Wisdom**:
- [knowledge/chestertons-fence](knowledge/chestertons-fence.md): [Advanced application]
- [knowledge/conways-law](knowledge/conways-law.md): [Strategic application with inverse Conway maneuver]
- `paved-roads-guardrails`: Defaults without constraints

**Strategic Models**:
- [knowledge/wardley-mapping](knowledge/wardley-mapping.md): [Strategic positioning]
- [knowledge/cynefin-framework](knowledge/cynefin-framework.md): [Response strategy selection]
- [knowledge/ooda-loop](knowledge/ooda-loop.md): Observe, orient, decide, act
- [knowledge/inversion-thinking](knowledge/inversion-thinking.md): How would this fail?
- [knowledge/critical-path-method](knowledge/critical-path-method.md): Focus on longest dependency chain
- [knowledge/systems-archetypes](knowledge/systems-archetypes.md): Fixes that fail, shifting burden, limits to growth

**Architecture**:
- [adr/adrs-architecture-decision-records](adr/adrs-architecture-decision-records.md): Capture decisions with context
- `sociotechnical-design`: Align org and architecture (Team Topologies)
- `fitness-functions`: Automated architectural intent verification
- [knowledge/products-over-projects](knowledge/products-over-projects.md): Durable teams over temporary funding
- `design-principles-overview`: Philosophy of accommodating change
- `services-capabilities`: Operational maturity model

**Risk & Resilience**:
- `slos-error-budgets`: Balance reliability and velocity
- [knowledge/chaos-engineering](knowledge/chaos-engineering.md): Confidence through controlled failure
- [security/threat-modeling](security/threat-modeling.md): Structured security risk identification
- [knowledge/pre-mortems](knowledge/pre-mortems.md): Identify failure modes before starting

**Organizational Leadership**:
- [engineering/engineering-strategy](engineering/engineering-strategy.md): Vision, strategy, specifications
- [knowledge/platform-engineering](knowledge/platform-engineering.md): Self-service developer capabilities
- [knowledge/buy-vs-build-framework](knowledge/buy-vs-build-framework.md): Core vs context evaluation
- [knowledge/migrations-at-scale](knowledge/migrations-at-scale.md): Incremental transformation

### Tier 5: Distinguished (25+ Years)

**Legacy Thinking**:
- [knowledge/lindy-effect](knowledge/lindy-effect.md): Older technology has longer expected life
- [knowledge/second-system-effect](knowledge/second-system-effect.md): Resist over-engineering replacements
- `path-dependence`: Historical constraints on current choices
- `architectural-paleontology`: Understanding design layers
- `golden-path-vs-golden-cage`: Enable without constraining

**Governance**:
- `sociotechnical-coherence`: Align technology with org dynamics
- `run-vs-change-business`: Separate operations from innovation
- `systemic-risk-portfolios`: Classify dependencies and failure risk
- `compliance-as-code`: Policy enforcement via automation
- `data-lineage-sovereignty`: Track data across jurisdictions
- `principle-based-governance`: Guide via values, not rules

**Migration**:
- [knowledge/strangler-fig-pattern](knowledge/strangler-fig-pattern.md): [Strategic application]
- `expand-contract`: [Schema evolution]
- `capability-based-migration`: User-facing capabilities over technical components
- `sacrificial-architecture`: Plan for replacement
- `core-context-mapping`: Invest in differentiation, buy commodities

**Time Horizons**:
- [knowledge/three-horizons-framework](knowledge/three-horizons-framework.md): Balance current (H1), emerging (H2), future (H3)
- `long-term-constraint-thinking`: What will successors wish we documented?

**Leadership**:
- `principle-based-governance`: Guide via values, not rules
- `enterprise-architecture`: Cross-cutting business-technology integration
- `technical-ethics`: Privacy, fairness, bias, safety
- `knowledge-continuity`: Prevent knowledge rot in long-lived systems

**Classics**:
- `mythical-man-month`: Brooks's Law, conceptual integrity
- `designing-data-intensive-applications`: Distributed systems foundation
- `thinking-in-systems`: Stocks, flows, feedback loops, leverage points
- `fifth-discipline`: Learning organization disciplines
- `how-buildings-learn`: Pace layers, shearing layers
- [knowledge/wardley-mapping](knowledge/wardley-mapping.md): [Strategic application]

## Knowledge by Problem Domain

### Decision-Making
- Tier 1: [knowledge/second-order-thinking](knowledge/second-order-thinking.md), [knowledge/technical-debt-quadrant](knowledge/technical-debt-quadrant.md)
- Tier 3: [knowledge/cynefin-framework](knowledge/cynefin-framework.md), [knowledge/rumsfeld-matrix](knowledge/rumsfeld-matrix.md)
- Tier 4: [knowledge/ooda-loop](knowledge/ooda-loop.md), [knowledge/inversion-thinking](knowledge/inversion-thinking.md), [knowledge/pre-mortems](knowledge/pre-mortems.md)

### Architecture
- Tier 1: `clean-architecture`, `separation-of-concerns`
- Tier 2: [architecture/c4-model](architecture/c4-model.md), [knowledge/cap-theorem](knowledge/cap-theorem.md), [knowledge/poka-yoke](knowledge/poka-yoke.md)
- Tier 3: [knowledge/wardley-mapping](knowledge/wardley-mapping.md), [knowledge/strangler-fig-pattern](knowledge/strangler-fig-pattern.md)
- Tier 4: [adr/adrs-architecture-decision-records](adr/adrs-architecture-decision-records.md), `sociotechnical-design`, `fitness-functions`
- Tier 5: [knowledge/second-system-effect](knowledge/second-system-effect.md), `architectural-paleontology`, `sacrificial-architecture`

### Change Management
- Tier 1: [knowledge/chestertons-fence](knowledge/chestertons-fence.md), [knowledge/boy-scout-rule](knowledge/boy-scout-rule.md)
- Tier 3: [knowledge/feature-toggles](knowledge/feature-toggles.md), `branch-by-abstraction`, `expand-contract-migration`
- Tier 4: [knowledge/migrations-at-scale](knowledge/migrations-at-scale.md)
- Tier 5: [knowledge/strangler-fig-pattern](knowledge/strangler-fig-pattern.md), `capability-based-migration`

### Legacy Systems
- Tier 1: [knowledge/chestertons-fence](knowledge/chestertons-fence.md), [knowledge/galls-law](knowledge/galls-law.md)
- Tier 3: [knowledge/strangler-fig-pattern](knowledge/strangler-fig-pattern.md), `expand-contract-migration`
- Tier 5: [knowledge/lindy-effect](knowledge/lindy-effect.md), [knowledge/second-system-effect](knowledge/second-system-effect.md), `path-dependence`, `architectural-paleontology`

### Strategic Planning
- Tier 3: [knowledge/wardley-mapping](knowledge/wardley-mapping.md), [knowledge/cynefin-framework](knowledge/cynefin-framework.md), [knowledge/antifragility](knowledge/antifragility.md)
- Tier 4: [knowledge/ooda-loop](knowledge/ooda-loop.md), [knowledge/critical-path-method](knowledge/critical-path-method.md), [knowledge/products-over-projects](knowledge/products-over-projects.md)
- Tier 5: [knowledge/three-horizons-framework](knowledge/three-horizons-framework.md), `core-context-mapping`

### Operability & Reliability
- Tier 1: `observability-three-pillars`
- Tier 2: [knowledge/resilience-patterns](knowledge/resilience-patterns.md), `idempotency`
- Tier 3: [knowledge/slo-sli-sla](knowledge/slo-sli-sla.md), `error-budgets`, `mttr-optimization`, `blameless-postmortems`
- Tier 4: [knowledge/chaos-engineering](knowledge/chaos-engineering.md), [security/threat-modeling](security/threat-modeling.md)

### Organization Design
- Tier 1: [knowledge/conways-law](knowledge/conways-law.md)
- Tier 4: `sociotechnical-design`, [knowledge/platform-engineering](knowledge/platform-engineering.md)
- Tier 5: `sociotechnical-coherence`, `run-vs-change-business`, `knowledge-continuity`

### Design Principles & Patterns
- Tier 1: `code-qualities`, `solid-principles`, `dry-principle`, `kiss-principle`, `programming-by-intention`, `tell-dont-ask`
- Tier 2: `common-design-patterns`, `pattern-oriented-design`, `specification-pattern`
- Tier 3: `cva-commonality-variability-analysis`, `wisdom-from-gof`, [design/design-by-contract](design/design-by-contract.md)
- Tier 4: `design-principles-overview`, `services-capabilities`, `fitness-functions`

### Modernization & .NET
- Tier 2: `supported-tfms`, `sdk-style-projects`, `global-json`
- Tier 3: `central-package-management`, `dotnet-container-publish`, `ev2-managed-sdp`
- Tier 4: `modernization`, `silicon-agnosticism`, `arm-performance-tuning`, `cobalt-100`

## .NET Modernization Pipeline

For organizations modernizing .NET workloads, the following pipeline applies:

```text
Modernize → Silicon Agnostic → ARM Deploy → COGS Savings
```

**Phase 1: Modernization** (Tier 4)
- Upgrade to modern .NET (8+)
- Migrate to Kubernetes/container orchestration
- Implement OpenTelemetry observability
- Enable workload identity

**Phase 2: Silicon Agnosticism** (Tier 4)
- Multi-architecture container builds (AMD64, ARM64)
- Platform-independent dependencies
- Architecture-agnostic code patterns

**Phase 3: ARM Performance Tuning** (Tier 4)
- Thread pool optimization (`DOTNET_ThreadPool_UnfairSemaphoreSpinLimit=0`)
- Garbage collection tuning (Server GC, region-based GC)
- NUMA configuration testing
- Load testing and profiling

**Foundation Practices** (Tier 2-3)
- `supported-tfms`: Target framework selection (.NET 8, .NET 9)
- `sdk-style-projects`: Modern MSBuild project format
- `global-json`: SDK version pinning for reproducible builds
- `central-package-management`: Centralized NuGet version management
- `dotnet-container-publish`: Native .NET containerization support
- `ev2-managed-sdp`: Safe deployment practices

## Query Examples

**By Memory Name**:
```python
mcp__serena__read_memory(memory_file_name="knowledge/cynefin-framework")
```

**By Experience Tier**:
```python
# Search for foundational knowledge
mcp__serena__list_memories()
# Filter by "tier-1-foundational" tag
```

**By Problem Domain**:
```python
# Search for decision-making frameworks
mcp__serena__read_memory(memory_file_name="knowledge/ooda-loop")
mcp__serena__read_memory(memory_file_name="knowledge/inversion-thinking")
```

## Integration with Agents

**Analyst**: Use Tier 3-4 strategic frameworks for research classification
**Architect**: Use Tier 1-5 architecture and legacy system knowledge
**High-Level Advisor**: Use Tier 4-5 strategic and decision-making frameworks
**Planner**: Use Tier 3-4 time horizon and critical path knowledge
**Implementer**: Use Tier 1-2 foundational principles and practices
**QA**: Use Tier 1-2 testing and quality frameworks

## Maintenance

This index should be updated when:
- New engineering knowledge added to Serena memories
- Knowledge reclassified across experience tiers
- New problem domains identified
- Agent knowledge requirements change