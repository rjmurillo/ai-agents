## AI Agent System

Multi-agent system for software development. Specialized agents handle different responsibilities with explicit handoff protocols.

### Invoking Agents

Use the `/agent` command:

```text
/agent orchestrator
Help me implement a new feature for user authentication

/agent analyst
Investigate why the API is returning 500 errors

/agent implementer
Implement the login form per the plan in .agents/planning/
```

### Workflow Paths

| Path | Agents | When |
|------|--------|------|
| Quick Fix | implementer → qa | One-sentence fix, single file |
| Standard | analyst → milestone-planner → implementer → qa | Investigation needed, 2-5 files |
| Strategic | independent-thinker → high-level-advisor → task-decomposer | WHETHER questions, scope/priority |

### Handoff Protocol

When handing off between agents:

1. Announce: "Completing [task]. Handing off to [agent] for [purpose]"
2. Save artifacts: store outputs in the appropriate `.agents/` directory
3. Route: use `/agent [agent_name]`

### Best Practices

1. Memory first: retrieve context before multi-step reasoning
2. Clear handoffs: announce next agent and purpose
3. Follow plans: the plan document is authoritative
4. Commit atomically: small, conventional commits

### Available Agents

See `.github/agents/` for the full catalog. Each agent file contains its description, purpose, and when to use guidance in YAML frontmatter.

### Known Limitations

User-level (global) agent loading has a known issue. Use repository-level installation through each tool's native support instead:

- Copilot CLI: add the marketplace with `/plugin marketplace add rjmurillo/ai-agents`, then install `project-toolkit@ai-agents`
- VS Code / Visual Studio: open the repository so `.github/agents/` and `.github/copilot-instructions.md` load automatically
