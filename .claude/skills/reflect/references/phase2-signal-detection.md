# Phase 2: Analyze the Conversation (Detailed)

Scan the conversation for learning signals with confidence levels. SKILL.md
Process step 2 points here for the full detection patterns and the confidence
threshold table.


Scan the conversation for learning signals with confidence levels:

#### HIGH Confidence: Corrections

User actively steered or corrected output. These are the most valuable signals.

**Detection patterns**:

- Explicit rejection: "no", "not like that", "that's wrong", "I meant"
- Strong directives: "never do", "always do", "don't ever"
- Immediate requests for changes after generation
- User provided alternative implementation
- User explicitly corrected output format/structure

**Example**:

```text
User: "No, use the PowerShell skill script instead of raw gh commands"
→ [HIGH] + Add constraint: "Use PowerShell skill scripts, never raw gh commands"
```

#### MEDIUM Confidence: Success Patterns

Output was accepted or praised. Good signals but may be context-specific.

**Detection patterns**:

- Explicit praise: "perfect", "great", "yes", "exactly", "that's it"
- Implicit acceptance: User built on top of output without modification
- User proceeded to next step without corrections
- Output was committed/merged without changes

**Example**:

```text
User: "Perfect, that's exactly what I needed"
→ [MED] + Add preference: "Include example usage in script headers"
```

#### MEDIUM Confidence: Edge Cases

Scenarios the skill didn't anticipate. Opportunities for improvement.

**Detection patterns**:

- Questions skill didn't answer
- Workarounds user had to apply
- Features user asked for that weren't covered
- Error handling gaps discovered

**Example**:

```text
User: "What if the file doesn't exist?"
→ [MED] ~ Add edge case: "Handle missing file scenario"
```

#### LOW Confidence: Preferences

Accumulated patterns over time. Need more evidence before formalizing.

**Detection patterns**:

- Repeated choices in similar situations
- Style preferences shown implicitly (formatting, naming)
- Tool/framework preferences
- Workflow preferences

**Example**:

```text
User consistently uses `-Force` flag
→ [LOW] ~ Note for review: "User prefers -Force flag for overwrites"
```

#### Confidence Threshold

Only propose changes when sufficient evidence exists:

| Threshold | Action |
|-----------|--------|
| ≥1 HIGH signal | Always propose (user explicitly corrected) |
| ≥2 MED signals | Propose (sufficient pattern) |
| ≥3 LOW signals | Propose (accumulated evidence) |
| 1-2 LOW only | Skip (insufficient evidence), note for next session |
