---
name: Agent Prompts
applyTo: "src/claude/**/*.md,.github/copilot-instructions.md"
priority: 9
version: 1.0.0
status: active
---

# Agent Prompts Steering

## Scope

**Applies to**:

- `src/claude/**/*.md` - Agent prompt files
- `.github/copilot-instructions.md` - Copilot instructions

## Purpose

This steering file defines prompt engineering patterns for writing agent prompts.
All agent definitions in `src/claude/` follow these conventions.

## Prompt Structure

### YAML Front Matter

Every agent prompt file starts with YAML front matter containing four required fields.

```yaml
---
name: agent-name
description: One-sentence role summary starting with a noun phrase. Ends with usage guidance.
model: opus | sonnet | haiku
argument-hint: Describe what input the agent expects
---
```

| Field | Purpose | Example |
|-------|---------|---------|
| `name` | Agent identifier, lowercase, hyphenated | `milestone-planner` |
| `description` | Role summary for agent catalog display | `Technical authority on system design...` |
| `model` | LLM tier selection | `opus` for coordination, `sonnet` for execution, `haiku` for lightweight |
| `argument-hint` | Guides callers on what context to provide | `Specify the plan file path and task to implement` |

### Section Organization

Agent prompts follow a consistent section order. Not all sections are required for every agent.

| Section | Purpose | Required |
|---------|---------|----------|
| Core Identity | Bold role title and one-line mission | Yes |
| Activation Profile | Keywords and summon text for routing | Yes |
| Style Guide Compliance | Writing style rules | Yes |
| Claude Code Tools | Available tools and memory access | Yes |
| Core Mission | Expanded mission statement | Yes |
| Key Responsibilities | Numbered list of duties | Yes |
| Constraints | Explicit boundaries on agent scope | Yes |
| Memory Protocol | Retrieve-before-reason, store-at-milestones | Yes |
| Handoff Options | Table of downstream agents | Yes |
| Handoff Protocol | Return-to-orchestrator rules | Yes |
| Execution Mindset | Think/Act/Verify closing pattern | Yes |
| Output Location | Where artifacts are saved | Recommended |
| Impact Analysis Mode | Template for cross-domain analysis | When applicable |

### RFC 2119 Keyword Usage

Use RFC 2119 keywords (MUST, SHOULD, MAY) to signal obligation levels.

| Keyword | Meaning | Example |
|---------|---------|---------|
| MUST | Non-negotiable requirement | "You MUST retrieve memory before reasoning" |
| SHOULD | Expected unless justified deviation | "You SHOULD include coverage metrics" |
| MAY | Optional, at agent discretion | "You MAY include diagrams" |
| MUST NOT | Explicitly prohibited | "You MUST NOT modify planning artifacts" |

Use uppercase for emphasis. Use these keywords only when prescribing behavior.

## Agent Definition Patterns

### Core Identity

Start with a bold role title followed by a concise mission statement.

```markdown
## Core Identity

**Technical Authority** for system design coherence and architectural governance.
```

The identity section answers: "What is this agent, and what does it own?"

### Responsibilities

Use a numbered list. Each item starts with a bold verb.

```markdown
## Key Responsibilities

1. **Maintain** master architecture document
2. **Review** feature fit against existing modules
3. **Document** decisions with ADRs
```

### Constraints

Define explicit boundaries. State what the agent cannot do.

```markdown
## Constraints

- **Edit only** `.agents/architecture/` files
- **No code implementation**
- **No plan creation** (that is the Planner's role)
- Focus on governance, not execution
```

Constraints prevent scope creep and clarify handoff boundaries between agents.

### Activation Profile

Include keywords for routing and a summon paragraph for the orchestrator.

```markdown
## Activation Profile

**Keywords**: Design, Governance, ADR, Coherence, Patterns

**Summon**: I need a technical authority on system design...
```

The summon text is a first-person prompt the orchestrator uses to invoke the agent.
Write it as if the orchestrator is speaking to the agent directly.

### Style Guide Compliance

Every agent prompt includes a style section. The style rules are consistent across agents.

```markdown
## Style Guide Compliance

Key requirements:

- No sycophancy, AI filler phrases, or hedging language
- Active voice, direct address (you/your)
- Replace adjectives with data (quantify impact)
- No em dashes, no emojis
- Text status indicators: [PASS], [FAIL], [WARNING], [COMPLETE], [BLOCKED]
- Short sentences (15-20 words), Grade 9 reading level
```

Add agent-specific style requirements after the common block.

### Quality Gates

Use markdown checklists for validation steps. Group related checks.

```markdown
### Pre-PR Validation Gate (MANDATORY)

**Code Quality** (5 items):

- [ ] No TODO/FIXME/XXX placeholders remaining
- [ ] No hardcoded values
- [ ] No duplicate code introduced
- [ ] Cyclomatic complexity <=10, methods <=60 lines
- [ ] All tests pass locally
```

Label gates as MANDATORY or BLOCKING when they must pass before proceeding.

### Success Criteria

Use text status indicators for clear verdict signaling.

| Indicator | Meaning |
|-----------|---------|
| `[PASS]` | Requirement met |
| `[FAIL]` | Requirement not met, blocks progress |
| `[WARNING]` | Concern noted, does not block |
| `[COMPLETE]` | Task finished |
| `[BLOCKED]` | Cannot proceed without resolution |
| `[SKIP]` | Intentionally omitted with justification |

