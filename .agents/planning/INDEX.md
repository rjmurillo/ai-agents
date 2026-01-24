# Planning Directory Index

**Last Updated**: 2026-01-23
**Total Planning Docs**: Active tracking
**Current Milestone**: v0.3.0 (Memory Enhancement + Quality)

---

## Purpose

This directory contains:
- **Implementation Plans**: Detailed task breakdowns for features
- **PRDs**: Product requirements documents (subset, see `.agents/specs/` for full catalog)
- **Task Lists**: Milestone-based work tracking
- **Phase Documentation**: Multi-phase project plans

---

## Active Plans

**Currently being implemented or actively referenced:**

| Document | Type | Status | Related Issue/PR |
|----------|------|--------|------------------|
| **[v0.3.0/PLAN.md](./v0.3.0/PLAN.md)** | **Milestone Plan** | **🟢 ACTIVE** | **v0.3.0 (23 issues)** |
| [phase2b-memory-sync-strategy.md](./phase2b-memory-sync-strategy.md) | Strategy | Active | #747 |
| [prd-workflow-orchestration-enhancement.md](./prd-workflow-orchestration-enhancement.md) | PRD | ⚠️ Deferred | Epic #739 (Future) |
| [prd-agent-consolidation.md](./prd-agent-consolidation.md) | PRD | Planning | Epic #907, #972 |
| [prd-visual-studio-install-support.md](./prd-visual-studio-install-support.md) | PRD | Planning | TBD |
| [prd-pre-pr-security-gate.md](./prd-pre-pr-security-gate.md) | PRD | Planning | TBD |

### v0.3.0 Milestone (Current Focus)

**Master Plan**: [v0.3.0/PLAN.md](./v0.3.0/PLAN.md)

| Focus Area | Issues | Key Deliverables |
|------------|--------|------------------|
| Memory Enhancement | #997, #998, #999, #1001 | Citations, graph traversal, health reporting |
| Memory Optimization | #751, #734, #747, #731 | Unified interface, 13x performance |
| Traceability | #724, #721, #722, #723 | Graph implementation, spec tooling |
| Quality & Testing | #749, #778, #840 | Testing philosophy, coverage |
| Skill Quality | #761, #809 | v2.0 compliance, session-end skill |
| CI/CD | #77, #90, #71, #101 | Permissions, documentation |

**Parallel Chains**: 6 independent worktrees for concurrent execution. See plan for details.

---

## Reference Plans

**Completed or historical plans useful for context:**

| Document | Type | Archived | Notes |
|----------|------|----------|-------|
| [phase1-completion-summary.md](../archive/phase1-completion-summary.md) | Summary | ✅ | Moved to archive |
| [phase2-complete-handoff.md](../archive/phase2-complete-handoff.md) | Handoff | ✅ | Moved to archive |
| [phase3-complete-handoff.md](../archive/phase3-complete-handoff.md) | Handoff | ✅ | Moved to archive |
| [phase4-complete-handoff.md](../archive/phase4-complete-handoff.md) | Handoff | ✅ | Moved to archive |
| [pr-60-*.md](../archive/) | PR Plans | ✅ | 7 files, PR #60 merged |
| [pr43-remediation-plan.md](../archive/pr43-remediation-plan.md) | PR Plan | ✅ | PR #43 merged |
| [pr830-remediation-plan.md](../archive/pr830-remediation-plan.md) | PR Plan | ✅ | PR #830 merged |
| [plan-pr760-fixes.md](../archive/plan-pr760-fixes.md) | PR Plan | ✅ | PR #760 merged |
| [265-*.md](../archive/) | Epic Plans | ✅ | 4 files, Epic #265 complete (v0.2.0) |

---

## Plans by Category

### Phase Documentation

Multi-phase project plans and handoffs:

