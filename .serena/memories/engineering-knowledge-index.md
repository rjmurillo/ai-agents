# Engineering Knowledge Index

Comprehensive index of engineering knowledge across 5 experience tiers.

## How to Use This Index

1. **By Experience Level**: Find knowledge appropriate to your experience tier
2. **By Concept**: Look up specific mental models, frameworks, or patterns
3. **By Problem Domain**: Find relevant knowledge for specific challenges

## Knowledge by Experience Tier

### Tier 1: Foundational (<5 Years)

**Mental Models**:
- `chestertons-fence`: Understand before removing
- `conways-law`: Org structure mirrors architecture
- `hyrums-law`: Observable behaviors become dependencies
- `second-order-thinking`: Ask "And then what?"
- `law-of-demeter`: Only talk to immediate friends
- `galls-law`: Complex systems evolve from simple ones
- `yagni`: You aren't gonna need it
- `technical-debt-quadrant`: Deliberate vs inadvertent, prudent vs reckless
- `boy-scout-rule`: Leave code better than you found it

**Principles**:
- `solid-principles`: Single responsibility, open-closed, Liskov, interface segregation, dependency inversion
- `dry-principle`: Don't repeat yourself
- `kiss-principle`: Keep it simple
- `separation-of-concerns`: Decompose into non-overlapping parts
- `tell-dont-ask`: Bundle data with behavior
- `programming-by-intention`: Express intent over implementation

**Practices**:
- `tdd-red-green-refactor`: Test-driven development cycle
- `clean-architecture`: Domain at center, dependencies point inward
- `twelve-factor-app`: Cloud-ready application methodology
- `trunk-based-development`: Frequent commits to shared trunk
- `observability-three-pillars`: Logs, metrics, traces

### Tier 2: Advanced (5-10 Years)

**Architectural Models**:
- `c4-model`: Context, container, component, code
- `cap-theorem`: Consistency, availability, partition tolerance
- `resilience-patterns`: Circuit breaker, bulkheads, retries, timeouts
- `idempotency`: Operations safe to retry
- `poka-yoke`: Design to prevent errors

**Patterns**:
- `strategy-pattern`: Vary behavior at runtime
- `decorator-pattern`: Add behavior dynamically
- `null-object-pattern`: Avoid null checks
- `specification-pattern`: Encapsulate business rules

**Security**:
- `owasp-top-10`: Web vulnerabilities
- `principle-of-least-privilege`: Minimal permissions needed

### Tier 3: Senior (10-15 Years)

**Trade-Off Thinking**:
- `coupling-vs-duplication`: When to copy vs share
- `speed-vs-safety`: Fast vs validated
- `complexity-vs-flexibility`: General vs specific

**Design Practices**:
- `design-for-replaceability`: Favor replaceability over reuse
- `design-by-contract`: Preconditions, postconditions, invariants
- `policy-vs-mechanism`: Separate rules from execution
- `fallacies-of-distributed-computing`: Network assumptions that fail

**Evolution Patterns**:
- `feature-toggles`: Decouple deployment from release
- `branch-by-abstraction`: Large refactorings safely
- `strangler-fig-pattern`: Incremental legacy migration
- `expand-contract-migration`: Schema changes without downtime

**Thinking Models**:
- `wardley-mapping`: Capability evolution and strategy
- `cynefin-framework`: Problem classification (clear, complicated, complex, chaotic)
- `antifragility`: Systems that improve from stress
- `rumsfeld-matrix`: Known/unknown knowns/unknowns

**Operability**:
- `slo-sli-sla`: Service level objectives, indicators, agreements
- `error-budgets`: Acceptable unreliability enabling innovation
- `mttr-optimization`: Mean time to recovery
- `blameless-postmortems`: Learning from failures

### Tier 4: Principal (15-25 Years)

**Wisdom**:
- `chestertons-fence`: [Advanced application]
- `conways-law`: [Strategic application with inverse Conway maneuver]
- `paved-roads-guardrails`: Defaults without constraints

**Strategic Models**:
- `wardley-mapping`: [Strategic positioning]
- `cynefin-framework`: [Response strategy selection]
- `ooda-loop`: Observe, orient, decide, act
- `inversion-thinking`: How would this fail?
- `critical-path-method`: Focus on longest dependency chain
- `systems-archetypes`: Fixes that fail, shifting burden, limits to growth

