# Roadmap Skills

**Extracted**: 2025-12-16
**Source**: `.agents/roadmap/` directory

## Skill-Roadmap-001: RICE-KANO Scoring (85%)

**Statement**: Prioritize features using RICE score combined with KANO model classification

**Context**: Backlog grooming and feature prioritization

**Evidence**: Product roadmap document with prioritization framework

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 7/10

**RICE Formula**:

```text
Score = (Reach × Impact × Confidence) / Effort
```

**KANO Categories**:

- **Must-have**: Expected features, dissatisfaction if missing
- **Performance**: More is better, linear satisfaction
- **Delighter**: Unexpected features, high satisfaction

**Combined Approach**:

1. Calculate RICE score for all items
2. Apply KANO classification
3. Prioritize: Must-haves first, then Delighters, then Performance
4. Within each KANO category, order by RICE score

**Source**: `.agents/roadmap/product-roadmap.md`

---

## Related Documents

- Source: `.agents/roadmap/product-roadmap.md`
- Related: skills-planning (task prioritization)
