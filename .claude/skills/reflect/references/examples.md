# Reflect Examples

Worked signal-to-learning examples. Load when categorizing a conversation signal.

## Examples

### Example 1: Correction Detected

```text
Conversation:
User: "Create a PR for this change"
Agent: [runs gh pr create directly]
User: "No, use the github skill script!"

Analysis:
[HIGH] + Add constraint: "Always use .claude/skills/github/ scripts for PR operations"
  Source: User correction - "No, use the github skill script!"
```

### Example 2: Success Pattern

```text
Conversation:
User: "Add error handling"
Agent: [adds try/catch with specific error types]
User: "Perfect! That's exactly what I wanted"

Analysis:
[MED] + Add preference: "Use specific error types in catch blocks, not generic [Exception]"
  Source: User approval after seeing specific error types
```

### Example 3: Edge Case Discovery

```text
Conversation:
User: "Run the build"
Agent: [runs build command]
User: "Wait, what if the node_modules folder doesn't exist?"

Analysis:
[MED] + Add edge case: "Check for node_modules existence before build"
  Source: User question about missing dependencies
```

