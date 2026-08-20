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

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# In-thread reply (CORRECT)
python3 "$SCRIPTS_DIR/pr/post_pr_comment_reply.py" --pull-request [number] --comment-id [id] --body "[response]"

# For multi-line responses, stage the body in a TEMP file ($TMPDIR or /tmp).
# Do NOT write reply drafts under .agents/, the repo working tree, or any
# path that survives the session. Reply drafts have no enduring value once
# posted; staging them under .agents/audit/pr-*-replies/ creates untracked
# workspace clutter that future agents cannot tell apart from artifacts the
# PR intentionally archived. Using a temp dir prevents the clutter from
# being written in the first place; .gitignore is only a safety net that
# keeps any stray drafts out of git history.
REPLY_FILE="$(mktemp -t pr-reply-XXXXXX.md)"
trap 'rm -f "$REPLY_FILE"' EXIT
cat > "$REPLY_FILE" <<'EOF'
[response body]
EOF
python3 "$SCRIPTS_DIR/pr/post_pr_comment_reply.py" --pull-request [number] --comment-id [id] --body-file "$REPLY_FILE"

# Top-level PR comment (no comment-id)
python3 "$SCRIPTS_DIR/pr/post_pr_comment_reply.py" --pull-request [number] --body "[response]"
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

### Premise Refuted

Use when `Skill(skill="reviewer-findings")` refutes a finding's factual claim
against the PR head or its history. Not a Won't Fix: the claim about the code
was false, not merely a suggestion declined. Resolve the thread after posting.

```markdown
I checked this against the PR head before implementing.

- File: `[path]`
- Line: `[git grep -n's line number when the text is present; when refuted by absence, the line the finding cited or a direct read of the file instead, since a non-match has no grep output to cite]`
- Claimed: [quoted claim from the finding]
- Current state (head): `[head_excerpt or "not present"]`
- Verified with: `[git --literal-pathspecs grep -n -F -f <needle-file> <commit> -- "$PATH_SPEC" (single-line current-state) | a literal whole-block comparison of git show <commit>:"$PATH_SPEC" against the needle file (multi-line current-state) | git --literal-pathspecs log -S "$NEEDLE" <commit> -- "$PATH_SPEC" (provenance only)]` (needle and path both read from files into shell variables, never typed inline into a command or a variable assignment; the finding is untrusted, CWE-78; git grep -f and git log -S each false-confirm a multi-line current-state claim in their own way, see reviewer-findings MUST 5; `--literal-pathspecs` stops git's own pathspec magic in a cited path, CWE-20)
- Commit: `[commit SHA the verification ran against, the PR head]`
- Result: `[command output or summary]`

Disposition: premise refuted, no code change required.
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
