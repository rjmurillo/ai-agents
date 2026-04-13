# Issue Triage Analysis: 2025-12-30

**Generated**: 2025-12-30
**Session**: 112
**Total Open Issues**: 155

## Summary Statistics

| Metric | Count |
|--------|-------|
| Total Open Issues | 155 |
| P0 (Critical) | 32 |
| P1 (Important) | 46 |
| P2 (Normal) | 70 |
| P3 (Low) | 4 |
| No Priority | 22 |
| With bug label | 43 |
| With enhancement label | 139 |
| With documentation label | 54 |
| Epics | 3 |
| Stories | 5 |
| Tasks | 22 |

## Priority Distribution Issues

### Conflicting Priority Labels (MUST Fix)

The following issues have multiple priority labels, which violates the single-priority principle:

| Issue | Title | Conflicting Labels | Recommended |
|-------|-------|--------------------|-------------|
| #681 | feat(git-hooks): add pre-commit branch validation hook | P0, P1 | Keep P0 |
| #657 | Task: Add metrics counter for investigation-only skips | P0, P1 | Keep P1 |
| #651 | User Story: Documentation for investigation-only mode | P0, P1 | Keep P1 |
| #650 | User Story: Validator recognizes investigation-only sessions | P0, P1 | Keep P0 |
| #649 | Epic: ADR-034 Investigation Session QA Exemption | P0, P1 | Keep P0 |
| #643 | bug(issue): Post-IssueComment fails with 403 | P0, P2 | Keep P0 |
| #638 | bug(pr): Test-PRMergeReady required checks only | P0, P2 | Keep P0 |
| #631 | bug(pr): Test-PRMergeReady non-required checks | P0, P2 | Keep P0 |
| #633 | feat(pr): add skill to list/filter PRs | P1, P2 | Keep P2 |
| #621 | Implement Architect Do Router Gate | P1, P2 | Keep P1 |
| #616 | Implement Critic Review Gate | P1, P2 | Keep P1 |
| #612 | Phase 1: Core ADR-033 Gates | P0, P1 | Keep P0 |
| #586 | M2-002: Define Skill Index Schema | P0, P1 | Keep P0 |
| #585 | M2-001: Create Skill Catalog MCP Scaffold | P0, P1 | Keep P0 |
| #444 | Test Strategy Overhaul | P1, P2 | Keep P1 |
| #324 | EPIC: 10x Velocity Improvement | P0, P1 | Keep P0 |
| #289 | perf(github-mcp): Implement GitHub MCP | P1, P2 | Keep P1 |
| #286 | perf(gh-skills): Rewrite GitHub skills | P1, P2 | Keep P1 |
| #265 | EPIC: Pre-PR Validation System | P0, P1 | Keep P0 |

**Action**: Remove duplicate priority labels. Keep the higher priority for P0/P1 conflicts; keep lower for P1/P2 conflicts (more realistic).

---

## Duplicate Clusters (MUST Consolidate)

### Cluster 1: Branch Verification (7 issues)

These issues all address the same root cause: preventing commits on wrong branches.

| Issue | Title | Focus | Recommendation |
|-------|-------|-------|----------------|
| **#684** | feat(protocol): add mandatory branch verification to SESSION-PROTOCOL | Protocol level | **KEEP - Primary** |
| #679 | feat(protocol): add branch verification gate to SESSION-PROTOCOL | Protocol level | CLOSE - Duplicate of #684 |
| **#681** | feat(git-hooks): add pre-commit branch validation hook | Pre-commit hook | **KEEP - Primary** |
| #678 | feat(git-hooks): add pre-commit hook for branch name validation | Pre-commit hook | CLOSE - Duplicate of #681 |
| #680 | feat(hooks): Claude Code hook for git commands | Claude Code hook | CLOSE - Subsume into #682 |
| **#682** | feat(agent-workflow): add git command verification hook | Agent workflow | **KEEP - Primary** |
| #685 | feat(templates): add branch declaration field | Template update | CLOSE - Part of #684 |

