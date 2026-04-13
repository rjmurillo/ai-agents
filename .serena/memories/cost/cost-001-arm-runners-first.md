# Skill-Cost-001: ARM Runners First

> **STATUS**: ⚠️ **NOT APPLICABLE** for public repositories
>
> This skill was based on incorrect cost assumptions. GitHub provides **FREE** runners for public repos.

**Statement**: ~~Use ubuntu-24.04-arm for new GitHub Actions workflows~~

**Correction (2025-12-21)**:

For **PUBLIC repositories** (like ai-agents):
- Runner architecture (ARM vs x64) has **NO cost impact**
- Both `ubuntu-latest` and `ubuntu-24.04-arm` are **FREE**
- ADR-007 was **REJECTED** based on this finding

For **PRIVATE repositories**:
- This skill may still apply (37.5% cost savings)
- Verify current GitHub Actions pricing before applying

**Context**: When creating or modifying GitHub Actions workflow files

**Why This Changed**:

GitHub provides free unlimited usage of standard runners for public repositories. The original skill was created without verifying the repository visibility, leading to incorrect cost optimization recommendations.

**Current Recommendation** (Public Repos):

- Use `ubuntu-latest` for maximum compatibility
- ARM only for performance testing (not cost)
- No runner-related cost optimization needed

**Evidence**:

- [GitHub: ARM runners free for public repos (Jan 2025)](https://github.blog/changelog/2025-01-16-linux-arm64-hosted-runners-now-available-for-free-in-public-repositories-public-preview/)
- ADR-007 rejection (2025-12-21)
- Repository visibility: PUBLIC (`gh repo view --json visibility`)

**RFC 2119 Level**: ~~MUST~~ → **N/A** (no cost benefit)

**Atomicity**: 98%

**Tag**: invalidated

**Impact**: ~~9/10~~ → 0/10 (for public repos)

**Created**: 2025-12-20

**Invalidated**: 2025-12-21

**Category**: CI/CD Cost Optimization

**Lesson Learned**: Always verify repository visibility and free tier eligibility before making cost-based recommendations.
