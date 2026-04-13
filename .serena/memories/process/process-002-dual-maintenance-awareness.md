# Process: Dual Maintenance Awareness

## Skill-Process-002: Dual Maintenance Awareness

**Statement**: When updating agent templates, check if Claude agents require manual sync

**Context**: When modifying shared agent templates (templates/agents/*.shared.md)

**Evidence**: Issue #44 Phase 4 - 4 Claude agents (src/claude/*.md) required manual sync after template updates because they are not part of Generate-Agents.ps1 automation

**Impact**: Prevents incomplete updates, ensures Claude agents stay synchronized with shared templates

**Atomicity**: 90%

**Tags**: helpful, consistency, manual-check

## Pattern: Agent Dual Maintenance

**Pattern Name**: Dual-mode agent maintenance

**Description**: Agent files exist in two maintenance modes:

1. **Generated agents**: copilot-cli and vs-code platforms regenerated via Generate-Agents.ps1 from shared templates
2. **Manual agents**: src/claude/*.md require manual synchronization after template changes

**Evidence**: Commit e46bec1 updated 4 shared templates, regenerated 8 platform agents, and manually synchronized 4 Claude agents (16 files total)

**Risk**: Divergence over time without vigilance

**Mitigation**:

- Document in CONTRIBUTING.md which agents are generated vs. manual
- Consider drift detection automation (extend Validate-Consistency.ps1)
- Add checklist to agent update tasks

## Improvement Opportunities

### P1: Document Dual Maintenance Pattern

- Add to CONTRIBUTING.md or agent documentation
- List which agents are generated (copilot-cli, vs-code)
- List which agents require manual sync (src/claude/*.md)
- Provide checklist for agent updates

### P1: Drift Detection Automation

- Extend Validate-Consistency.ps1 to compare Claude agents with shared templates
- Run in CI to catch divergence early
- Flag when manual sync needed

### P2: Unified Agent Generation

- Explore single source of truth for all agents
- Platform-specific frontmatter only
- Eliminate dual maintenance burden

## SMART Validation Results

All 4 skills passed SMART validation with atomicity scores 90-98%:

- Specific: Single concept, no compound statements
- Measurable: Can verify application
- Attainable: Demonstrated in execution
- Relevant: Applies to real scenarios
- Timely: Clear trigger conditions

## ROTI: 3 (High Return)

**Benefits**: 4 high-quality skills, 3 improvement opportunities identified, process patterns documented

**Time**: ~30-40 minutes

**Verdict**: Continue - High-value retrospective for new capability rollout