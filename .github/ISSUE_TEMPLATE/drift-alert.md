---
name: Agent Drift Alert
about: Automated alert when Claude agents drift from VS Code/Copilot agents
title: "Agent Drift Detected - [DATE]"
labels: drift-detected, automated
assignees: ''
---

## Agent Drift Detected

**Detection Date**: <!-- Enter date -->
**Workflow Run**: <!-- Enter workflow URL -->

### Agents with Drift

<!-- List agents that have drifted -->

| Agent | Similarity | Drifting Sections |
|-------|------------|-------------------|
| <!-- agent name --> | <!-- X% --> | <!-- section names --> |

### Drift Details

<!-- For each agent with drift, include: -->

#### Agent Name

- **Overall similarity**: X%
- **Drifting sections**: <!-- sections below similarity threshold -->

**Section Details:**

- Section Name: X% similar

### What This Means

Claude agents (`src/claude/`) and VS Code/Copilot agents (`src/vs-code-agents/`) should have similar semantic content for core sections like Core Identity, Key Responsibilities, and Constraints.

When drift is detected, it means Claude agents have diverged from the shared template content.

### Recommended Actions

1. Review the differences listed above
2. Determine if drift is intentional or accidental
3. Either:
   - Update Claude agents to match VS Code/template content
   - Update shared templates to include Claude improvements (then regenerate)
   - Document the intentional difference in a comment

### Related Files

- Claude agents: `src/claude/`
- Shared templates: `templates/agents/`
- VS Code agents: `src/vs-code-agents/`
- Copilot CLI agents: `src/copilot-cli/`

### Commands

```powershell
# Run drift detection locally
pwsh build/scripts/Detect-AgentDrift.ps1

# See detailed JSON output
pwsh build/scripts/Detect-AgentDrift.ps1 -OutputFormat JSON

# Get markdown report
pwsh build/scripts/Detect-AgentDrift.ps1 -OutputFormat Markdown

# Adjust similarity threshold (default 80%)
pwsh build/scripts/Detect-AgentDrift.ps1 -SimilarityThreshold 90
```

### Resolution Checklist

- [ ] Identified root cause of drift
- [ ] Decided on resolution approach
- [ ] Made necessary updates
- [ ] Verified with `pwsh build/Detect-AgentDrift.ps1`
- [ ] Closed this issue
