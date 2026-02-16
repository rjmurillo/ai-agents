# Process: Templatefirst Pattern

## Skill-Process-001: Template-First Pattern

**Statement**: Update shared templates before regenerating platform agents

**Context**: When updating agent capabilities across multiple platforms (copilot-cli, vs-code)

**Evidence**: Issue #44 Phase 4 - Commit e46bec1: 4 templates updated in templates/agents/*.shared.md, then Generate-Agents.ps1 regenerated 8 platform agents

**Impact**: Prevents drift, reduces manual work, ensures consistency

**Atomicity**: 95%

**Tags**: helpful, efficiency, consistency