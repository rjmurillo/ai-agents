# PR Review Reply Uses CommentId

## Guidance

`Post-PRCommentReply.ps1` replies to review comments using `-CommentId`, not a thread ID.
To fully resolve a review thread, post the reply using the comment ID, then call
`Resolve-PRReviewThread.ps1` with the thread ID.

## Example

```powershell
pwsh -NoProfile .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 \
  -PullRequest 918 \
  -CommentId 2693056802 \
  -Body "Fixed in 150c0ee0."

pwsh -NoProfile .claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1 \
  -ThreadId "PRRT_kwDOQoWRls5peCTz"
```

## Why

GitHub review comment replies are tied to the comment ID; thread resolution is a
separate GraphQL mutation.
