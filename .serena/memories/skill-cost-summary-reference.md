# Cost Optimization Skills Summary

Reference document linking all cost avoidance skills with quick comparison.

> **IMPORTANT (2025-12-21)**: This repository is **PUBLIC**. GitHub Actions runners are **FREE**.
> Skills related to runner architecture (ARM, Windows) have **NO cost impact** here.
> Focus on: Token costs (Claude API), Artifact storage, Workflow efficiency.

## Skills Index

| Skill ID | Focus Area | Savings % | Impact | RFC Level | Notes |
|----------|-----------|-----------|--------|-----------|-------|
| ~~Skill-Cost-001~~ | ~~ARM Runners~~ | ~~37.5%~~ | ~~9/10~~ | ~~MUST~~ | **N/A for public repos** |
| Skill-Cost-002 | No Artifacts Default | 60-80% | 8/10 | MUST | ✅ Still applies |
| Skill-Cost-003 | Path Filters | Reduce noise | 7/10 | SHOULD | ✅ Reduces bot runs |
| Skill-Cost-004 | Concurrency Cancel | Reduce noise | 6/10 | SHOULD | ✅ Reduces bot runs |
| Skill-Cost-005 | Serena Symbolic | 80%+ | 10/10 | MUST | ✅ Token savings |
| Skill-Cost-006 | Memory Caching | 90% | 10/10 | MUST | ✅ Token savings |
| Skill-Cost-007 | Haiku Quick Tasks | 98% | 9/10 | SHOULD | ✅ Token savings |
| Skill-Cost-008 | Artifact Compression | 70-90% | 7/10 | MUST | ✅ Still applies |
| Skill-Cost-009 | Debug on Failure | 90% | 8/10 | MUST | ✅ Still applies |
| ~~Skill-Cost-010~~ | ~~Avoid Windows~~ | ~~69%~~ | ~~9/10~~ | ~~MUST NOT~~ | **N/A for public repos** |
| Skill-Cost-011 | Retention Minimum | 93% | 8/10 | MUST | ✅ Still applies |
| Skill-Cost-012 | Offset/Limit Reads | 99% | 7/10 | SHOULD | ✅ Token savings |

## Cost Reference Table

### GitHub Actions Runners (PUBLIC REPOS)

| Runner | Cost | Notes |
|--------|------|-------|
| All standard runners | **FREE** | Public repos only |
| ubuntu-latest | FREE | Use for compatibility |
| ubuntu-24.04-arm | FREE | Use for performance testing |
| windows-latest | FREE | Use when needed |

### GitHub Actions Runners (PRIVATE REPOS - for reference)

| Runner | Cost/Min | Monthly (100h) | vs ARM |
|--------|----------|----------------|--------|
| ubuntu-24.04-arm | $0.005 | $30 | Baseline |
| ubuntu-latest | $0.008 | $48 | +60% |
| windows-latest | $0.016 | $96 | +220% |
| macOS-latest | $0.080 | $480 | +1500% |

### Claude API Tokens

| Model | Input (no cache) | Input (cache) | Output | Use When |
|-------|------------------|---------------|--------|----------|
| Opus 4.5 | $15/M | $1.50/M | $75/M | Complex reasoning |
| Sonnet 4.5 | $3/M | $0.30/M | $15/M | Balanced tasks |
| Haiku 4.5 | $0.25/M | $0.025/M | $1.25/M | Quick tasks |

### GitHub Artifact Storage

| Resource | Cost | Notes |
|----------|------|-------|
| Storage | $0.25/GB/month | Billed daily |
| Compression | Free | 70-90% size reduction |
| Retention | Linear | 90 days = 12.9x cost of 7 days |

## High-Impact Quick Wins

**Token Cost Savings** (Highest ROI for this repo):

1. **Use Serena tools** (Skill-Cost-005)
   - Replace Read with find_symbol
   - 80%+ token reduction

2. **Read memories first** (Skill-Cost-006)
   - Call before work starts
   - 90% cache savings

3. **Use Haiku for quick tasks** (Skill-Cost-007)
   - 98% cheaper than Opus
   - Good for simple queries

**Artifact Cost Savings**:

4. **Audit artifacts** (Skill-Cost-002, 008, 009, 011)
   - Review each upload
   - Add justifications
   - Set short retention
   - 60-80% storage savings

**Workflow Efficiency** (Reduces bot noise, not costs):

5. **Add path filters** (Skill-Cost-003)
   - Add 4 lines to workflow file
   - Fewer unnecessary runs

6. **Add concurrency** (Skill-Cost-004)
   - Add 3 lines to workflow file
   - Cancel duplicate runs

**NOT Applicable for Public Repos**:

- ~~Migrate to ARM (Skill-Cost-001)~~ - No cost impact
- ~~Avoid Windows (Skill-Cost-010)~~ - No cost impact

## Enforcement Checklist

**For Workflow Changes**:

- [ ] Has path filters (Skill-Cost-003) - SHOULD
- [ ] Has concurrency block (Skill-Cost-004) - SHOULD
- [ ] No artifacts OR justified with ADR-008 (Skill-Cost-002)
- [ ] Artifacts use compression-level: 9 (Skill-Cost-008)
- [ ] Debug artifacts use if: failure() (Skill-Cost-009)
- [ ] Retention ≤7 days (Skill-Cost-011)
- ~~[ ] Uses `ubuntu-24.04-arm` (Skill-Cost-001)~~ - N/A for public repos
- ~~[ ] No Windows runner unless justified (Skill-Cost-010)~~ - N/A for public repos

**For Agent Sessions**:

- [ ] Read memories before work (Skill-Cost-006)
- [ ] Use Serena symbolic tools (Skill-Cost-005)
- [ ] Use offset/limit for large files (Skill-Cost-012)
- [ ] Consider Haiku for quick tasks (Skill-Cost-007)

## Related Documents

- [COST-GOVERNANCE.md](../../.agents/governance/COST-GOVERNANCE.md)
- [ADR-007: GitHub Actions Runner Selection](../../.agents/architecture/ADR-007-github-actions-runner-selection.md)
- [ADR-008: Artifact Storage Minimization](../../.agents/architecture/ADR-008-artifact-storage-minimization.md)
- [SESSION-PROTOCOL.md](../../.agents/SESSION-PROTOCOL.md) Phase 5

## Version

- **Created**: 2025-12-20
- **Updated**: 2025-12-21 (Marked Skill-Cost-001, 010 as N/A for public repos)
- **Skills Count**: 12 (10 applicable for public repos)
- **Total Potential Savings**: Token costs (80-90%), Artifact storage (60-80%). Runner costs: N/A (free for public repos)
