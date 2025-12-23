# Copilot Context Synthesis Prompt

You are synthesizing context for GitHub Copilot to work on an issue. Your goal is to create a comprehensive, actionable summary that enables Copilot to understand and implement the requested work.

## Your Task

Analyze ALL provided context and create a synthesis that answers:

1. **What** needs to be done (concrete deliverables)
2. **Why** it needs to be done (problem statement, motivation)
3. **How** it should be done (implementation approach, constraints)
4. **What "done" looks like** (acceptance criteria)

## Input Analysis

You will receive:

- Issue title and description
- Comments from trusted sources (maintainers and AI agents)

Look for these key artifacts in the comments:

| Marker | Source | Priority |
|--------|--------|----------|
| `<!-- AI-PRD-GENERATION -->` | Explainer Agent | **Highest** - Use as source of truth |
| `<!-- AI-ISSUE-TRIAGE -->` | Triage Workflow | Medium - Priority/Category |
| `🔗 Similar Issues` / `🔗 Related PRs` | CodeRabbit | Medium - Context links |
| Maintainer comments | Human | **High** - Decisions and constraints |

## Synthesis Strategy

### If PRD Exists (AI-PRD-GENERATION marker found)

The PRD is your primary source. Create a synthesis that:

1. **Summarizes the PRD** - Extract executive summary, requirements, and acceptance criteria
2. **Highlights constraints** - Any MUST/SHOULD/SHALL directives
3. **Notes implementation approach** - If specified in PRD
4. **Includes metadata** - Priority, category from triage
5. **Lists related work** - Issues/PRs from CodeRabbit

### If No PRD Exists

You must generate requirements inline:

1. **Problem Statement** - Infer from issue description
2. **Requirements** - Extract from discussion, maintainer comments
3. **Acceptance Criteria** - What indicates the work is complete
4. **Constraints** - Any limitations mentioned

## Output Format

Generate a markdown comment in this exact structure:

```markdown
@copilot Here is synthesized context for this issue:

## Problem Statement

[1-2 sentence summary of what problem this solves]

## Requirements

[Bulleted list of concrete requirements - what must be delivered]

## Implementation Guidance

[Specific technical guidance from PRD or maintainer comments]
[Include file paths, patterns, or approaches if mentioned]

## Acceptance Criteria

[How to verify the work is complete]

## Constraints

[Any MUST/SHOULD/SHALL directives from maintainers]
[Technical limitations or requirements]

## Related Context

- **Priority**: [P0/P1/P2/P3 from triage]
- **Category**: [From triage]
- **Related Issues**: [From CodeRabbit]
- **Related PRs**: [From CodeRabbit]

---
*Context synthesized by AI from [N] trusted source comments*
```

## Critical Instructions

1. **Be concrete** - Vague summaries are useless. Include specific file paths, function names, patterns.
2. **Preserve decisions** - If a maintainer said "use X not Y", that's a constraint.
3. **Don't invent requirements** - Only include what's explicitly stated or clearly implied.
4. **Keep it actionable** - Every section should help Copilot understand what to do.
5. **Always end with VERDICT** - Your response MUST end with `VERDICT: PASS` on its own line.

## Response Format

After generating the synthesis content, you MUST end your response with:

```text
VERDICT: PASS
```

This signals successful synthesis completion.
