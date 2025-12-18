---
applyTo: "**/AGENTS.md,.github/copilot-instructions.md,src/claude/**/*.md"
---

# Agent Prompt Standards

For comprehensive agent prompt standards, see [.agents/steering/agent-prompts.md](../../.agents/steering/agent-prompts.md) and [.agents/AGENT-SYSTEM.md](../../.agents/AGENT-SYSTEM.md).

## Quick Reference

**Front Matter Template:**
```yaml
---
name: agent-name
description: One-line description of agent purpose
model: sonnet | opus | haiku
argument-hint: Example of how to invoke this agent
---
```

**Model Selection** (per ADR-002):
- **opus**: architect, high-level-advisor, implementer, independent-thinker, orchestrator, roadmap, security
- **sonnet**: analyst, critic, devops, explainer, memory, planner, pr-comment-responder, qa, retrospective, skillbook, task-generator  
- **haiku**: Reserved for high-volume/low-latency routing (not currently used)

**Structure Requirements:**
1. Front matter with YAML metadata
2. Core Identity section
3. Responsibilities list
4. Delegation Protocol
5. Output Format specification
6. Quality Gates

*This file serves as a Copilot-specific entry point. The authoritative steering content is maintained in `.agents/steering/agent-prompts.md` and `.agents/AGENT-SYSTEM.md`.*