### Delegation and Handoff

#### Handoff Options Table

Define where work goes after this agent finishes.

```markdown
## Handoff Options

| Target | When | Purpose |
|--------|------|---------|
| **milestone-planner** | Architecture approved | Proceed with planning |
| **analyst** | More research needed | Investigate options |
| **implementer** | Design finalized | Begin implementation |
```

#### Handoff Protocol

State that subagents return to the orchestrator. They do not delegate further.

```markdown
## Handoff Protocol

**As a subagent, you CANNOT delegate**. Return results to orchestrator.

When work is complete:

1. Save artifacts to designated output directory
2. Store learnings in memory
3. Return to orchestrator: "Work complete. Recommend routing to [agent] for [next step]"
```

#### Handoff Validation Checklists

Include a checklist for each handoff scenario. This prevents incomplete handoffs.

```markdown
### Completion Handoff (to qa)

- [ ] All plan tasks implemented
- [ ] All tests pass
- [ ] Build succeeds
- [ ] Commits made with conventional message format
- [ ] Implementation notes documented
```

## Memory Protocol

### Retrieve Before Reasoning

Every agent retrieves relevant context before starting work.

```markdown
## Memory Protocol

**Before work (retrieve context):**

pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "[relevant topic]"
```

### Store at Milestones

After completing work, store learnings for future sessions.

```markdown
**After work (store learnings):**

mcp__serena__write_memory
memory_file_name: "[category]-[topic]"
content: "# [Topic]\n\n**Statement**: ...\n\n**Evidence**: ...\n\n## Details\n\n..."
```

### Fallback

Always include a fallback for when memory tools are unavailable.

```markdown
> **Fallback**: If Memory Router unavailable, read `.serena/memories/` directly with Read tool.
```

## Output Format Specifications

### Structured Deliverables

Agents produce artifacts at designated paths. Define the path pattern and template.

```markdown
## Output Location

`.agents/architecture/`

- `ADR-NNNN-[decision].md` - Architecture Decision Records
- `DESIGN-REVIEW-[topic].md` - Design review notes
```

### Execution Mindset

Close every agent prompt with a Think/Act pattern. This anchors agent behavior.

```markdown
## Execution Mindset

**Think:** "I guard the system's long-term health"

**Act:** Review against principles, not preferences

**Challenge:** Technical choices that compromise architecture

**Document:** Every decision with context and rationale
```

Use three to four verbs. Each verb maps to a core behavior.

## Anti-Patterns

### Ambiguous Instructions

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| "Handle errors appropriately" | No concrete guidance | Specify error categories and actions |
| "Write good tests" | Subjective quality | Define coverage targets and test types |
| "Follow best practices" | Vague reference | List specific practices by name |

### Missing Delegation Logic

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| No handoff table | Agent does not know where to route work | Add Handoff Options table |
| No constraints section | Agent scope creeps into other roles | Add explicit boundaries |
| Handoff without checklist | Incomplete work gets passed downstream | Add validation checklist per handoff |

### Unclear Success Criteria

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| "Verify it works" | No measurable outcome | Define pass/fail with metrics |
| Missing verdict format | Downstream agents cannot parse results | Use [PASS]/[FAIL] indicators |
| No blocking gates | Quality checks are optional | Label gates as MANDATORY or BLOCKING |

### Inconsistent Terminology

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Mixed terms for same concept | "task" vs "work item" vs "ticket" | Pick one term per concept |
| Different status labels | "done" vs "complete" vs "finished" | Use standard indicators: [COMPLETE] |
| Inconsistent agent names | "planner" vs "milestone-planner" | Use the exact `name` from front matter |

## Examples

### Well-Structured Front Matter

```yaml
---
name: qa
description: Quality assurance specialist who verifies implementations work correctly for real users. Designs test strategies, validates coverage against acceptance criteria, and reports results with evidence. Use when you need confidence through verification.
model: sonnet
argument-hint: Provide the implementation or feature to verify
---
```

### Effective Delegation Pattern (Orchestrator)

```markdown
## Sub-Agent Delegation

| Work Type | Route To | Example |
|-----------|----------|---------|
| Code changes | implementer | "Implement the fix" |
| Investigation | analyst | "Find root cause" |
| Design decisions | architect | "Review API design" |
| Test strategy | qa | "Create test plan" |
```

### Clear Handoff with Validation

```markdown
## Handoff Protocol

**As a subagent, you CANNOT delegate**. Return results to orchestrator.

When implementation is complete:

1. Ensure all commits are made with conventional messages
2. Store implementation notes in memory
3. Return to orchestrator: "Implementation complete. Recommend routing to qa for verification"

### Completion Handoff (to qa)

- [ ] All plan tasks implemented or deferred with rationale
- [ ] All tests pass (exit code 0)
- [ ] Build succeeds (exit code 0)
- [ ] Commits made with conventional message format
- [ ] Security flagging completed (YES/NO with justification)
```

### Impact Analysis Template Reference

Agents that support impact analysis include a standardized template.
The template captures direct impacts, affected areas, recommendations, and effort estimates.
See `src/claude/architect.md` and `src/claude/implementer.md` for full examples.
