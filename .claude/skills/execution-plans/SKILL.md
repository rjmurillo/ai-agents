---
name: execution-plans
version: 1.0.0
model: claude-sonnet-4-6
description: Manage execution plans as versioned artifacts with progress tracking and decision logs. Use when you say "create execution plan", "update plan progress", "log decision", "complete plan", or "abandon plan". Do NOT use to break work into milestones or delegate tasks (use planner).
license: MIT
---

# Execution Plans Skill

Treat execution plans as first-class artifacts, versioned in the repository.

<!-- vendor-portability: declared. This skill reads and writes plan artifacts under the consumer's .agents/plans/ (active/, completed/, abandoned/) and .agents/debt/tech-debt-registry.md, seeded from .agents/plans/TEMPLATE.md. These are consumer-side write targets created on demand; a vendored install without .agents/ creates the directories when the first plan is written rather than failing silently. Issue #2050. -->

## Directory Structure

```text
.agents/
├── plans/
│   ├── active/        # Plans currently in progress
│   ├── completed/     # Successfully finished plans
│   └── abandoned/     # Plans that were stopped (with rationale)
└── debt/
    └── tech-debt-registry.md  # Known technical debt items
```

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `create execution plan` | Create new plan in active/ |
| `update plan progress` | Add progress entry to existing plan |
| `log decision` | Add decision to plan's decision log |
| `complete plan` | Move plan to completed/ |
| `abandon plan` | Move plan to abandoned/ with rationale |

## Plan Template

Use `.agents/plans/TEMPLATE.md` as the starting point for new plans.

### Required Sections

| Section | Purpose |
|---------|---------|
| Metadata | Status, dates, owner, complexity |
| Objectives | Checkboxes for trackable goals |
| Decision Log | Table of decisions with rationale |
| Progress Log | Timestamped updates with agent attribution |
| Blockers | Current impediments |
| Related | Links to issues, PRs, ADRs |

## Process

### Creating a Plan

1. Copy TEMPLATE.md to `.agents/plans/active/{slug}.md`
2. Fill metadata (status: In Progress, created: today, owner: agent name)
3. Define objectives as checkboxes
4. Link to related issue/PR

### Updating Progress

1. Check off completed objectives
2. Add entry to Progress Log table with date, update, and agent name
3. Update blockers if any emerge

### Logging Decisions

Add row to Decision Log table:

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| YYYY-MM-DD | What was decided | Why this choice | What else was evaluated |

### Completing a Plan

1. Verify all objectives checked
2. Update status to Completed
3. Move file from `active/` to `completed/`
4. Add final progress entry

### Blocking a Plan

1. Update status to Blocked
2. Document impediment in Blockers section
3. Add progress entry noting the block

### Abandoning a Plan

1. Update status to Abandoned
2. Document rationale in blockers or final progress entry
3. Move file from `active/` to `abandoned/`

## Integration

- Session logs reference active plans when relevant
- Planner skill creates plans here when executing complex work
- Retrospectives link back to completed plans

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Plans without objectives | Not trackable | Define measurable checkboxes |
| Undocumented decisions | Lost institutional knowledge | Log every non-trivial choice |
| Stale active plans | Clutters workspace | Complete or abandon promptly |
| Plans without issue links | No traceability | Always link to source issue |

## Verification

After creating a plan:

- [ ] File in `.agents/plans/active/`
- [ ] Metadata section complete
- [ ] At least one objective defined
- [ ] Linked to issue or PR

After completing:

- [ ] All objectives checked
- [ ] Final progress entry added
- [ ] File moved to `completed/`
