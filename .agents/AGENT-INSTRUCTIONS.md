# Agent Instructions for AI Agents Development

> **CRITICAL**: Read this entire document before starting ANY work.
> This document governs how agents execute development tasks in the ai-agents repository.

---

## Agent System Overview

This repository implements a coordinated multi-agent system for software development. See `AGENT-SYSTEM.md` for:

- Full agent catalog and capabilities
- Workflow patterns and routing heuristics
- Memory system and handoff protocols
- Conflict resolution and quality gates

**Quick Reference - Common Agents:**

| Agent | Use When |
|-------|----------|
| `orchestrator` | Complex multi-step tasks, routing decisions |
| `implementer` | Writing agent prompts, modifying files |
| `analyst` | Research and investigation |
| `architect` | Design decisions, ADRs, system structure |
| `planner` | Breaking down work into tasks |
| `critic` | Validating plans before implementation |
| `qa` | Test strategy and verification |
| `spec-generator` | Creating EARS requirements from vibe prompts |
| `independent-thinker` | Alternative perspectives, evaluation |
| `retrospective` | Session learnings, skill extraction |

---

## Quick Start Checklist

Before starting work, complete these steps IN ORDER:

- [ ] Read this file completely
- [ ] Read `.agents/AGENT-SYSTEM.md` for agent catalog
- [ ] Read `.agents/planning/enhancement-PROJECT-PLAN.md` for current project
- [ ] Check `.agents/HANDOFF.md` for previous session notes
- [ ] Identify your assigned phase and tasks
- [ ] Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.md`

---

## Document Hierarchy

| Document | Purpose | When to Update |
|----------|---------|----------------|
| `AGENT-INSTRUCTIONS.md` | How to execute work (this file) | Rarely - only if process changes |
| `AGENT-SYSTEM.md` | Agent catalog and workflows | When agents added/modified |
| `planning/enhancement-PROJECT-PLAN.md` | Master project plan | After task completion |
| `HANDOFF.md` | Session-to-session context | At END of every session |
| `sessions/*.md` | Detailed session logs | Throughout session |
| `governance/*.md` | Standards and protocols | When governance changes |
| `specs/*/*.md` | Requirements, designs, tasks | When specs created/updated |
| `steering/*.md` | Domain-specific guidance | When steering updated |

---

## Phase Execution Protocol

### 1. Session Initialization (MANDATORY)

```markdown
## Session Start Checklist
- [ ] Invoke serena initialization:
  ```text
  mcp__serena__activate_project  (with project path)
  mcp__serena__initial_instructions
  ```
- [ ] Created session log: `.agents/sessions/YYYY-MM-DD-session-NN.md`. Everything is referred to by "session-NN" from here on.
- [ ] Read HANDOFF.md from previous session
- [ ] Identified all tasks in assigned phase from enhancement-PROJECT-PLAN.md
- [ ] Verified git state is clean: `git status`
- [ ] Verified branch: `git branch --show-current`
- [ ] Noted starting commit: `git log --oneline -1`
- [ ] Read the commits since last session for context: `git log --oneline [last-session-commit]..HEAD`. If that cannot be determined, read the last 5 commits `git log --oneline -5`.
```

### 2. Task Execution (FOR EACH TASK)

**Before starting a task:**

1. Read the full task description in `enhancement-PROJECT-PLAN.md`
2. Understand acceptance criteria
3. Plan the implementation approach
4. **If task involves agent prompt changes**: Complete Impact Analysis (see below)

**During task execution:**

1. Work incrementally - small, atomic changes
2. Commit frequently with conventional commit messages
3. Run markdown linting after documentation changes
4. Validate agent prompts for consistency

**After completing a task:**

1. ✅ Check off the task in `enhancement-PROJECT-PLAN.md`
2. Update session log with:
   - What was done
   - Decisions made and why
   - Challenges encountered
   - How challenges were resolved
3. Commit the documentation update

### 3. Session Finalization (MANDATORY)

**Before ending ANY session, you MUST:**

```markdown
## Session End Checklist

- [ ] All assigned tasks checked off in enhancement-PROJECT-PLAN.md
- [ ] Session log complete with all details
- [ ] HANDOFF.md updated with:
  - [ ] What was completed
  - [ ] What's next
  - [ ] Any blockers or concerns
- [ ] Linting passes:
  - [ ] `npx markdownlint-cli2 --fix "**/*.md"` - Fix markdown issues
