# PR Comment Triage

## Task

Analyze all review comments on this PR and provide a structured triage for automated processing.

## Input Context

The context includes:

- PR description and title
- PR diff (changes made)
- Review comments from bots and humans

## Classification Rules

Classify each comment into ONE category:

| Classification | When to Use | Action |
|---------------|-------------|--------|
| `quick-fix` | Single file, clear fix, no architecture impact | Implement immediately |
| `standard` | Needs investigation, may affect multiple files | Delegate to orchestrator |
| `strategic` | Question is whether not how | Requires discussion |
| `wontfix` | Decline with documented rationale | Reply with explanation |
| `question` | Need clarification from reviewer | Reply asking for details |

## Reviewer Signal Quality

Apply these biases when triaging:

| Reviewer | Signal Quality | Guidance |
|----------|---------------|----------|
| `cursor[bot]` | High (100%) | Process immediately, historically accurate |
| Human reviewers | High | Prioritize, domain expertise |
| `coderabbitai[bot]` | Medium (~30%) | Triage carefully, many false positives |
| `copilot[bot]` | Medium (~30%) | Verify before acting |
| `gemini-code-assist[bot]` | Medium | Documentation-focused suggestions |

## Required Output Format

Output a JSON object with this exact structure:

```json
{
  "comments": [
    {
      "id": 123456789,
      "thread_id": "PRRT_abc123",
      "author": "reviewer-username",
      "classification": "quick-fix",
      "priority": "critical",
      "action": "implement",
      "summary": "Brief description of what the comment asks for",
      "file_path": "src/example.ts",
      "line_number": 42
    }
  ],
  "synthesis_needed": false,
  "total_comments": 5,
  "actionable_count": 3,
  "already_resolved": 2
}
```

### Field Definitions

| Field | Required | Values |
|-------|----------|--------|
| `id` | Yes | GitHub comment database ID |
| `thread_id` | No | GraphQL thread ID if review thread |
| `author` | Yes | GitHub username of commenter |
| `classification` | Yes | `quick-fix`, `standard`, `strategic`, `wontfix`, `question` |
| `priority` | Yes | `critical`, `major`, `minor` |
| `action` | Yes | `implement`, `reply`, `defer`, `clarify`, `resolve` |
| `summary` | Yes | One sentence describing what needs to be done |
| `file_path` | No | File path if comment is on specific code |
| `line_number` | No | Line number if applicable |

### Priority Rules

- `critical`: Blocks merge, security issue, or breaking change
- `major`: Should be addressed before merge
- `minor`: Nice to have, could be deferred

### Action Rules

- `implement`: Make code changes to address the comment
- `reply`: Post a response without code changes
- `defer`: Create a follow-up issue
- `clarify`: Ask reviewer for more details
- `resolve`: Mark thread as resolved (already addressed)

## Verdict Format

End with:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [Summary of triage results]
```

Use:

- `PASS`: All comments triaged, none blocking
- `WARN`: Has minor or deferrable comments
- `CRITICAL_FAIL`: Has critical unresolved issues
