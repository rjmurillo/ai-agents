# Skill: Agent Generation Workflow

**Skill ID**: Skill-AgentWorkflow-001
**Category**: Infrastructure
**Discovered**: 2025-12-16
**Source**: PR #49 - Phase 2 CodeRabbit Remediation

## Skill Statement

When modifying agent behavior in this repository, always update the shared templates in `templates/agents/*.shared.md` FIRST, then run `pwsh build/Generate-Agents.ps1` to regenerate platform-specific agents.

## Pattern

```
1. Edit templates/agents/[agent].shared.md
2. Run: pwsh build/Generate-Agents.ps1
3. Verify: Check src/copilot-cli/, src/vs-code-agents/
4. If needed: Manually update src/claude/ (separate platform)
5. Commit all changes together
```

## Evidence

Phase 2 changes were initially made only to `src/claude/` files. This caused drift between the manually-edited Claude agents and the generated agents (copilot-cli, vs-code-agents). Rework was required to sync templates and regenerate.

## Related Skills

- **Skill-AgentWorkflow-002**: `src/claude/` is a separate platform with additional content (Claude Code Tools section) not in shared templates
- **Skill-AgentWorkflow-003**: Always verify agent changes appear in all three platform directories after generation

## Validation Commands

```bash
# Check for drift before making changes
pwsh build/Generate-Agents.ps1 -Validate

# Regenerate all agents
pwsh build/Generate-Agents.ps1

# Preview what would be generated
pwsh build/Generate-Agents.ps1 -WhatIf
```

## Anti-Pattern

❌ **Do NOT** edit `src/copilot-cli/` or `src/vs-code-agents/` directly - these are generated files

❌ **Do NOT** assume `src/claude/` will be updated by the generator - it's manually maintained

## Correct Pattern

✅ Edit `templates/agents/*.shared.md`  
✅ Run `Generate-Agents.ps1`  
✅ Update `src/claude/` manually if needed  
✅ Commit all changes together  