- [ ] All files committed (including .agents/ files)
- [ ] Retrospective agent invoked (for significant sessions or completing pr-comment-responder loop and fixes were made)
- [ ] Git status is clean (or intentionally dirty with explanation)
```

---

## Impact Analysis (Agent Prompt Changes)

**MANDATORY** when making changes to:

- Agent prompts in `src/claude/*.md`
- Orchestrator routing logic
- Agent workflow patterns
- Cross-agent dependencies

**Purpose:** Ensure changes don't break existing workflows or create inconsistencies.

### Analysis Steps

1. **Identify Affected Agents**

```bash
# Search for references to the agent being modified
grep -r "[agent-name]" src/claude/*.md
grep -r "[agent-name]" .agents/*.md
```

2. **Check Workflow Dependencies**

```bash
# Find workflows that include this agent
grep -r "→.*[agent-name]\|[agent-name].*→" .agents/
```

3. **Verify Routing Consistency**

- Check orchestrator.md routing table
- Verify agent is listed in AGENT-SYSTEM.md
- Confirm delegate relationships are bidirectional

4. **Create Impact Analysis Section**

```markdown
## Impact Analysis - [Agent/Feature Name]

### Affected Agents
- [ ] `orchestrator.md` - Update routing table
- [ ] `[other-agent].md` - Update delegate references

### Affected Documentation
- [ ] `AGENT-SYSTEM.md` - Update catalog entry
- [ ] `HANDOFF.md` - Note capability change

### Workflow Changes
- [ ] [Workflow name] - [Description of change]

### Verification Steps
- [ ] All affected agents reference correct delegates
- [ ] Routing table is complete
- [ ] No orphaned references
```

---

## Commit Message Format

Use conventional commits:

```text
<type>(<scope>): <short description>

<optional body with details>

<optional footer with references>
```

**Types:**

- `feat` - New feature or capability
- `fix` - Bug fix
- `docs` - Documentation only
- `chore` - Maintenance (CI, configs, etc.)
- `refactor` - Code/prompt restructuring
- `test` - Adding/fixing tests or validation

**Scopes for ai-agents:**

- `agents` - Agent prompt changes
- `orchestrator` - Orchestrator-specific changes
- `governance` - Governance document changes
- `specs` - Specification changes
- `steering` - Steering file changes
- `system` - AGENT-SYSTEM.md changes

**Examples:**

```text
feat(agents): add spec-generator agent

Implements Kiro's 3-tier spec hierarchy:
- EARS format requirements
- Design document generation
- Task breakdown

Refs: S-002
```

```text
docs(governance): add traceability validation rules

Document cross-reference requirements:
- TASK → DESIGN linking
- DESIGN → REQUIREMENT linking
- Orphan detection criteria

Refs: T-007
```

```text
fix(orchestrator): correct routing for spec requests

Routes "create spec" and "generate requirements" to spec-generator
instead of planner.

Refs: S-006
```

---

## Markdown Formatting Standards

**CRITICAL**: All markdown files must pass linting.

### Code Block Language Identifiers (MD040)

**ALWAYS** add a language identifier to code blocks:

```markdown
<!-- ❌ WRONG - triggers MD040 -->
```
some code
```

<!-- ✅ CORRECT -->
```text
some code
```
```

**Common language identifiers:**

| Content Type | Language ID |
|--------------|-------------|
| Shell commands | `bash` |
| PowerShell | `powershell` |
| JSON/YAML | `json` or `yaml` |
| Markdown templates | `markdown` |
| Plain text, diagrams | `text` |
| Workflow diagrams (→ arrows) | `text` |
| Agent invocation examples | `text` |

### Pre-commit Hook

The repository should have a pre-commit hook that:

1. Auto-fixes markdown with `markdownlint-cli2 --fix`
2. Re-stages corrected files automatically
3. Fails with instructions if issues can't be auto-fixed

---

## Session Log Template

Create at session start: `.agents/sessions/YYYY-MM-DD-session-NN.md`

```markdown
# Session NN - [Phase Name] - [Date]

## Session Info

- **Date**: YYYY-MM-DD
- **Phase**: [Phase number and name]
- **Branch**: `feat/phase-N-description`
- **Starting Commit**: [SHA]

## Pre-Flight Checks

- [ ] Read AGENT-INSTRUCTIONS.md
- [ ] Read AGENT-SYSTEM.md
- [ ] Read HANDOFF.md
- [ ] Identified tasks: [Task IDs]

## Tasks Completed

### [Task-ID] - [Task Name]

**Status**: ✅ Complete | 🔄 In Progress | ❌ Blocked

**What was done**:
- [Specific changes made]

**Decisions made**:
- [Decision]: [Rationale]

**Challenges**:
- [Challenge]: [Resolution]

**Files changed**:
- `path/to/file.md` - [description]

**Commits**:
- `abc1234` - [commit message]

---

## Session Summary

**Completed**: X/Y tasks
**Time spent**: ~X hours
**Next up**: [What the next session should do]

## Verification

```bash
# Verify markdown linting
npx markdownlint-cli2 "**/*.md"

