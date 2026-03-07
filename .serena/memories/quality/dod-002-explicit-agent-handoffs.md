# Dod: Explicit Agent Handoffs

## Skill-DoD-002: Explicit Agent Handoffs

**Statement**: When a plan identifies multiple agent types, create explicit handoff checkpoints to ensure all agents are invoked

**Context**: Multi-agent execution plans

**Evidence**: Plan said "(explainer)" for documentation but no handoff occurred during execution

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Pattern**:

```markdown
## Execution Handoffs

1. implementer → code complete
   - [ ] Handoff to: **qa** for verification
   
2. qa → tests pass
   - [ ] Handoff to: **explainer** for documentation
   
3. explainer → docs complete
   - [ ] Handoff to: **retrospective** for learning extraction
```

---