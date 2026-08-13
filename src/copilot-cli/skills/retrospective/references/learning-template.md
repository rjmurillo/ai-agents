# Learning Extraction Template

The byte-exact retrospective artifact structure. Phases 0 through 4 were lifted verbatim
from the canonical source agent body at `.claude/agents/retrospective.md` (Phase 4,
"Learning Extraction Template", original lines 696-789). Phase 5 records the persistence
and closing outputs required by [SKILL.md](../SKILL.md), using the memory
protocol in `diagnosis-and-actions.md` and the closing activities in `frameworks.md`. The
output artifact MUST match this template, modulo filled placeholders. Do not reword the
headings or table columns; downstream readers and the auto-retro skeleton-fill path depend
on the exact shape.

Save to: `.agents/retrospective/YYYY-MM-DD-[scope].md`

````markdown
# Retrospective: [Scope]

## Session Info
- **Date**: YYYY-MM-DD
- **Agents**: [List]
- **Task Type**: [Feature | Bug | Research]
- **Outcome**: [Success | Partial | Failure]

## Phase 0: Data Gathering
[4-Step Debrief output]
[Execution Trace output]
[Outcome Classification output]

## Phase 1: Insights Generated
[Five Whys output if failure]
[Fishbone output if complex]
[Patterns and Shifts output]
[Learning Matrix output]

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| [Strategy] | [Outcome] | [1-10] | [%] |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| [Strategy] | [Type] | [Cause] | [Fix] | [%] |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| [Situation] | [Save] | [Takeaway] |

## Phase 3: Decisions

### Action Classification
[Keep/Drop/Add/Modify table]

### SMART Validation
[Validation for each new skill]

### Action Sequence
[Ordered actions with dependencies]

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: [Atomic - max 15 words]
- **Atomicity Score**: [%]
- **Evidence**: [Execution detail]
- **Skill Operation**: ADD | UPDATE | TAG | REMOVE
- **Target Skill ID**: [If UPDATE/TAG/REMOVE]

## Skillbook Updates

### ADD
```json
{
  "skill_id": "{domain}-{description}",
  "statement": "[Atomic]",
  "context": "[When to apply]",
  "evidence": "[Source]",
  "atomicity": [%]
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| [Learning] | [%] | [Memory name or none] | [Added / Updated / Deduplicated / Skipped / Failed] |

### +/Delta

#### + Keep
- [What worked well in this retrospective]

#### Delta Change
- [What should be different next time]

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| [Item from Delta] | [Missing Docs/Tool Gap/Process/Feature] | P0/P1/P2/P3 | Issue #N / Memory / Skip | [Link] |

#### Issues Created

| Issue | Title | Priority | Labels |
|-------|-------|----------|--------|
| #[N] | [Title] | P0/P1 | enhancement, source:retrospective |

#### Backlog Items Stored

| Item | Priority | Memory File |
|------|----------|-------------|
| [Item] | P2/P3 | backlog/retro-YYYY-MM-DD-items.md |

#### Skipped Items

| Item | Reason |
|------|--------|
| [Item] | [Duplicate of #X / Not actionable / Already addressed] |

### ROTI Assessment

**Score**: [0-4]

**Benefits Received**:
- [Benefit 1]
- [Benefit 2]

**Time Invested**: [Duration]

**Verdict**: [Continue | Modify | Stop]

### Helped, Hindered, Hypothesis

#### Helped
- [What made this retrospective effective]

#### Hindered
- [What got in the way]

#### Hypothesis
- [Experiment to try next retrospective]
````

<!-- vendor-portability: declared. This template names .agents/retrospective/YYYY-MM-DD-[scope].md as the save location. The path is a write target created on demand; it is not a read precondition. Issue #2050. -->