# Verify no broken internal links
grep -r "](.*\.md)" .agents/ | grep -v node_modules | head -20

# Verify git state
git status
```

## Notes for Next Session

- [Important context]
- [Gotchas discovered]
- [Recommendations]
```

---

## HANDOFF.md Template

Update at session end:

```markdown
# Handoff Document

> **Last Updated**: YYYY-MM-DD by Claude (Session NN - [Phase Name])
> **Current Phase**: Phase N - [Phase Name]
> **Branch**: `feat/phase-N-description`

---

## Current State

**Git Status**: ✅ Clean | 🔄 Uncommitted changes
**Last Commit**: `abc1234` - [message]
**Markdown Lint**: ✅ Passing | ❌ Issues

**Project Context**:
- Repository: rjmurillo/ai-agents
- Purpose: Multi-agent orchestration system
- Enhancement Goal: Reconcile Kiro, Anthropic, and existing patterns

### Session Summary (Session NN - YYYY-MM-DD)

**Purpose**: [What this session accomplished]

**Work Completed**:
1. [Task-ID]: [What was done]
2. [Task-ID]: [What was done]

**Files Changed**:
- `[path]` - [What changed]

**Commits**:
- `[hash]` - [message]

---

## What's Next

The next session should:

1. [Specific first action]
2. [Specific second action]
3. [etc.]

## Blockers & Concerns

| Issue | Impact | Mitigation |
|-------|--------|------------|
| [Issue] | [Impact] | [What to do] |

## Quick Verification

```bash
# Verify state
git log --oneline -5
git status

# Verify markdown
npx markdownlint-cli2 "**/*.md"
```

---

## Session History

| Date | Phase | Tasks | Status |
|------|-------|-------|--------|
| YYYY-MM-DD | 0 | F-001, F-002 | ✅ Complete |
| YYYY-MM-DD | 1 | S-001 | 🔄 In Progress |

## Files to Review

If you need context, read these files in order:

1. `.agents/AGENT-INSTRUCTIONS.md` - Process instructions (this file)
2. `.agents/AGENT-SYSTEM.md` - Agent catalog and workflows
3. `.agents/planning/enhancement-PROJECT-PLAN.md` - Master project plan
4. `.agents/HANDOFF.md` - Previous session context
5. `.agents/sessions/YYYY-MM-DD-session-NN.md` - Last session details
```

---

## Recommended Agent Workflows

> **Note**: Use these workflows to maximize agent effectiveness and ensure quality.

### Full Feature Development (Recommended)

Use this workflow for any non-trivial feature:

```text
analyst → architect → planner → critic → implementer → qa → retrospective
```

