# Artifact Insight Scanner

Analyze the provided project artifacts for missed insights, action items, and follow-ups that should become tracked issues.

## What to Look For

### 1. Untracked TODOs

- `TODO:` or `FIXME:` comments without linked issues
- "We should..." or "Need to..." statements
- Checkbox items that were never checked (`- [ ]`)
- "Later" or "future work" mentions

### 2. Lessons Not Captured

- Patterns discovered during debugging
- Workarounds that should be documented
- "Next time..." observations
- Root cause insights that could prevent recurrence

### 3. Blocked Work

- Items waiting on external dependencies
- Work paused due to other priorities
- "Once X is done..." statements
- Deferred scope items

### 4. Process Improvements

- Repeated friction points across sessions
- Automation opportunities mentioned
- Documentation gaps identified
- Workflow inefficiencies noted

### 5. Follow-up Tasks

- "After this PR..." commitments
- Review feedback not yet addressed
- Deferred scope items from PRDs
- Testing or validation that was skipped

## Output Format

For each actionable finding, output this exact format:

```text
FINDING:
TYPE: [TODO|LESSON|BLOCKED|IMPROVEMENT|FOLLOWUP]
TITLE: [Concise issue title, 50-70 chars, conventional commit style]
BODY: [Issue body with context, 2-4 sentences]
PRIORITY: [P0|P1|P2|P3]
LABELS: [comma-separated labels from: enhancement, bug, documentation, automation, area-workflows, area-prompts, area-infrastructure, area-installation]
SOURCE: [file path and line/section reference]
---
```

## Priority Guidelines

- **P0**: Security issues, data loss risks, critical blockers
- **P1**: Important functionality gaps, significant user impact
- **P2**: Improvements, process enhancements, nice-to-haves
- **P3**: Minor polish, optional enhancements

## Rules

1. Only report actionable items that should become issues
2. Skip items that are clearly completed or superseded
3. Do not duplicate existing tracked work
4. Use conventional commit prefixes in titles (feat:, fix:, docs:, chore:)
5. Keep issue bodies concise but informative
6. Include enough context for someone unfamiliar with the session

## Deduplication Hints

If an item appears similar to common patterns, note it:

- Session protocol improvements -> Check existing session-related issues
- Memory system changes -> Check memory-related issues
- Workflow automation -> Check area-workflows issues

## Example Output

```text
FINDING:
TYPE: TODO
TITLE: feat(validation): add schema validation for session JSON files
BODY: Session logs currently lack schema validation. Invalid JSON can cause silent failures in downstream tools. Add JSON schema and validation step to session-init skill.
PRIORITY: P2
LABELS: enhancement, area-workflows
SOURCE: .agents/sessions/2026-02-20-session-42.json:15
---

FINDING:
TYPE: IMPROVEMENT
TITLE: docs(memory): document memory tier selection criteria
BODY: Multiple sessions show confusion about when to use Serena vs Forgetful memory. Add decision tree to AGENTS.md clarifying tier selection.
PRIORITY: P2
LABELS: documentation
SOURCE: .agents/retrospective/2026-02-18-retrospective.md:45
---
```

End with:

```text
VERDICT: [PASS if no critical items, WARN if items found]
FINDING_COUNT: [number of findings]
```