**Architecture**:
- `adrs-architecture-decision-records`: Capture decisions with context
- `sociotechnical-design`: Align org and architecture (Team Topologies)
- `fitness-functions`: Automated architectural intent verification
- `products-over-projects`: Durable teams over temporary funding

**Risk & Resilience**:
- `slos-error-budgets`: Balance reliability and velocity
- `chaos-engineering`: Confidence through controlled failure
- `threat-modeling`: Structured security risk identification
- `pre-mortems`: Identify failure modes before starting

**Organizational Leadership**:
- `engineering-strategy`: Vision, strategy, specifications
- `platform-engineering`: Self-service developer capabilities
- `buy-vs-build-framework`: Core vs context evaluation
- `migrations-at-scale`: Incremental transformation

### Tier 5: Distinguished (25+ Years)

**Legacy Thinking**:
- `lindy-effect`: Older technology has longer expected life
- `second-system-effect`: Resist over-engineering replacements
- `path-dependence`: Historical constraints on current choices
- `architectural-paleontology`: Understanding design layers
- `golden-path-vs-golden-cage`: Enable without constraining

**Governance**:
- `sociotechnical-coherence`: Align technology with org dynamics
- `run-vs-change-business`: Separate operations from innovation
- `systemic-risk-portfolios`: Classify dependencies and failure risk
- `compliance-as-code`: Policy enforcement via automation
- `data-lineage-sovereignty`: Track data across jurisdictions

**Migration**:
- `strangler-fig-pattern`: [Strategic application]
- `expand-contract`: [Schema evolution]
- `capability-based-migration`: User-facing capabilities over technical components
- `sacrificial-architecture`: Plan for replacement
- `core-context-mapping`: Invest in differentiation, buy commodities

**Time Horizons**:
- `three-horizons-framework`: Balance current (H1), emerging (H2), future (H3)
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
- `wardley-mapping`: [Strategic application]

## Knowledge by Problem Domain

### Decision-Making
- Tier 1: `second-order-thinking`, `technical-debt-quadrant`
- Tier 3: `cynefin-framework`, `rumsfeld-matrix`
- Tier 4: `ooda-loop`, `inversion-thinking`, `pre-mortems`

### Architecture
- Tier 1: `clean-architecture`, `separation-of-concerns`
- Tier 2: `c4-model`, `cap-theorem`, `poka-yoke`
- Tier 3: `wardley-mapping`, `strangler-fig-pattern`
- Tier 4: `adrs-architecture-decision-records`, `sociotechnical-design`, `fitness-functions`
- Tier 5: `second-system-effect`, `architectural-paleontology`, `sacrificial-architecture`

### Change Management
- Tier 1: `chestertons-fence`, `boy-scout-rule`
- Tier 3: `feature-toggles`, `branch-by-abstraction`, `expand-contract-migration`
- Tier 4: `migrations-at-scale`
- Tier 5: `strangler-fig-pattern`, `capability-based-migration`

### Legacy Systems
- Tier 1: `chestertons-fence`, `galls-law`
- Tier 3: `strangler-fig-pattern`, `expand-contract-migration`
- Tier 5: `lindy-effect`, `second-system-effect`, `path-dependence`, `architectural-paleontology`

### Strategic Planning
- Tier 3: `wardley-mapping`, `cynefin-framework`, `antifragility`
- Tier 4: `ooda-loop`, `critical-path-method`, `products-over-projects`
- Tier 5: `three-horizons-framework`, `core-context-mapping`

### Operability & Reliability
- Tier 1: `observability-three-pillars`
- Tier 2: `resilience-patterns`, `idempotency`
- Tier 3: `slo-sli-sla`, `error-budgets`, `mttr-optimization`, `blameless-postmortems`
- Tier 4: `chaos-engineering`, `threat-modeling`

### Organization Design
- Tier 1: `conways-law`
- Tier 4: `sociotechnical-design`, `platform-engineering`
- Tier 5: `sociotechnical-coherence`, `run-vs-change-business`, `knowledge-continuity`

## Query Examples

**By Memory Name**:
```python
mcp__serena__read_memory(memory_file_name="cynefin-framework")
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
mcp__serena__read_memory(memory_file_name="ooda-loop")
mcp__serena__read_memory(memory_file_name="inversion-thinking")
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
