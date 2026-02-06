# Velocity Opportunity Analysis

You are analyzing a velocity opportunity detected from repository activity.
Evaluate the opportunity and suggest concrete next actions.

## Context

You will receive a JSON object describing a detected opportunity from one of:

- **PR Merge**: TODO/FIXME patterns found in merged code
- **Issue Triage**: Newly opened issue needing complexity scoring
- **Artifact Change**: Agent artifacts (ADRs, plans, skills) were updated

## Output Format

Respond with ONLY valid JSON (no markdown, no explanation):

```json
{
  "verdict": "ACTION|DEFER|SKIP",
  "priority": "high|medium|low",
  "action_type": "create_issue|add_label|add_comment|generate_prd|none",
  "suggested_agent": "task-generator|planner|analyst|orchestrator",
  "reasoning": "Brief explanation of recommendation",
  "follow_up_title": "Title for follow-up issue if action_type is create_issue",
  "follow_up_body": "Body for follow-up issue if action_type is create_issue"
}
```

## Rules

1. Verdict MUST be one of: ACTION, DEFER, SKIP
2. Use ACTION for genuine follow-up work that improves the codebase
3. Use DEFER for items that need more context before action
4. Use SKIP for trivial items or false positives
5. Keep reasoning brief (one to two sentences)
6. Only suggest create_issue for substantive follow-ups
