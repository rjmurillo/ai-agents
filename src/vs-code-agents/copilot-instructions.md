## AI Agent System

Multi-agent system for software development. Specialized agents handle different responsibilities with explicit handoff protocols.

### Invoking Agents

Use the `#runSubagent` command in Copilot Chat:

```text
#runSubagent with subagentType=orchestrator
Help me implement a new feature for user authentication

#runSubagent with subagentType=analyst
Investigate why the API is returning 500 errors

#runSubagent with subagentType=implementer
Implement the login form per the plan in .agents/planning/
```

### Workflow Paths

| Path | Agents | When |
|------|--------|------|
| Quick Fix | implementer → qa | One-sentence fix, single file |
| Standard | analyst → planner → implementer → qa | Investigation needed, 2-5 files |
| Strategic | independent-thinker → high-level-advisor → task-generator | WHETHER questions, scope/priority |

### Handoff Protocol

When handing off between agents:

1. **Announce**: "Completing [task]. Handing off to [agent] for [purpose]"
2. **Save Artifacts**: Store outputs in appropriate `.agents/` directory
3. **Route**: Use `#runSubagent with subagentType={agent_name}`

### Best Practices

1. **Memory First**: Retrieve context before multi-step reasoning
2. **Clear Handoffs**: Announce next agent and purpose
3. **Follow Plans**: The plan document is authoritative
4. **Commit Atomically**: Small, conventional commits

### Available Agents

See `.github/agents/` for the full catalog. Each agent file contains its description, purpose, and when to use guidance in YAML frontmatter.
