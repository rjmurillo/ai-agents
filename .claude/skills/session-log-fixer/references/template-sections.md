# Template Sections for Session Protocol Compliance

Copy these templates exactly when fixing session files. Do not recreate from memory.

---

## Session Start Table

```markdown
### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [x] | Tool output present |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [x] | Tool output present |
| MUST | Read `.agents/HANDOFF.md` | [x] | Content in context |
| MUST | Create this session log | [x] | This file exists |
| MUST | List skill scripts in `.claude/skills/github/scripts/` | [x] | Output documented below |
| MUST | Read usage-mandatory memory | [x] | Content in context |
| MUST | Read PROJECT-CONSTRAINTS.md | [x] | Content in context |
| MUST | Read memory-index, load task-relevant memories | [x] | List memories loaded |
| SHOULD | Verify git status | [x] | Output documented below |
| SHOULD | Note starting commit | [x] | SHA documented below |
```

---

## Session End Table

```markdown
### Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Complete session log (all sections filled) | [x] | File complete |
| MUST | Update Serena memory (cross-session context) | [x] | Memory write confirmed |
| MUST | Run markdown lint | [x] | Output below |
| MUST | Route to qa agent (feature implementation) | [x] | QA report: `.agents/qa/[report].md` |
| MUST | Commit all changes (including .serena/memories) | [x] | Commit SHA: abc1234 |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [x] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [x] | Tasks checked off |
| SHOULD | Invoke retrospective (significant sessions) | [x] | Doc: _______ |
| SHOULD | Verify clean git status | [x] | Output below |
```

---

## Evidence Column Values

Valid evidence values to use:

| Step Type | Valid Evidence |
|-----------|----------------|
| Tool call | "Tool output present" |
| File read | "Content in context" |
| File creation | "This file exists" |
| List operation | "Output documented below" |
| Memory read | "Content in context" or "Memory: [name]" |
| Commit | "Commit SHA: abc1234" (use actual SHA) |
| QA report | "QA report: `.agents/qa/[filename].md`" |
| Lint | "Lint output clean" or "Output below" |
| Not applicable | "N/A - [justification]" |

---

## Git State Section

```markdown
### Git State

- **Status**: clean
- **Branch**: feat/my-feature
- **Starting Commit**: abc1234
```

---

## Skill Inventory Section

```markdown
### Skill Inventory

Available GitHub skills:

- Add-CommentReaction.ps1
- Get-IssueContext.ps1
- Get-PRContext.ps1
- Get-PRReviewComments.ps1
- Get-PRReviewers.ps1
- Post-IssueComment.ps1
- Post-PRCommentReply.ps1
- Set-IssueLabels.ps1
- Set-IssueMilestone.ps1
```

---

## Full Protocol Compliance Section

Complete section for new session logs:

```markdown
## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [x] | Tool output present |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [x] | Tool output present |
| MUST | Read `.agents/HANDOFF.md` | [x] | Content in context |
| MUST | Create this session log | [x] | This file exists |
| MUST | List skill scripts in `.claude/skills/github/scripts/` | [x] | Output documented below |
| MUST | Read usage-mandatory memory | [x] | Content in context |
| MUST | Read PROJECT-CONSTRAINTS.md | [x] | Content in context |
| MUST | Read memory-index, load task-relevant memories | [x] | List memories loaded |
| SHOULD | Verify git status | [x] | Output documented below |
| SHOULD | Note starting commit | [x] | SHA documented below |

### Skill Inventory

Available GitHub skills:

- [List from directory scan]

### Git State

- **Status**: [clean/dirty]
- **Branch**: [branch name]
- **Starting Commit**: [SHA]

### Work Blocked Until

All MUST requirements above are marked complete.

---

### Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Complete session log (all sections filled) | [x] | File complete |
| MUST | Update Serena memory (cross-session context) | [x] | Memory write confirmed |
| MUST | Run markdown lint | [x] | Output below |
| MUST | Route to qa agent (feature implementation) | [x] | QA report: `.agents/qa/[report].md` |
| MUST | Commit all changes (including .serena/memories) | [x] | Commit SHA: _______ |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [x] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [x] | Tasks checked off |
| SHOULD | Invoke retrospective (significant sessions) | [x] | Doc: _______ |
| SHOULD | Verify clean git status | [x] | Output below |
```

---

## Source

Canonical source: `.agents/SESSION-PROTOCOL.md`
