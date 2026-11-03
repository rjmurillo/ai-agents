# Research templates

The three document skeletons the research skill fills in, plus the Phase 3
assessment areas. Held here rather than in `SKILL.md` so the skill body stays
readable at a glance and the templates stay editable without re-reading the
whole workflow.

## Phase 2: analysis document

Organize each document for its topic, not for the template. If a topic has no
historical context, do not force the section.

```markdown
# {Topic Name}: Analysis

**Date**: YYYY-MM-DD | **Context**: {CONTEXT} | **Sources**: [URLs]

## Executive Summary
[2 to 3 paragraphs: essence, why it matters, key takeaways]

## Core Concepts
[Definitions, principles, foundations]

## Frameworks
[Decision frameworks, models, process patterns, if applicable]

## Applications
### Example 1: [Scenario]
**Context**: [situation] **Application**: [how applied] **Outcome**: [result] **Lesson**: [takeaway]
### Example 2, 3: [same structure]

## Failure Modes
### Anti-Pattern 1: [Name]
**Description**: [what it looks like] **Why It Fails**: [root cause] **Correction**: [proper approach]
### Anti-Pattern 2, 3: [same structure]

## Relationships
### Connection to [Concept A]
[How they relate, complement, or contrast]

## Applicability to this project
[Integration points, proposed applications, priority assessment]

## References
[Sources with URLs]
```

## Phase 3: applicability assessment

Work these five areas, then record the result in the analysis document:

1. **Agents**: which agents benefit, and does this change their prompts or responsibilities?
2. **Protocols**: does this improve session protocols, handoffs, or quality gates?
3. **Memory**: does this change how knowledge is stored or retrieved?
4. **Governance**: should this become a constraint, or inform ADR review?
5. **Skills and automation**: could this be encoded in a skill or a script?

```markdown
## Applicability to this project

### Integration Points
[Named agents, protocols, memory usage, skill opportunities]

### Proposed Applications
1. **[Application]**
- **What**: [specific change] **Where**: [files or agents affected]
- **Why**: [benefit] **Effort**: [trivial/small/medium/large]

### Priority Assessment
**High**: [aligns with current objectives] **Medium**: [valuable, not urgent] **Low**: [nice to have]
```

Applications must be concrete: file paths and agent names, not generic
possibilities. Justify priority against project goals rather than opinion.

## Phase 5: issue body

Write this with the `Write` tool to `{analysis-dir}/{topic-slug}-issue-body.md`,
never through a shell heredoc, then pass it by path so the multi-line body stays
out of shell quoting.

```markdown
## Context
Research completed: {analysis-dir}/{topic-slug}.md

## Proposal
[What to implement]

## Integration Points
[Specific files, agents, protocols]

## References
- Analysis: {analysis-dir}/{topic-slug}.md
- Serena memory: {topic-slug}-integration

## Tasks
- [ ] [Task 1]

## Acceptance Criteria
- [ ] [Criterion 1]
```
