# Retrospective: Phase 2 CodeRabbit Remediation - Workflow Learnings

**Date**: 2025-12-16
**Issue**: #44 (Phase 2 Consistency Fixes)
**PR**: #49

## Executive Summary

During Phase 2 implementation, changes were made directly to `src/claude/` without also updating the shared templates in `templates/agents/`, causing agent drift and requiring rework.

## What Happened

1. Initial implementation modified only `src/claude/` files:
   - `src/claude/critic.md` - Added escalation template
   - `src/claude/task-generator.md` - Added estimate reconciliation protocol
   - `src/claude/planner.md` - Added condition traceability

2. These changes were NOT made to the shared source files in `templates/agents/`:
   - `templates/agents/critic.shared.md`
   - `templates/agents/task-generator.shared.md`
   - `templates/agents/planner.shared.md`

3. This caused the generated agents (`src/copilot-cli/`, `src/vs-code-agents/`) to drift from the manually-edited `src/claude/` files

## Root Cause

**Incomplete understanding of agent generation workflow**:
- The repository uses a generation pattern: `templates/agents/*.shared.md` → `Generate-Agents.ps1` → `src/copilot-cli/`, `src/vs-code-agents/`
- `src/claude/` appears to be a separate, manually-maintained platform (uses different frontmatter and "Claude Code Tools" section)
- Future agents should understand this tri-platform structure

## Correct Workflow

When modifying agent behavior:

1. **Update shared template first**: Edit `templates/agents/[agent].shared.md`
2. **Run generator**: `pwsh build/Generate-Agents.ps1`
3. **Update src/claude if needed**: This platform has additional content not in shared templates
4. **Verify all platforms**: Check `src/copilot-cli/`, `src/vs-code-agents/`, `src/claude/`
5. **Commit all changes**: Include templates, generated files, and src/claude

## Skills Extracted

### Skill-AgentWorkflow-001
**Statement**: When modifying agent behavior, update `templates/agents/*.shared.md` FIRST, then run `Generate-Agents.ps1`
**Evidence**: Phase 2 changes to src/claude/ required rework to sync with templates
**Pattern**: Generator-based workflow

### Skill-AgentWorkflow-002
**Statement**: `src/claude/` is a separate platform with additional content (Claude Code Tools section) not in shared templates
**Evidence**: Comparison shows Claude agents have extra "Claude Code Tools" section
**Pattern**: Tri-platform structure (Claude, VS Code, Copilot CLI)

### Skill-AgentWorkflow-003
**Statement**: Always verify agent changes appear in all three platform directories after generation
**Evidence**: Changes to templates propagate to generated agents but not to src/claude
**Pattern**: Manual + generated content coexistence

## Recommendations for Future Agents

1. Before making agent changes, run `pwsh build/Generate-Agents.ps1 -Validate` to check for drift
2. Follow the workflow: templates → generate → verify → claude manual update if needed
3. Include all generated files in commits
4. Leave handoff artifacts documenting what was changed and why

## Files Modified in Correction

### Shared Templates
- `templates/agents/critic.shared.md` - Added Escalation Prompt Completeness Requirements
- `templates/agents/task-generator.shared.md` - Added Estimate Reconciliation Protocol
- `templates/agents/planner.shared.md` - Added Condition-to-Task Traceability

### Generated Agents (via Generate-Agents.ps1)
- `src/copilot-cli/critic.agent.md`
- `src/copilot-cli/task-generator.agent.md`
- `src/copilot-cli/planner.agent.md`
- `src/vs-code-agents/critic.agent.md`
- `src/vs-code-agents/task-generator.agent.md`
- `src/vs-code-agents/planner.agent.md`

### Previously Modified (from original Phase 2)
- `src/claude/critic.md`
- `src/claude/task-generator.md`
- `src/claude/planner.md`

## Validation Script Created

- `build/scripts/Validate-PlanningArtifacts.ps1` - Cross-document consistency validation
- `build/scripts/tests/Validate-PlanningArtifacts.Tests.ps1` - 17 Pester tests