| Step | Agent | Purpose | Output |
|------|-------|---------|--------|
| 1 | `analyst` | Research existing code, gather context | `.agents/analysis/` |
| 2 | `architect` | Design decision, create ADR if needed | `.agents/architecture/` |
| 3 | `planner` | Break down into tasks with criteria | `.agents/planning/` |
| 4 | `critic` | **Validate plan before implementation** | `.agents/critique/` |
| 5 | `implementer` | Implement changes following the plan | Source files |
| 6 | `qa` | Verify implementation, document tests | `.agents/qa/` |
| 7 | `retrospective` | Extract learnings, update skills | `.agents/retrospective/` |

### Spec Generation Workflow (Kiro Pattern)

For new features starting from vibe-level descriptions:

```text
spec-generator → critic → planner → task-generator
```

| Step | Agent | Purpose | Output |
|------|-------|---------|--------|
| 1 | `spec-generator` | Create EARS requirements, design, tasks | `.agents/specs/` |
| 2 | `critic` | Validate spec completeness and clarity | `.agents/critique/` |
| 3 | `planner` | Refine implementation approach | `.agents/planning/` |
| 4 | `task-generator` | Create atomic task breakdown | Updated specs |

### Quality Evaluation Workflow (Anthropic Pattern)

For quality-critical outputs:

```text
[generator] → independent-thinker → (accept or regenerate)
```

| Step | Agent | Purpose | Output |
|------|-------|---------|--------|
| 1 | [any] | Generate initial output | Artifact |
| 2 | `independent-thinker` | Evaluate against rubric | Score + feedback |
| 3 | [any] | Regenerate if score < 70% | Improved artifact |

**Loop termination:**
- Score >= 70%: Accept
- Score < 70% AND iterations < 3: Regenerate
- Iterations >= 3: Escalate to user

### Quick Fix Workflow

For small changes or simple updates:

```text
implementer → qa
```

### Strategic Decision Workflow

For major architectural or strategic decisions:

```text
analyst → independent-thinker → high-level-advisor → architect
```

### Plan Validation (Don't Skip!)

**IMPORTANT**: Always invoke the critic agent before implementation:

```text
@critic Validate plan at .agents/planning/[plan-file].md
```

The critic will:
- Identify gaps in the plan
- Challenge assumptions
- Suggest improvements
- Flag risks

### Post-Session Learning

After completing significant work:

```text
@retrospective Analyze this session for learnings.
Session log: .agents/sessions/YYYY-MM-DD-session-NN.md
Tasks completed: [list]
```

---

## Agent Invocation Reference

### Orchestrator Delegation

```text
@orchestrator [request description]

Context:
- Current phase: [N]
- Task: [Task-ID]
- Relevant files: [list]
```

### Specialized Agent Invocation

```text
# Research before implementation
@analyst Investigate [topic] and document findings in .agents/analysis/

# Design review before coding
@architect Review design for [feature], create ADR if needed

# Plan validation (REQUIRED before implementation)
@critic Validate plan at .agents/planning/[file].md

# Implementation
@implementer Implement [feature] per plan at .agents/planning/[file].md

# Test verification (REQUIRED after implementation)
@qa Verify [feature] and document test strategy

# Extract learnings (after significant work)
@retrospective Analyze session and extract learnings

# Generate specs from vibe prompt
@spec-generator Create specifications for: [vibe-level description]

# Alternative perspective
@independent-thinker Evaluate [output] against quality rubric
```

---

## Skill System

### Skill File Organization

Skills are organized in `.agents/skills/` by category:

```text
.agents/skills/
├── README.md           # Skill system overview
├── agent-skills.md     # Agent prompt patterns
├── workflow-skills.md  # Workflow optimization
├── quality-skills.md   # Quality assurance patterns
└── documentation-skills.md  # Documentation patterns
```

### Skill Format

```markdown
## Skill-[Category]-NNN

**Statement**: [Concise skill statement]
**Atomicity**: [0-100]% (how standalone is this skill)
**Category**: [Category name]
**Context**: [When to apply this skill]
**Evidence**: [Where this was discovered]
**Details**: [Additional context if needed]
```

### Skill Citation Protocol

When applying a skill, cite it explicitly:

```markdown
**Applying**: Skill-Agent-001
**Strategy**: Use structured output format
**Expected**: Consistent agent responses

[Execute action...]

**Result**: Agent produced expected format
**Skill Validated**: Yes
```

