# Decision Tree, Examples, Use Cases, Anti-Patterns (Detailed)

SKILL.md points here for the full decision tree, worked examples, per-domain
use cases, and anti-patterns.

## Decision Tree

```text
User says "reflect" or similar?
│
├─► YES
│   │
│   ├─► Identify skill(s) used in conversation
│   │   │
│   │   └─► Skill identified?
│   │       │
│   │       ├─► YES → Analyze conversation for signals
│   │       │   │
│   │       │   └─► Meets confidence threshold?
│   │       │       │
│   │       │       ├─► YES → Present findings, await approval
│   │       │       │   │
│   │       │       │   ├─► User says Y → Update memory file
│   │       │       │   │   │
│   │       │       │   │   ├─► Serena available? → Use MCP write
│   │       │       │   │   └─► Serena unavailable? → Use Git fallback
│   │       │       │   │
│   │       │       │   ├─► User says n → Ask for feedback
│   │       │       │   │   │
│   │       │       │   │   ├─► User wants revision → Re-analyze
│   │       │       │   │   └─► User skips → End workflow
│   │       │       │   │
│   │       │       │   └─► User says edit → Interactive review
│   │       │       │       │
│   │       │       │       └─► Per-finding [keep/modify/remove]
│   │       │       │
│   │       │       └─► NO → Report "Insufficient evidence. Note for next session."
│   │       │
│   │       └─► NO → Ask user which skill to reflect on
│   │           │
│   │           ├─► User specifies skill → Continue with that skill
│   │           └─► User says "none" → End workflow
│   │
│   └─► Multiple skills?
│       │
│       └─► Analyze each, group findings by skill, present together
│
└─► NO → This skill not invoked
```

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

## Use Cases

### 1. Code Review Skills

Capture learnings about code review patterns:

- **Style guide rules**: User corrections on formatting, naming, structure
- **Security patterns**: Security vulnerabilities caught, OWASP patterns enforced
- **Severity levels**: When issues are P0 vs P1 vs P2
- **False positives**: Patterns that look like issues but aren't

**Example memory**: `.serena/memories/code-review-observations.md`

### 2. API Design Skills

Track API design decisions:

- **Naming conventions**: REST endpoint patterns, verb choices
- **Error formats**: HTTP status codes, error response structure
- **Auth patterns**: OAuth, JWT, API key patterns
- **Versioning style**: URL versioning, header versioning

**Example memory**: `.serena/memories/api-design-observations.md`

### 3. Testing Skills

Remember testing preferences:

- **Coverage targets**: Minimum % required, critical paths
- **Mocking patterns**: When to mock vs integration test
- **Assertion styles**: Preferred assertion libraries, patterns
- **Test naming**: Convention for test method names

**Example memory**: `.serena/memories/testing-observations.md`

### 4. Documentation Skills

Learn documentation patterns:

- **Structure/format**: Section order, heading levels
- **Code examples**: Real vs pseudo-code, language choice
- **Tone preferences**: Formal vs casual, active vs passive voice
- **Diagram styles**: Mermaid vs ASCII, detail level

**Example memory**: `.serena/memories/documentation-observations.md`

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Applying without showing | User loses visibility | Always preview changes |
| Overwriting existing learnings | Loses history | Append with timestamps |
| Generic observations | Not actionable | Be specific and contextual |
| Ignoring LOW confidence | Lose valuable patterns | Track for future validation |
| Creating memory for one-off | Noise | Wait for repeated patterns |
