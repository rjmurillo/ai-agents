# Response Templates

## Reply Guidelines

**DO mention reviewer when**:

- You have a question that needs their answer
- You need clarification to proceed
- The comment requires their decision

**DO NOT mention reviewer when**:

- Acknowledging receipt (use reaction instead)
- Providing a final resolution (commit hash)
- The response is informational only

**Why this matters**:

- Mentioning @copilot triggers a new PR analysis (costs premium requests)
- Mentioning @coderabbitai triggers re-review
- Unnecessary mentions create noise and cleanup work

## Reply API Usage

**CRITICAL**: Never use the issue comments API (`/issues/{number}/comments`) to reply to review comments. This places replies out of context as top-level PR comments instead of in-thread.

```powershell
# In-thread reply (CORRECT)
pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest [number] -CommentId [id] -Body "[response]"

# For multi-line responses
pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest [number] -CommentId [id] -BodyFile reply.md

# Top-level PR comment (no CommentId)
pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest [number] -Body "[response]"
```

## Templates

### Won't Fix

```markdown
Thanks for the suggestion. After analysis, we've decided not to implement this because:

[Rationale]

If you disagree, please let me know and I'll reconsider.
```

### Question/Clarification

```markdown
@[reviewer] I have a question before I can address this:

[Question]

Once clarified, I'll proceed with the implementation.
```

### Acknowledged (for complex items)

```markdown
Understood. This will require [brief scope]. Working on it now.
```

### Resolution Reply

```markdown
Fixed in [commit_hash].

[Brief summary of change]
```

## Security Domain Priority

Process comments in priority order by domain:

| Comment Domain | Keywords | Priority |
|----------------|----------|----------|
| **Security** | CWE, vulnerability, injection, XSS, SQL, CSRF, auth | +50% (Always first) |
| **Bug** | error, crash, exception, fail, null | Standard |
| **Style** | formatting, naming, convention | Standard |

### Security Keyword Detection

```text
CWE-\d+          # CWE identifier
vulnerability    # General security issue
injection        # SQL, command, code injection
XSS              # Cross-site scripting
SQL              # SQL-related
CSRF             # Cross-site request forgery
auth             # Authentication/authorization
secrets?         # Secret exposure
credentials?     # Credential exposure
TOCTOU           # Time-of-check-time-of-use
symlink          # Symlink attacks
traversal        # Path traversal
sanitiz          # Input sanitization
escap            # Output escaping
```
