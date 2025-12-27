# PR Comment Triage

Analyze all comments on this pull request and provide a structured triage decision for each.

## Your Task

1. Review each comment from bots (gemini-code-assist, copilot-pull-request-reviewer, coderabbitai) and humans
2. Classify each comment by type and priority
3. Determine the appropriate action for each
4. Return structured JSON that can be parsed by automation

## Classification Rules

| Classification | Description | Action |
|----------------|-------------|--------|
| `quick-fix` | Single file, clear fix, no architecture impact | Implement immediately |
| `standard` | Needs investigation, may affect multiple files | Implement with analysis |
| `strategic` | Questions architecture or approach (why, not how) | Reply with rationale |
| `wontfix` | Invalid, out of scope, or disagree with principle | Reply declining |
| `question` | Needs clarification before proceeding | Reply asking for details |
| `stale` | Already addressed or superseded | Mark resolved |

## Priority Levels

| Priority | Description |
|----------|-------------|
| `critical` | Blocks merge - security, correctness, or breaking change |
| `major` | Should fix before merge - significant improvement |
| `minor` | Nice to have - can address in follow-up |

## Output Format

You MUST output valid JSON that can be parsed. Do NOT include markdown code fences or extra text.

```json
{
  "comments": [
    {
      "id": 123456789,
      "author": "gemini-code-assist",
      "file": "path/to/file.ps1",
      "line": 42,
      "classification": "quick-fix",
      "priority": "major",
      "action": "implement",
      "summary": "Add null check before accessing property",
      "resolution": "Add `if ($null -ne $obj)` guard"
    }
  ],
  "summary": {
    "total": 5,
    "quick_fix": 2,
    "standard": 1,
    "strategic": 0,
    "wontfix": 1,
    "question": 0,
    "stale": 1
  },
  "recommendation": "Implement 3 fixes, decline 1, mark 1 stale"
}
```

## Important Rules

1. **Every comment gets a classification** - No skipping
2. **Be specific in resolution** - Describe exact fix, not vague "fix this"
3. **Preserve comment ID** - Required for automation to acknowledge/reply
4. **Include file and line** - When available from the comment
5. **Security issues are always critical** - Never downgrade security findings

## Comment Sources

- `gemini-code-assist`: Usually high-quality, specific suggestions
- `copilot-pull-request-reviewer`: Often flags patterns, may have false positives
- `coderabbitai`: Detailed reviews, check for overlapping suggestions
- Human reviewers: Highest priority, always address

VERDICT: PASS (when all comments triaged successfully)
