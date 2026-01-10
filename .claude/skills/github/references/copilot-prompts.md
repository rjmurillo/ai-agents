# Copilot Directive Prompts

Guidelines for creating effective @copilot prompts.

---

## Key Principle

GitHub Copilot is **amnesiac**. It has no memory of the codebase, PR context, or prior work. Every @copilot directive must be a complete, self-contained prompt.

**Before posting any @copilot directive, use the prompt-builder agent to generate a high-quality prompt.**

---

## Workflow

1. Gather context (PR diff, review comments, codebase patterns)
2. Invoke prompt-builder to synthesize a comprehensive prompt
3. Post the generated prompt via issue comment or PR comment reply

```powershell
# Step 1: Gather context
$pr = pwsh -NoProfile scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles | ConvertFrom-Json
$threads = pwsh -NoProfile scripts/pr/Get-UnresolvedReviewThreads.ps1 -PullRequest 50 | ConvertFrom-Json

# Step 2: Use prompt-builder agent to generate the directive
# Pass context to prompt-builder, which will create an actionable, specific prompt

# Step 3: Post the generated prompt
pwsh -NoProfile scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "$generatedPrompt"
# OR for PR comment reply:
pwsh -NoProfile scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123 -Body "$generatedPrompt"
```

---

## Prompt Quality Requirements

Copilot prompts MUST include:

- **Specific file paths**: Copilot cannot infer which files to modify
- **Exact requirements**: Use imperative language (MUST, WILL, NEVER)
- **Success criteria**: Define what "done" looks like
- **Constraints**: Coding standards, patterns to follow, things to avoid
- **Context**: Relevant code snippets, error messages, or review feedback

---

## Anti-patterns

| Bad | Why |
|-----|-----|
| `@copilot please fix this` | No specifics, no file paths |
| `@copilot refactor the code` | Vague scope, no constraints |
| `@copilot address the review comments` | Assumes context Copilot doesn't have |

**Good example:**

```text
@copilot In src/Services/UserService.cs, refactor the GetUser method
to use async/await. MUST maintain the existing interface signature.
MUST add null checks for the userId parameter. Follow the pattern
in src/Services/OrderService.cs line 45-60.
```

---

## When to Use Each Tool

| Scenario | Tool | Rationale |
|----------|------|-----------|
| Creating new @copilot prompt | prompt-builder | Builds from scratch with validation |
| Refining existing prompt template | prompt-optimizer | Applies research-backed improvements |
| Complex multi-step task | prompt-builder | Handles context gathering and structure |

---

## Prompt-Builder Integration

The prompt-builder agent follows a structured process:

1. **Research**: Analyzes codebase patterns, README, existing code
2. **Draft**: Creates specific, imperative instructions
3. **Validate**: Tests prompt clarity through Prompt Tester persona
4. **Iterate**: Refines until success criteria are met

Invoke prompt-builder with the context you gathered:

```text
Create a @copilot prompt for:
- Task: [what Copilot should do]
- Files: [which files to modify]
- Context: [PR diff, review comments, error messages]
- Constraints: [coding standards, patterns to follow]
```
