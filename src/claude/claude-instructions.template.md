## AI Agent System

Multi-agent system for software development. Specialized agents handle different responsibilities with explicit handoff protocols.

### Invoking Agents

Use the Task tool with `subagent_type` parameter:

```python
Task(subagent_type="orchestrator", prompt="Help me implement feature X")
Task(subagent_type="analyst", prompt="Investigate why X fails")
Task(subagent_type="implementer", prompt="Implement feature X per plan")
```

### Workflow Paths

| Path | Agents | When |
|------|--------|------|
| Quick Fix | implementer → qa | One-sentence fix, single file |
| Standard | analyst → milestone-planner → implementer → qa | Investigation needed, 2-5 files |
| Strategic | independent-thinker → high-level-advisor → task-decomposer | WHETHER questions, scope/priority |

### Best Practices

1. **Start with orchestrator**: For complex tasks, let orchestrator route to appropriate agents
2. **Memory First**: Agents retrieve context before multi-step reasoning
3. **Clear Handoffs**: Agents announce next agent and purpose
4. **Commit Atomically**: Small, conventional commits

### Agent Output Directories

Agents save artifacts to `.agents/`:

| Directory | Purpose |
|-----------|---------|
| `analysis/` | Analyst findings, research |
| `architecture/` | ADRs |
| `planning/` | Plans and PRDs |
| `critique/` | Reviews |
| `qa/` | Test strategies |
| `sessions/` | Session context |

### Available Agents

See `.claude/agents/` for the full catalog. Each agent file contains its description, purpose, and when to use guidance in YAML frontmatter.
