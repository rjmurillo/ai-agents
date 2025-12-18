applyTo: "src/claude/**/*.md,.github/copilot-instructions.md"

# Agent Prompt Standards

Guidelines for writing consistent, effective agent prompts.

## Structure

All agent prompts must include:

1. **Front matter**: YAML metadata (name, description, model, argument-hint)
2. **Core Identity**: Role and primary purpose
3. **Responsibilities**: Numbered list of key tasks
4. **Delegation Protocol**: How to hand off to other agents
5. **Output Format**: Expected artifact structure
6. **Quality Gates**: Validation criteria

## Best Practices

- **Clear scope**: Define what agent does and doesn't do
- **Explicit handoffs**: Specify when to delegate to other agents
- **Memory integration**: Use cloudmcp-manager for context
- **Consistent terminology**: Use standard terms from AGENT-SYSTEM.md
- **Examples**: Include concrete examples of outputs

## Front Matter Template

```yaml
---
name: agent-name
description: One-line description of agent purpose
model: sonnet | opus
argument-hint: Example of how to invoke this agent
---
```

## Anti-Patterns to Avoid

- ❌ Ambiguous delegation instructions
- ❌ Missing success criteria
- ❌ Inconsistent artifact naming
- ❌ Unclear output expectations

*Note: Full steering content to be implemented in Phase 4. See `.agents/steering/agent-prompts.md` for placeholder.*