### Adding New Skills

After discovering a reusable pattern:

1. Identify the appropriate category file
2. Add skill using the format above
3. Assign next available ID in that category
4. Commit with message: `docs(skills): add Skill-[Category]-NNN`

---

## Traceability Rules

### Cross-Reference Requirements

1. Every TASK must link to at least one DESIGN
2. Every DESIGN must link to at least one REQUIREMENT
3. No orphaned requirements (REQ without DESIGN)
4. No orphaned designs (DESIGN without TASK)
5. Status consistency (completed TASK implies completed chain)

### YAML Front Matter Schema

**Requirements:**
```yaml
---
type: requirement
id: REQ-NNN
status: draft | review | approved | implemented
priority: P0 | P1 | P2
related:
  - DESIGN-NNN
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

**Designs:**
```yaml
---
type: design
id: DESIGN-NNN
status: draft | review | approved | implemented
requirements:
  - REQ-NNN
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

**Tasks:**
```yaml
---
type: task
id: TASK-NNN
status: pending | in-progress | complete | blocked
complexity: XS | S | M | L | XL
designs:
  - DESIGN-NNN
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### Validation

Run traceability validation before commits:

```bash
# When validation script is available (Phase 2)
./scripts/Validate-Traceability.ps1

# Manual verification
grep -r "related:" .agents/specs/ | wc -l
grep -r "requirements:" .agents/specs/ | wc -l
grep -r "designs:" .agents/specs/ | wc -l
```

---

## Steering System

### Steering File Structure

```text
.agents/steering/
├── README.md              # Steering system overview
├── csharp-patterns.md     # → **/*.cs
├── agent-prompts.md       # → src/claude/**/*.md
├── testing-approach.md    # → **/*.test.*, **/*.spec.*
├── security-practices.md  # → **/Auth/**, *.env*
└── documentation.md       # → **/*.md (non-agent)
```

### Steering Application

Before delegating to an agent:

1. Identify files that will be touched
2. Match files against steering glob patterns
3. Include applicable steering content in context
4. Note steering files used in session log

---

## Critical Reminders

### DO

- ✅ Read ALL instructions before starting
- ✅ Work incrementally with small commits
- ✅ Update documentation as you go
- ✅ Check off tasks immediately when complete
- ✅ Run markdown linting frequently
- ✅ Update HANDOFF.md before session ends
- ✅ **Invoke critic agent** before major implementations
- ✅ **Invoke qa agent** after implementations
- ✅ **Run retrospective agent** after significant sessions
- ✅ Follow traceability rules for specs
- ✅ Apply relevant steering context

### DON'T

- ❌ Skip the pre-flight checklist
- ❌ Make large commits with multiple unrelated changes
- ❌ Forget to update PROJECT-PLAN.md checkboxes
- ❌ Leave session without updating HANDOFF.md
- ❌ Assume the next session has context you didn't document
- ❌ Skip verification steps
- ❌ **Skip critic validation** - empty critique/ directory is a warning sign
- ❌ **Skip qa documentation** - empty qa/ directory is a warning sign
- ❌ Create orphaned specs without proper cross-references

---

## Emergency Recovery

If something goes wrong:

1. **Lost context**: Read session logs in `.agents/sessions/`
2. **Unclear what to do**: Re-read `enhancement-PROJECT-PLAN.md`
3. **Broken references**: Run traceability validation
4. **Linting fails**: Run `npx markdownlint-cli2 --fix "**/*.md"`
5. **Git issues**: Check last working commit with `git log --oneline`

---

## Lessons Learned

> **Note**: This section captures real issues discovered during development.
> Read these carefully to avoid repeating past mistakes.

### [Placeholder for Future Learnings]

As the project progresses, document lessons learned here following this format:

```markdown
### Session NN: [Issue Title] (YYYY-MM-DD)

**Issue**: [What went wrong]

**Root Cause**: [Why it happened]

**Prevention**:
1. [Step to avoid in future]
2. [Another preventive measure]

**Fix Applied**:
- [What was done to resolve]
```

---

## Document Control

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-17 | Initial agent instructions for ai-agents enhancement |
