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
| Standard | analyst → planner → implementer → qa | Investigation needed, 2-5 files |
| Strategic | independent-thinker → high-level-advisor → task-generator | WHETHER questions, scope/priority |

### Handoff Protocol

When handing off between agents:

1. **Announce**: "Completing [task]. Handing off to [agent] for [purpose]"
2. **Save Artifacts**: Store outputs in appropriate `.agents/` directory
3. **Route**: Use `/agent [agent_name]`

### Best Practices

1. **Memory First**: Retrieve context before multi-step reasoning
2. **Clear Handoffs**: Announce next agent and purpose
3. **Follow Plans**: The plan document is authoritative
4. **Commit Atomically**: Small, conventional commits

### Available Agents

See `.github/agents/` for the full catalog. Each agent file contains its description, purpose, and when to use guidance in YAML frontmatter.

### Known Limitations

**Note**: User-level (global) agent loading has a known issue. For best results, install agents at the repository level using skill-installer:

```bash
# One-liner (no install required)
uvx --from git+https://github.com/rjmurillo/skill-installer skill-installer interactive

# Or install globally
uv tool install git+https://github.com/rjmurillo/skill-installer
skill-installer interactive
```