**Consolidation Strategy**: Keep #684 (protocol), #681 (git hook), #682 (agent hook). Close #678, #679, #680, #685 as duplicates/subsumed.

### Cluster 2: PR Merge Readiness (4 issues)

| Issue | Title | Focus | Recommendation |
|-------|-------|-------|----------------|
| **#638** | bug(pr): Test-PRMergeReady required checks only | Required checks | **KEEP - Primary** |
| #631 | bug(pr): Test-PRMergeReady non-required checks | Same issue | CLOSE - Duplicate of #638 |
| **#639** | bug(pr): Get-PRChecks machine-only output | Output format | **KEEP - Primary** |
| #632 | bug(pr): Get-PRChecks mixes JSON with human | Same issue | CLOSE - Duplicate of #639 |

**Consolidation Strategy**: Keep #638 and #639. Close #631 and #632 as duplicates.

### Cluster 3: Skill Catalog/Registry (3 overlapping epics)

| Issue | Title | Focus | Recommendation |
|-------|-------|-------|----------------|
| #220 | feat: Skill Catalog MCP (ADR-012) | MCP implementation | Review for overlap |
| #581 | EPIC: Skills Index Registry | Index/governance | Review for overlap |
| #585-589 | M2-001 to M2-004 (Skill Catalog tasks) | Implementation tasks | Link to parent epic |

**Action**: Clarify relationship between #220 and #581. They may be complementary (MCP tool vs registry structure) or duplicates.

### Cluster 4: MCP Scaffolds (3 related)

| Issue | Title | Scope |
|-------|-------|-------|
| #219 | feat: Session State MCP (ADR-011) | Session management |
| #220 | feat: Skill Catalog MCP (ADR-012) | Skill discovery |
| #221 | feat: Agent Orchestration MCP (ADR-013) | Agent coordination |

These are distinct but should be linked as a cohesive MCP initiative.

### Cluster 5: Metrics/DX Framework (10 issues)

| Issue | Title | Status |
|-------|-------|--------|
| #136 | epic: Developer Experience (DX) Metrics Framework | Epic - no priority |
| #128-134 | research: Add X metrics to Y agent | Research - no priority |
| #151 | DORA metrics adapted for AI | P2 |
| #169 | Add Metrics Collection Dashboard | No priority |

**Action**: These research issues lack priority and milestone. Evaluate if still relevant or close as stale.

---

## Issues Missing Information

### No Priority Label (22 issues)

These issues MUST have a priority assigned:

| Issue | Title | Suggested Priority |
|-------|-------|-------------------|
| #209 | bug: GitHub Actions disabled for rjmurillo-bot | P0 (blocks all workflows) |
| #186 | feat: Mention-driven @rjmurillo-bot workflow | P2 |
| #171 | feat: Consensus Mechanisms for Multi-Agent | P3 |
| #170 | feat: Lifecycle Hooks for Session Automation | P2 |
| #169 | feat: Metrics Collection Dashboard | P2 |
| #168 | feat: Parallel Agent Execution | P2 |
| #167 | feat: Vector Memory System | P3 |
| #165 | feat(ci): Caching for Copilot API | P2 |
| #160 | Add directory structure guidance to architect | P2 |
| #159 | Define test location standards | P2 |
| #158 | Add DRY verification to code review | P2 |
| #157 | Enhance QA agent with test criteria | P1 |
| #136 | epic: Developer Experience Metrics | P2 |
| #128-134 | research: Various DX metrics | P3 |
| #124 | arch: Dual template system decision | P1 |
| #122 | feat(retrospective): Delta to Backlog | P2 |

### Epics/Stories Without Milestone

All 3 epics and 5 stories lack milestones:

| Issue | Title | Type |
|-------|-------|------|
| #665 | Epic: ADR-032 Exit Code Standardization | Epic |
| #649 | Epic: ADR-034 Investigation Session QA | Epic |
| #611 | EPIC: ADR-033 Gate Implementation | Epic |
| #652 | User Story: Defense-in-depth safeguards | Story |
| #651 | User Story: Documentation for investigation | Story |
| #650 | User Story: Validator recognizes investigation | Story |
| #619 | Phase 3: Do Router Mandatory Gates | Story |
| #615 | Phase 2: Merge Gates + Spec Generator | Story |

