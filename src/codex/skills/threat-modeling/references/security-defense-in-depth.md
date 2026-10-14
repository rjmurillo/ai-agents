---
source: wiki/concepts/Architectural Patterns/Defense in Depth.md
created: 2026-04-11
review-by: 2026-07-11
---

# Defense in Depth

Multiple independent protection layers so that if one fails, others continue to provide security. No single layer is relied upon exclusively.

Core principle: **redundancy in defense, diversity in mechanism**.

## Protection Layer Model

| Layer | Function | Timing |
|-------|----------|--------|
| Reputation | Block known bad (URL, domain, sender) | Pre-access |
| Content | Analyze structure, visual similarity | During access |
| Behavior | Monitor interaction patterns, data flow | Runtime |

Each layer alone is insufficient. Attackers must defeat all layers simultaneously.

## Architectural Principles

### Independence

Each layer must function independently. If one layer is evaded, others still detect.

### Diversity

Layers use different detection mechanisms. A single evasion technique should not bypass multiple layers. Mix signature-based, ML inference, behavioral analysis, reputation systems, and human intelligence.

### Graceful Degradation

When layers fail, the system degrades gracefully. Higher layers catch what lower layers miss.

### Cost-Latency Tradeoff

| Characteristic | Fast Layers | Deep Layers |
|----------------|-------------|-------------|
| Latency | Milliseconds | Minutes to hours |
| Cost | Low per-check | High per-check |
| Accuracy | Lower (heuristic) | Higher (detonation) |
| Coverage | Broad (all traffic) | Selective (suspicious) |

Design so fast/cheap layers filter traffic for expensive/deep layers.

## Applying to Threat Modeling

During Phase 3 (Mitigation Strategy), evaluate mitigations against defense-in-depth criteria:

1. **Layer count**: Does the mitigation add a new independent layer, or duplicate an existing one?
2. **Mechanism diversity**: Does the mitigation use a different detection/prevention mechanism than existing controls?
3. **Failure independence**: If this mitigation fails, do other layers still protect the asset?
4. **Cost placement**: Is this mitigation at the right layer (fast/cheap for broad coverage, slow/expensive for precision)?

### Mitigation Checklist

For each Critical/High threat, verify:

- [ ] At least 2 independent mitigation layers exist
- [ ] Layers use different mechanisms (not just redundant copies)
- [ ] Failure of any single layer does not expose the asset
- [ ] Fast layers filter before expensive layers activate

## Application Beyond Security

| Domain | Layers |
|--------|--------|
| Data integrity | Input validation, business rules, database constraints, backup/restore |
| Service reliability | Load balancing, circuit breakers, retry logic, graceful degradation, alerting |
| Deployment safety | PR review, CI tests, canary deploy, progressive rollout, automatic rollback |
| Observability | Health checks, metrics, distributed tracing, log aggregation, alerting |

## Related

- [Zero Trust](security-zero-trust.md): Complementary model (verify at every layer)
- [Least Privilege](security-least-privilege.md): Minimizes blast radius at each layer
