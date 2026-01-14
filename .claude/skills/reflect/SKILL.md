---
name: reflect
description: Analyze conversations for skill learnings and propose memory improvements. Use when user says "reflect", "improve skill", "learn from this", or at session end after skill-heavy work. Acts as mini-retrospective for skill-based memories.
license: MIT
model: claude-sonnet-4-5
metadata:
  version: 1.0.0
  timelessness: 8/10
  adr: ADR-007
---

# Reflect Skill

Analyze the current conversation and propose improvements to skill-based memories based on what worked, what didn't, and edge cases discovered.

---

## Triggers

| Phrase | Action |
|--------|--------|
| "reflect" | Full analysis of current session |
| "improve skill" | Target specific skill for improvement |
| "learn from this" | Extract learnings from recent interaction |
| "what did we learn" | Summarize accumulated learnings |
| At session end | Proactive offer if skill was heavily used |

---

## Workflow

### Step 1: Identify the Skill

Locate the skill-based memory to update:

1. **Check Serena memories**: Look for files prefixed with `skill-` in `.serena/memories/`
2. **Infer from context**: Identify which skill(s) were used in the conversation
3. **Create if needed**: If no skill memory exists, propose creating `skill-{name}.md`

**Storage Locations**:

- Primary: `.serena/memories/skill-{skill-name}.md`
- Fallback (if Serena unavailable): Git at `.serena/memories/skill-{skill-name}.md`

### Step 2: Analyze the Conversation

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

### Step 3: Propose Changes

Present findings using WCAG AA accessible colors (4.5:1 contrast ratio):

```text
┌─────────────────────────────────────────────────────────────┐
│ SKILL REFLECTION: {skill-name}                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [HIGH] + Add constraint: "{specific constraint}"            │
│   Source: "{quoted user correction}"                        │
│                                                             │
│ [MED]  + Add preference: "{specific preference}"            │
│   Source: "{evidence from conversation}"                    │
│                                                             │
│ [MED]  + Add edge case: "{scenario}"                        │
│   Source: "{question or workaround}"                        │
│                                                             │
│ [LOW]  ~ Note for review: "{observation}"                   │
│   Source: "{pattern observed}"                              │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Apply changes? [Y/n/edit]                                   │
└─────────────────────────────────────────────────────────────┘
```

**Color Key** (accessible):

- `[HIGH]` - Red/bold: Mandatory corrections (user explicitly said "no")
- `[MED]` - Yellow/amber: Recommended additions
- `[LOW]` - Blue/dim: Notes for later review

**User Response Handling**:

| Response | Action |
|----------|--------|
| **Y** (yes) | Proceed to Step 4 (update memory) |
| **n** (no) | Abort update, ask "What would you like to change or was this not useful?" |
| **edit** | Present each finding individually, allow user to modify/reject each one |

**On rejection (n)**:

1. Log that reflection was declined (for future pattern analysis)
2. Ask user if they want to revise the analysis or skip entirely
3. If skip, end workflow without memory update

**On edit**:

1. Present first finding with options: [keep/modify/remove]
2. If modify, accept user's revised text
3. Repeat for each finding
4. Confirm final list before applying

### Step 4: Add or Update Memory

**ALWAYS show changes before applying.**

After user approval:

1. **Read existing memory** (if exists)
2. **Append new learnings** with timestamp and session reference
3. **Preserve existing content** - never remove without explicit request
4. **Write to file**: `.serena/memories/skill-{skill-name}.md`

**Storage Strategy**:

1. **Attempt Serena MCP** (primary):

   ```text
   mcp__serena__write_memory(memory_file_name="skill-{name}", memory_content="...")
   ```

2. **If Serena unavailable** (fallback to Git):

   ```powershell
   # Read existing (if any)
   $existingContent = Get-Content ".serena/memories/skill-{name}.md" -ErrorAction SilentlyContinue

   # Append new learnings
   $newContent = $existingContent + "`n" + $newLearnings

   # Write file
   Set-Content ".serena/memories/skill-{name}.md" -Value $newContent

   # Commit
   git add ".serena/memories/skill-{name}.md"
   git commit -m "chore(memory): update skill-{name} learnings"
   ```

**Memory Format**:

```markdown
# Skill Memory: {Skill Name}

**Last Updated**: {ISO date}
**Sessions Analyzed**: {count}

## Constraints (HIGH confidence)

- {constraint 1} (Session {N}, {date})
- {constraint 2} (Session {N}, {date})

## Preferences (MED confidence)

- {preference 1} (Session {N}, {date})
- {preference 2} (Session {N}, {date})

