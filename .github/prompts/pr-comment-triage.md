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

Your ENTIRE response must be a single JSON object. NO other text.

- Start your response with `{` and end with `}`
- Do NOT wrap JSON in markdown code fences
- Do NOT include explanations before or after the JSON

### Required JSON Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `comments` | array | Yes | One entry per comment analyzed |
| `comments[].id` | number | Yes | Comment ID from GitHub API |
| `comments[].author` | string | Yes | Username of commenter |
| `comments[].file` | string | When available | File path the comment references |
| `comments[].line` | number | When available | Line number the comment references |
| `comments[].classification` | string | Yes | One of: `quick-fix`, `standard`, `strategic`, `wontfix`, `question`, `stale` |
| `comments[].priority` | string | Yes | One of: `critical`, `major`, `minor` |
| `comments[].action` | string | Yes | One of: `implement`, `reply`, `resolve` |
| `comments[].summary` | string | Yes | Brief description of the issue |
| `comments[].resolution` | string | Yes | Specific fix or response |
| `summary` | object | Yes | Counts by classification |
| `recommendation` | string | Yes | Human-readable summary of actions |
| `verdict` | string | Yes | `PASS` or `WARN` |

### Verdict Values

- `PASS`: All comments classified successfully
- `WARN`: Comments classified but some marked as `question` (needs human input)

### CORRECT (raw JSON only)

{"comments":[{"id":123456789,"author":"gemini-code-assist","file":"src/utils.ps1","line":42,"classification":"quick-fix","priority":"major","action":"implement","summary":"Add null check before accessing property","resolution":"Add `if ($null -ne $obj) { ... }` guard at line 42"}],"summary":{"total":1,"quick_fix":1,"standard":0,"strategic":0,"wontfix":0,"question":0,"stale":0},"recommendation":"Implement 1 fix","verdict":"PASS"}

### INCORRECT (has wrapper text)

Here's my analysis of the PR comments:

```json
{"comments":[...],"verdict":"PASS"}
```

Let me know if you need clarification.

## Important Rules

1. **Every comment gets a classification** - No skipping
2. **Resolution must be actionable** - Include exact code or steps
   - CORRECT: "Add `if ($null -ne $obj) { ... }` guard at line 42"
   - INCORRECT: "Fix the null reference issue"
3. **Preserve comment ID** - Required for automation to acknowledge/reply
4. **Include file and line** - When available from the comment
5. **Security issues are always critical** - Never downgrade security findings

## Comment Source Handling

| Source | Default Priority | Notes |
|--------|------------------|-------|
| Human reviewers | `major` minimum | Upgrade to `critical` if blocking |
| `gemini-code-assist` | As warranted | High-quality, specific suggestions |
| `coderabbitai` | As warranted | Check for duplicates with other bots |
| `copilot-*` | As warranted | Higher false-positive rate |
