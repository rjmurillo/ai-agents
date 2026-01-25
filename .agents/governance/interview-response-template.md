# Agent Interview Response Template

## Metadata

| Field | Value |
|-------|-------|
| Agent Name | [agent-name] |
| Interview Date | [YYYY-MM-DD] |
| Interviewer | [name/agent] |
| Agent Version | [version or commit] |
| Previous Interview | [date or "Initial"] |

---

## Question 1: Core Specialty

> What is your core specialty? (One sentence)

**Response**:

[One sentence describing the agent's primary focus]

---

## Question 2: Specific Tasks

> What specific tasks can you handle? (5-10 examples with descriptions)

| # | Task | Description | Typical Output |
|---|------|-------------|----------------|
| 1 | [Task name] | [What it involves] | [Deliverable type] |
| 2 | [Task name] | [What it involves] | [Deliverable type] |
| 3 | [Task name] | [What it involves] | [Deliverable type] |
| 4 | [Task name] | [What it involves] | [Deliverable type] |
| 5 | [Task name] | [What it involves] | [Deliverable type] |

---

## Question 3: Limitations

> What are your limitations? What you CANNOT do?

### Technical Limitations

- [Limitation 1]
- [Limitation 2]

### Scope Limitations

- [Limitation 1]
- [Limitation 2]

### Dependency Limitations

- [Requires X before I can Y]
- [Cannot proceed without Z]

### Output Limitations

- [Cannot produce X type of deliverable]
- [Not suited for Y format]

---

## Question 4: Agent Pairings

> Which agents work well with you?

| Agent | Relationship | When to Pair | Handoff Artifact |
|-------|--------------|--------------|------------------|
| [agent-name] | Before me | [Scenario] | [What they provide] |
| [agent-name] | After me | [Scenario] | [What I provide] |
| [agent-name] | Parallel | [Scenario] | [Shared context] |

---

## Question 5: Input Expectations

> What input format do you expect?

### Minimum Required Context

- [Required item 1]
- [Required item 2]
- [Required item 3]

### Preferred Format

[Prose / Structured / Checklist / Other]

### Optional but Helpful

- [Optional item 1]
- [Optional item 2]

### Example: Good Task Description

```text
[Example of a well-formed task for this agent]
```

### Example: Insufficient Task Description

```text
[Example of a poorly-formed task that would fail]
```

**Why insufficient**: [Explanation of what's missing]

---

## Question 6: Output Format

> What should I expect in your output?

### Primary Deliverable

| Aspect | Value |
|--------|-------|
| Type | [Report / Code / Recommendations / Plan / etc.] |
| Location | `.agents/[category]/[pattern].md` |
| Format | [Markdown / JSON / YAML / Code] |
| Naming | `[PREFIX]-NNN-[description].md` |

### Output Structure

```markdown
# [Template of typical output structure]

## Section 1
[What goes here]

## Section 2
[What goes here]
```

### Handoff Artifacts

| Artifact | Purpose | Consumer |
|----------|---------|----------|
| [Artifact name] | [Why produced] | [Who uses it] |

---

## Question 7: When to Use

> When should I use you? (Invocation rules, ideal scenarios)

### P0 - Always Use

| Scenario | Indicators | Confidence |
|----------|------------|------------|
| [Scenario] | [How to detect] | High |

### P1 - Strongly Recommended

| Scenario | Indicators | Confidence |
|----------|------------|------------|
| [Scenario] | [How to detect] | High/Medium |

### P2 - Consider Using

| Scenario | Indicators | Confidence |
|----------|------------|------------|
| [Scenario] | [How to detect] | Medium |

---

## Question 8: When NOT to Use

> When should I NOT use you? (Anti-patterns, inappropriate use)

### Use Different Agent Instead

| Scenario | Better Agent | Why |
|----------|--------------|-----|
| [Scenario] | [agent-name] | [Reason] |

### Prerequisites Not Met

| Missing Prerequisite | Required First |
|---------------------|----------------|
| [What's missing] | [What must happen] |

### Common Misuse Patterns

| Anti-Pattern | Why It Fails | Correct Approach |
|--------------|--------------|------------------|
| [Pattern] | [Reason] | [Alternative] |

---

## Validation Notes

### Verified Capabilities

- [ ] [Capability 1] - Tested on [date]
- [ ] [Capability 2] - Tested on [date]

### Known Issues

| Issue | Workaround | Status |
|-------|------------|--------|
| [Issue] | [Workaround] | Open/Resolved |

### Cross-Reference

- [ ] Pairings verified with partner agents
- [ ] Limitations tested in practice
- [ ] Capabilities matrix updated