## Edge Cases (MED confidence)

- {edge case 1} (Session {N}, {date})
- {edge case 2} (Session {N}, {date})

## Notes for Review (LOW confidence)

- {note 1} (Session {N}, {date})
- {note 2} (Session {N}, {date})
```

---

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

---

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

---

## Use Cases

### 1. Code Review Skills

Capture learnings about code review patterns:

- **Style guide rules**: User corrections on formatting, naming, structure
- **Security patterns**: Security vulnerabilities caught, OWASP patterns enforced
- **Severity levels**: When issues are P0 vs P1 vs P2
- **False positives**: Patterns that look like issues but aren't

**Example memory**: `.serena/memories/skill-code-review.md`

### 2. API Design Skills

Track API design decisions:

- **Naming conventions**: REST endpoint patterns, verb choices
- **Error formats**: HTTP status codes, error response structure
- **Auth patterns**: OAuth, JWT, API key patterns
- **Versioning style**: URL versioning, header versioning

**Example memory**: `.serena/memories/skill-api-design.md`

### 3. Testing Skills

Remember testing preferences:

- **Coverage targets**: Minimum % required, critical paths
- **Mocking patterns**: When to mock vs integration test
- **Assertion styles**: Preferred assertion libraries, patterns
- **Test naming**: Convention for test method names

**Example memory**: `.serena/memories/skill-testing.md`

### 4. Documentation Skills

Learn documentation patterns:

- **Structure/format**: Section order, heading levels
- **Code examples**: Real vs pseudo-code, language choice
- **Tone preferences**: Formal vs casual, active vs passive voice
- **Diagram styles**: Mermaid vs ASCII, detail level

**Example memory**: `.serena/memories/skill-documentation.md`

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Applying without showing | User loses visibility | Always preview changes |
| Overwriting existing learnings | Loses history | Append with timestamps |
| Generic observations | Not actionable | Be specific and contextual |
| Ignoring LOW confidence | Lose valuable patterns | Track for future validation |
| Creating memory for one-off | Noise | Wait for repeated patterns |

---

## Integration

### With Session Protocol

Run reflection at session end as part of retrospective:

```text
## Session End Checklist
- [ ] Complete session log
- [ ] Run skill reflection (if skills were used)
- [ ] Update Serena memory
- [ ] Commit changes
```

### With Memory Skill

Skill memories integrate with the memory system:

```powershell
# Search skill memories
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "skill-github constraints"

# Read specific skill memory
Read .serena/memories/skill-github.md
```

### With Serena

If Serena MCP is available:

```text
mcp__serena__read_memory(memory_file_name="skill-github")
mcp__serena__write_memory(memory_file_name="skill-github", memory_content="...")
```

---

## Verification

| Action | Verification |
|--------|--------------|
| Analysis complete | Signals categorized by confidence |
| User approved | Explicit Y or approval statement |
| Memory updated | File written to `.serena/memories/` |
| Changes preserved | Existing content not lost |
| Commit ready | Changes staged, message drafted |

---

## Design Decisions

### Naming Convention: `skill-{name}.md`

**Decision**: Use `skill-` prefix for skill-based memories (e.g., `skill-github.md`).

**Rationale**:

- Explicit prefix makes skill memories instantly discoverable
- Separates skill learnings from factual/episodic memories
- User-specified requirement per original design

**Alternative Considered**: Agent sidecar pattern (`{name}-skill-sidecar-learnings.md`)

- More aligned with ADR-007 tiered index
- Rejected: User explicitly requested `skill-` prefix for clarity

**Migration Path**: If the project later adopts sidecar pattern, rename with:

```powershell
Get-ChildItem ".serena/memories/skill-*.md" | ForEach-Object {
    $newName = $_.Name -replace '^skill-(.+)\.md$', '$1-skill-sidecar-learnings.md'
    Rename-Item $_.FullName $newName
}
```

---

## Related

| Skill | Relationship |
|-------|--------------|
| `memory` | Skill memories are part of Tier 1 |
| `using-forgetful-memory` | Alternative storage for skill learnings |
| `curating-memories` | For maintaining/pruning skill memories |
| `retrospective` | Full session retrospective (this is mini version) |

---

## Commit Convention

When committing skill memory updates:

```text
chore(memory): update skill-{name} learnings from session {N}

- Added {count} constraints (HIGH confidence)
- Added {count} preferences (MED confidence)
- Added {count} edge cases (MED confidence)
- Added {count} notes (LOW confidence)

Session: {session-id}
```
