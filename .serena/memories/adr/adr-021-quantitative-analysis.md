# ADR-019 Quantitative Verification Findings

**Analyzed**: 2025-12-23 | **Analyst**: Claude Opus 4.5
**Full Report**: `.agents/analysis/083-adr-017-quantitative-verification.md`

---

## Key Corrections to ADR-019 Claims

| ADR Claim | Original | Corrected |
|-----------|----------|-----------|
| 78% token reduction | 130 vs 600 tokens | 27.6% (uncached) OR 81.6% (cached) |
| 2.25x efficiency | Fixed ratio | 4.62x (cached) OR 0.48x (uncached) |
| Token costs | 150 vs 600 | 243 vs 1,325 (measured) |

**Root Cause**: ADR excludes memory-index (2,639 tokens) from calculations, assuming it is cached.

---

### Break-Even Point

**Tiered loses to consolidated when needing 9+ skills** from same domain.

**Formula**:

```text
n_breakeven = (C_consolidated - C_domain_index) / C_atomic_avg
            = (1,325 - 98) / 145
            = 8.46 skills
```

**Retrieval Pattern Efficiency**:

| Skills Retrieved | Tiered (Cached) | Consolidated | Winner |
|------------------|-----------------|--------------|--------|
| 1 skill | 243 tokens | 1,325 tokens | Tiered (5.5x) |
| 3 skills | 533 tokens | 1,325 tokens | Tiered (2.5x) |
| 9 skills | 1,403 tokens | 1,325 tokens | Consolidated (1.06x) |
| All 12 (CodeRabbit) | 1,838 tokens | 1,415 tokens | Consolidated (1.3x) |

**Guideline**: Use tiered when typical retrieval needs **≤70% of domain content**.

---

### Maintenance Overhead at Scale

| Total Memories | Files (Tiered) | Files (Consolidated) | Overhead |
|----------------|----------------|----------------------|----------|
| 100 | 121 | 100 | +21% |
| 500 | 601 | 500 | +20% |
| 1000 | 1,201 | 1,000 | +20% |

**Operations Impacted** (vs Consolidated):

- Add skill: 1.5x time (create file + update index)
- Delete skill: 1.3x time (delete file + update index)
- Rename skill: 1.5x time (rename file + update index)
- Audit completeness: 2.0x time (verify index ↔ atomic consistency)

**Mitigation**: Automated CI validation for index consistency is **mandatory**.

---

### Edge Cases Where Consolidated Wins

1. **Full-domain retrieval**: Need 9+ skills from 12-skill domain
2. **High co-occurrence**: Skills always retrieved together
3. **Small domains**: 1-2 skills (index overhead exceeds benefit)
4. **Cold start**: Memory-index not cached (adds 2,639-token overhead)
5. **Index drift**: Atomic file renamed but index not updated

---

### Critical Dependency: Memory-Index Caching

**ADR-019 efficiency claims are valid ONLY if memory-index (2,639 tokens) is cached** across MCP `read_memory` calls.

**Without caching**:

- Single skill: Tiered uses **3.7x MORE tokens** than consolidated (3,964 vs 1,325)
- Tiered becomes worse for ALL retrieval patterns

**Status**: Assumption not documented in ADR-019. MCP caching behavior not verified.

---

### Recommendations (P0)

1. **Document caching assumption** in ADR-019 (10 min)
2. **Add CI check for index ↔ atomic file consistency** (2 hours)
3. **Establish domain consolidation threshold** (30 min):
   - Use tiered: ≥3 skills, ≤70% typical retrieval, low co-occurrence
   - Use consolidated: ≤2 skills, high co-occurrence, rarely accessed

---

### Measured Data (Copilot Domain)

**Consolidated (Pre-Tiered)**:

- `skills-copilot.md`: 5,300 bytes / 1,325 tokens

**Tiered (Current)**:

- `skills-copilot-index.md`: 391 bytes / 98 tokens
- `copilot-platform-priority.md`: 528 bytes / 132 tokens
- `copilot-follow-up-pr.md`: 378 bytes / 95 tokens
- `copilot-pr-review.md`: 833 bytes / 208 tokens
- Total atomic: 1,739 bytes / 435 tokens

**Routing**:

- `memory-index.md`: 10,554 bytes / 2,639 tokens

**Token approximation**: 1 token ≈ 4 characters (GPT-3 rule)

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
- [adr-021-split-execution](adr-021-split-execution.md)
