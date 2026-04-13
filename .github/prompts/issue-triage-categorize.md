# Issue Categorization Task

You are categorizing a GitHub issue to help with triage and prioritization.

## Available Labels

### Type Labels (choose one)

- `bug` - Something isn't working as expected
- `enhancement` - New feature or improvement request
- `documentation` - Documentation only changes
- `question` - Request for information or clarification
- `discussion` - Open-ended topic for discussion

### Agent Labels (choose if applicable)

Apply when the issue relates to a specific agent:

- `agent-orchestrator` - Task coordination agent
- `agent-analyst` - Research and investigation agent
- `agent-architect` - Design and ADR agent
- `agent-implementer` - Code implementation agent
- `agent-milestone-planner` - Milestone and work package agent
- `agent-critic` - Plan validation agent
- `agent-qa` - Testing and verification agent
- `agent-security` - Security assessment agent
- `agent-devops` - CI/CD pipeline agent
- `agent-roadmap` - Product vision agent
- `agent-explainer` - Documentation agent
- `agent-memory` - Context persistence agent
- `agent-retrospective` - Learning extraction agent

### Area Labels (choose if applicable)

- `area-workflows` - GitHub Actions workflows
- `area-prompts` - Agent prompts and templates
- `area-installation` - Installation scripts
- `area-infrastructure` - Build, CI/CD, configuration

## Output Format

Respond with ONLY valid JSON (no markdown, no explanation):

```json
{
  "labels": ["bug", "agent-security"],
  "category": "bug",
  "confidence": 0.85,
  "reasoning": "Issue describes a security vulnerability in the security agent"
}
```

## Rules

1. Always include exactly ONE type label
2. Include agent labels only if clearly relevant
3. Include area labels if the issue mentions specific areas
4. Set confidence between 0.0 and 1.0
5. Keep reasoning brief (one sentence)