- `phase1-handoff-remediation-pr43.md` - Phase 1 remediation work
- `phase2-handoff.md` - Phase 2 planning
- `phase2b-memory-sync-strategy.md` - Memory synchronization strategy (active)

### Product Requirements (PRDs)

High-level feature descriptions (also tracked in `.agents/specs/`):

- `prd-workflow-orchestration-enhancement.md` - Workflow improvements
- `prd-agent-consolidation.md` - Agent system consolidation
- `prd-visual-studio-install-support.md` - VS integration
- `prd-pre-pr-security-gate.md` - Security gate design

### Implementation Plans

Task-level breakdowns for specific features:

- `pr-automation-implementation-plan.md` - PR automation workflow
- `pr-maintenance-matrix-processing-plan.md` - Maintenance matrix

### Prompt Documentation

Agent and workflow prompts:

- `prompts-acknowledged-vs-resolved.md` - Comment handling patterns

---

## Naming Conventions

### Implementation Plans
- **Format**: `PLAN-{feature-name}.md` or `{feature}-implementation-plan.md`
- **Purpose**: Task breakdown with acceptance criteria
- **Contains**: Tasks, dependencies, milestones, exit criteria

### Product Requirements
- **Format**: `prd-{feature-name}.md` or `PRD-{feature-name}.md`
- **Purpose**: Feature specification with user stories
- **Contains**: Problem statement, goals, success metrics, design
- **Note**: Master PRD catalog is in `.agents/specs/STATUS.md`

### Phase Documentation
- **Format**: `phase{N}-{descriptor}.md`
- **Purpose**: Multi-phase project coordination
- **Contains**: Objectives, deliverables, handoff notes

### PR-Specific Plans
- **Format**: `pr{number}-{descriptor}.md` or `plan-pr{number}-{descriptor}.md`
- **Purpose**: Remediation or enhancement plans for specific PRs
- **Lifecycle**: Archive when PR merges

---

## Lifecycle Management

### Active Plans
- Actively being implemented
- Referenced in current session work
- Linked to open GitHub issues/PRs

### Reference Plans
- Completed implementation
- Historical context
- Useful patterns for future work

### Archived Plans
- PR merged or issue closed
- Phase completed
- Epic delivered
- **Location**: `.agents/archive/`

---

## Archive Criteria

Move plans to `.agents/archive/` when:

1. **PR Plans**: Associated PR merged
2. **Phase Plans**: Phase completed and handed off
3. **Epic Plans**: All epic work delivered (e.g., Epic #265)
4. **Superseded Plans**: Replaced by newer planning docs

**Do NOT archive**:
- Active PRDs (keep until implemented)
- Reference patterns (useful for future work)
- Ongoing phase documentation

---

## Creating New Plans

1. **Choose type**: Implementation plan vs PRD vs phase doc
2. **Follow naming**: Use conventions above
3. **Add frontmatter**: Status, author, dates, related issue
4. **Update INDEX.md**: Add entry to "Active Plans"
5. **Link to GitHub**: Create or link tracking issue
6. **Update regularly**: Keep plan status current

---

## Finding Plans

### By Feature
Check `.agents/specs/STATUS.md` for all PRDs and their implementation status.

### By PR Number
Use `git log --all --grep="PR #123"` to find related plans.

### By Issue
Search: `grep -r "#123" .agents/planning/`

### By Status
- **Active**: Listed in "Active Plans" section above
- **Reference**: Listed in "Reference Plans" section
- **Archived**: See `.agents/archive/`

---

## Related Documentation

- [`.agents/specs/`](../specs/) - Specifications and PRDs (master catalog)
- [`.agents/architecture/`](../architecture/) - ADRs (architectural decisions)
- [`.agents/archive/`](../archive/) - Historical documentation
- [`.agents/SESSION-PROTOCOL.md`](../SESSION-PROTOCOL.md) - Session management

---

**Questions?** Create a GitHub issue or see [AGENTS.md](../../AGENTS.md).
