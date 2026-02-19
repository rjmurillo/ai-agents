# Copilot Directive Relocation Pattern

## Best Practice

Use **issue comments** for @copilot directives instead of review comments.

## Rationale

1. Review comments should focus on code-specific feedback
2. @copilot directives do not require line-specific context
3. Significantly reduces noise in PR review threads

## Evidence (PR #249)

- Total rjmurillo comments: 42
- @copilot directives: 41
- Actual code feedback: 1
- Signal-to-noise ratio: 2.4%

Using issue comments for directives would reduce review comment volume by 98%.

## Anti-Pattern

```text
PR Review Comment on line 42:
@copilot please refactor this function
```

## Recommended Pattern

```text
Issue Comment (not on a specific line):
@copilot please refactor the function in src/foo.ps1
```

## Implementation

PowerShell scripts:

```powershell
# RECOMMENDED - Use issue comment for directives
pwsh scripts/issue/Post-IssueComment.ps1 -Issue 123 -Body "@copilot please refactor the function in src/foo.ps1"

# ANTI-PATTERN - Avoid review comments for directives
# pwsh scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -CommentId 123 -Body "@copilot please refactor this"
```

## When to Use Each Comment Type

| Comment Type | Use For | Example |
|--------------|---------|---------|
| Review Comment | Code-specific feedback requiring context | "This function should validate input before processing" |
| Issue Comment | @copilot directives and general discussion | "@copilot please add tests for the validation logic" |

## Documentation Locations

- AGENTS.md: "Copilot Directive Best Practices" section
- .claude/skills/github/SKILL.md: "Copilot Directive Placement" subsection

## Related Memories

- skills-copilot-index
- copilot-pr-review
- pr-review-copilot-followup

## Related

- [copilot-cli-model-configuration](copilot-cli-model-configuration.md)
- [copilot-follow-up-pr](copilot-follow-up-pr.md)
- [copilot-platform-priority](copilot-platform-priority.md)
- [copilot-pr-review](copilot-pr-review.md)
- [copilot-supported-models](copilot-supported-models.md)