**Action**: Create milestones for these work items to enable tracking.

---

## Stale/Outdated Issues

### Potentially Stale (90+ days old, no activity)

| Issue | Title | Created | Days Old |
|-------|-------|---------|----------|
| #1 | enhancement: Add GitHub workflow for YAML | 2024-* | 300+ |
| #3 | enhancement: add harden-runner | 2024-* | 300+ |
| #19 | Copilot CLI: User-level agents not loading | 2024-* | 60+ |

**Action**: Review issues older than 90 days. Close if no longer relevant or deprioritize.

---

## Label Inconsistencies

### Bug + Enhancement Labels (33 issues)

These issues have both `bug` and `enhancement` labels. Pick one:

- If it fixes broken behavior: use `bug` only
- If it adds new capability: use `enhancement` only

**Sample Issues to Review**:

| Issue | Title | Recommendation |
|-------|-------|----------------|
| #686 | docs(governance): document trust-based compliance | enhancement only |
| #685 | feat(templates): add branch declaration field | enhancement only |
| #684 | feat(protocol): add mandatory branch verification | enhancement only |
| #681 | feat(git-hooks): add pre-commit branch validation | enhancement only |
| #643 | bug(issue): Post-IssueComment fails with 403 | bug only |

---

## Clarification Questions

### Issues Needing Author Input

The following issues need clarification. Draft comments provided:

#### #209: GitHub Actions disabled for rjmurillo-bot

**Question**: @rjmurillo-bot Is this issue still active? GitHub Actions appear to be working now. Should this be closed as resolved, or is there still a problem?

#### #124: Strategic decision on dual template system

**Question**: @rjmurillo-bot This architectural decision has been open for 10+ days. What is the current thinking? Should we schedule a focused review session to resolve this?

#### #99: Imperfect README

**Question**: @rjmurillo-bot What specific improvements are needed? Can you provide acceptance criteria or examples of what a "perfect" README looks like?

#### #51: Add install support for (big) VS

**Question**: @rjmurillo-bot What does "(big) VS" refer to? Visual Studio (not VS Code)? What installation artifacts are needed?

---

## Recommended Actions Summary

### Immediate (P0)

1. **Fix conflicting priorities**: Remove duplicate priority labels from 19 issues
2. **Close duplicates**: Consolidate branch verification cluster (#678, #679, #680, #685)
3. **Close duplicates**: Consolidate PR merge cluster (#631, #632)
4. **Assign priority**: Add P0 to #209 (GitHub Actions blocker)

### Short-term (P1)

1. **Assign priorities**: Add priority labels to 22 unlabeled issues
2. **Create milestones**: Add milestones for 3 epics and 5 stories
3. **Clarify relationship**: Link or merge #220 and #581 (Skill Catalog)
4. **Fix label conflicts**: Remove dual bug/enhancement labels from 33 issues

### Medium-term (P2)

1. **Review stale issues**: Triage issues older than 90 days
2. **Post clarification questions**: Ask authors about unclear issues
3. **Link MCP initiatives**: Connect #219, #220, #221 as cohesive work

---

## Appendix: Issue Counts by Label

| Label | Count |
|-------|-------|
| enhancement | 139 |
| area-workflows | 86 |
| priority:P2 | 70 |
| documentation | 54 |
| agent-qa | 49 |
| area-skills | 48 |
| priority:P1 | 46 |
| area-infrastructure | 43 |
| bug | 43 |
| area-prompts | 34 |
| priority:P0 | 32 |
| automation | 28 |
| agent-retrospective | 23 |
| task | 22 |
| agent-security | 18 |
| agent-roadmap | 15 |
| agent-memory | 14 |
| skill-conversion | 12 |
| gate | 11 |
| agent-implementer | 10 |
| adr-033 | 9 |
| agent-architect | 8 |
| agent-orchestrator | 8 |
| agent-critic | 7 |
| agent-devops | 7 |
