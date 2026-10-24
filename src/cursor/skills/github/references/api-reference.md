# GitHub Skill API Reference

Reference documentation for the GitHub skill. For usage, see `../SKILL.md`.

## Exit Codes

| Code | Meaning | Claude Action |
|------|---------|---------------|
| 0 | Success | Parse JSON output |
| 1 | Invalid parameters | Check script parameters |
| 2 | Resource not found | PR/issue/milestone doesn't exist |
| 3 | GitHub API error | Check error message, may be rate limit |
| 4 | gh CLI not authenticated | Run `gh auth login` |
| 100 | Not mergeable (`merge_pr.py`, script-specific) | PR has conflicts or checks failing |

## API Endpoints Used

| Script | Endpoint |
|--------|----------|
| `get_pr_context.py` | `gh pr view --json ...` |
| `get_pr_review_comments.py` | `repos/{owner}/{repo}/pulls/{pr}/comments` |
| `get_pr_review_threads.py` | GraphQL: `repository.pullRequest.reviewThreads` |
| `get_pr_reviewers.py` | Multiple: pulls/comments, issues/comments, pr view |
| `new_pr_review_comment.py` | `repos/{owner}/{repo}/pulls/{pr}` (head SHA), then POST `repos/{owner}/{repo}/pulls/{pr}/comments` with `commit_id`, `path`, `line`, `side` |
| `post_pr_comment_reply.py` | `repos/{owner}/{repo}/pulls/{pr}/comments` (with in_reply_to) |
| `resolve_pr_review_thread.py` | GraphQL: `resolveReviewThread` mutation |
| `close_pr.py` | `gh pr close` |
| `reopen_pr.py` | `gh pr reopen` |
| `merge_pr.py` | `gh pr merge` |
| `Get-IssueContext` | `gh issue view --json ...` |
| `Set-IssueLabels` | `repos/{owner}/{repo}/labels`, `gh issue edit --add-label` |
| `Set-IssueMilestone` | `gh issue edit --milestone` |
| `Post-IssueComment` | `repos/{owner}/{repo}/issues/{issue}/comments` |
| `Add-CommentReaction` | `repos/{owner}/{repo}/pulls/comments/{id}/reactions` or `issues/comments/{id}/reactions` |
| `Invoke-CopilotAssignment` | `repos/{owner}/{repo}/issues/{issue}/comments`, `gh issue edit --add-assignee` |

## `get_pr_context.py` Output Fields

The `Data` object returned by `get_pr_context.py` includes these fields.

| Field | Type | Source (`gh pr view --json`) | Notes |
|-------|------|------------------------------|-------|
| `number` | int | `number` | PR number |
| `title` | string | `title` | PR title |
| `body` | string | `body` | PR description |
| `state` | string | `state` | `OPEN`, `CLOSED`, or `MERGED` |
| `author` | string \| null | `author.login` | Login of the PR author |
| `head_branch` | string | `headRefName` | Source branch name |
| `head_sha` | string \| null | `headRefOid` | Head commit SHA. Use as the expected remote SHA for force-push and push safety checks: compare the local branch ref against this before any push. `null` if the API omits `headRefOid` or returns it as `null`. |
| `base_branch` | string | `baseRefName` | Target branch name |
| `labels` | list[string] | `labels[].name` | Label names |
| `commits` | int | `len(commits)` | Number of commits |
| `additions` | int | `additions` | Lines added |
| `deletions` | int | `deletions` | Lines removed |
| `changed_files` | int | `changedFiles` | Files changed |
| `mergeable` | string | `mergeable` | `MERGEABLE`, `CONFLICTING`, or `UNKNOWN` |
| `status_checks` | list[object] | `statusCheckRollup` | Raw `CheckRun` and `StatusContext` records. Empty when the rollup is `null`. |
| `status_check_total_count` | int | `len(statusCheckRollup)` | Number of returned status checks. |
| `review_thread_total_count` | int | GraphQL `reviewThreads.totalCount` | Total review threads reported by GitHub. |
| `review_thread_returned_count` | int | GraphQL `reviewThreads.nodes` | Review-thread nodes returned across all pages. |
| `review_thread_unresolved_count` | int | GraphQL `reviewThreads.nodes[].isResolved` | Unresolved threads among returned nodes. |
| `review_thread_counts_complete` | bool | Derived | Whether returned thread count equals GitHub's total count. |
| `merged` | bool | `bool(mergedAt)` | Whether the PR is merged |
| `merged_by` | string \| null | `mergedBy.login` | Who merged the PR |
| `created_at` | string | `createdAt` | ISO 8601 timestamp |
| `updated_at` | string | `updatedAt` | ISO 8601 timestamp |
| `diff` | string \| null | `gh pr diff` | Populated only with `--include-diff` |
| `files` | list[string] \| null | `gh pr diff --name-only` | Populated only with `--include-changed-files` |
| `owner` | string | (resolved) | Repository owner |
| `repo` | string | (resolved) | Repository name |

## `test_pr_merged.py` Output Fields

The script prints one flat JSON object. Branch on `merged`, not the exit code.

| Field | Type | Source (GraphQL) | Description |
|-------|------|------------------|-------------|
| `success` | bool | (constant) | `true` when the query answered |
| `pull_request` | int | (argument) | PR number queried |
| `owner` | string | (resolved) | Repository owner |
| `repo` | string | (resolved) | Repository name |
| `state` | string \| null | `state` | `OPEN`, `CLOSED`, or `MERGED` |
| `merged` | bool | `merged` | Whether the PR is merged |
| `merged_at` | string \| null | `mergedAt` | ISO 8601 merge time |
| `merged_by` | string \| null | `mergedBy.login` | Who merged the PR |
| `head_ref` | string \| null | `headRefName` | Source branch name |
| `head_sha` | string \| null | `headRefOid` | Head commit SHA |
| `merge_commit_sha` | string \| null | `mergeCommit.oid` | Merge commit SHA. `null` until the PR merges |

Post-merge cleanup in `pr-autofix` reads `head_ref`, `head_sha`, and
`merge_commit_sha` to find and remove the PR worktree.

## Shared Module Functions

All scripts import `modules/GitHubCore.psm1`:

| Function | Purpose |
|----------|---------|
| `Get-RepoInfo` | Infer owner/repo from git remote |
| `Resolve-RepoParams` | Resolve or error on owner/repo |
| `Test-GhAuthenticated` | Check gh CLI auth status |
| `Assert-GhAuthenticated` | Exit if not authenticated |
| `Write-ErrorAndExit` | Consistent error handling |
| `Invoke-GhApiPaginated` | Fetch all pages from API |
| `Get-IssueComments` | Fetch all comments for an issue |
| `Update-IssueComment` | Update an existing comment |
| `New-IssueComment` | Create a new issue comment |
| `Get-TrustedSourceComments` | Filter comments by trusted users |
| `Get-PriorityEmoji` | P0-P3 to emoji mapping |
| `Get-ReactionEmoji` | Reaction type to emoji |
| `Test-GitHubNameValid` | Validate owner/repo names (CWE-78 prevention) |
| `Test-SafeFilePath` | Prevent path traversal (CWE-22 prevention) |
| `Assert-ValidBodyFile` | Validate BodyFile parameter |

## Body and Comment Files

One rule covers every github skill script that reads `--body-file` or `--comment-file`: `post_issue_comment.py`, `new_issue.py`, `close_issue.py`, `reopen_issue.py`, `close_pr.py`, `edit_issue_body.py`, `post_pr_comment_reply.py`, `add_pr_review_thread_reply.py`, `new_pr_review_comment.py`, `new_pr.py`, and `edit_pr_body.py`.

Relative paths resolve differently per script, so pass an absolute path. `close_issue.py` resolves against `GITHUB_WORKSPACE` when set, else the checkout that holds the script. `reopen_issue.py` resolves against `GITHUB_WORKSPACE` when set, else the git root of the working directory. `new_pr.py` and `edit_pr_body.py` resolve against the repo root. Every other script resolves against the working directory. That base only resolves the path and is not an extra root. The file must resolve under the repo root, a temp directory (`TMPDIR`, the system temp dir, `/tmp`, `/private/tmp`), or the git dir; `new_pr.py` and `edit_pr_body.py` refuse the git dir (see below). Outside a repository there is no repo root, and the working directory is never a root. A path under `/proc`, `/sys` or `/dev` exits 2 under every root. Files below `/dev/shm` are exempt from that rule, so they pass only when `/dev/shm` is the temp directory, such as with `TMPDIR=/dev/shm`. Any other path exits 2, including a symlink that points out of those roots. A session scratchpad under `/tmp` passes, so write the body there and pass the path. Do not inline it with `--comment "$(cat file)"`.

The rule lives in `github_core.validation.is_allowed_body_file_path`. `assert_valid_body_file` wraps it for scripts that exit directly. `close_issue.py`, `reopen_issue.py` and `new_issue.py` call the predicate so they keep their JSON error envelope. `new_pr.py`, `edit_pr_body.py`, `close_issue.py`, `reopen_issue.py` and `post_issue_comment.py` then read the file with `read_body_file_text`. `new_pr.py` loads `github_core` by path because it runs under `python3 -I`. `new_pr.py` and `edit_pr_body.py` also refuse a body that still holds the `<!-- replace with PR body -->` line.

`read_body_file_text` resolves the parent directory once and leaves the file name unresolved. It opens the file by walking down from the filesystem root, one directory at a time, with `O_NOFOLLOW` on every step and `O_NONBLOCK` on the file. A symlinked file, a parent swapped for a symlink after the check, and a FIFO all fail. The checks then run on the opened objects:

- A regular file with one hard link, owned by you, and not world-writable.
- At most 65536 characters, GitHub's body limit. A larger file is refused before the API call.
- A `pr-body-*.md` file from `--prepare-body-file` must be mode 600.
- Below a temp root, every directory down to the file must be owned by you with no group or other write bit. The walk starts at the broadest root, so a `TMPDIR` inside `/tmp` is checked too.
- Below the repo root or the git dir, every directory down to the file must belong to you or to root. One that anyone can write needs the sticky bit. Group write is allowed there, since umask 002 leaves repo directories at mode 775. For a linked worktree's git dir the walk starts at the common git dir. The clone root above it is not checked: whoever can write there can already replace `.git`. A checkout another user owns is refused, even when you run as root. ACLs are not read, only mode bits.
- A group-writable file, such as mode 664 from umask 002, passes only inside a directory only you can enter (mode 700). Every directory between that one and the file must be yours and refuse other writers. The session scratchpad qualifies. Otherwise run `chmod 600` on the file.
- No dotfile and no dot directory at any depth below the root, so `.env`, `service/.env` and `.git/config` all fail. The scratch directory that `--prepare-body-file` uses is the one exception.
- A temp root that others can write, such as `/tmp`, needs the sticky bit and must belong to root or to you.
- No component that NTFS could read as another name: one with `:` (a stream), `~` and a digit (an 8.3 short name such as `GIT~1`), or a trailing dot or space. This applies on every platform. On Windows the checks run again on the real name of the opened file. Windows also refuses any junction or other reparse point on the path, so a OneDrive Files On-Demand file is refused; copy the body to a local folder first.
- `new_pr.py` and `edit_pr_body.py` refuse the git dir and the common git dir, even though the general rule above lists the git dir. `close_issue.py`, `reopen_issue.py` and `post_issue_comment.py` keep the documented git-dir reply flow: they accept a linked worktree's own git dir (`.git/worktrees/<name>/`). They refuse its `config` and `config.worktree` files and a primary clone's `.git`. `new_issue.py` does not use this reader and still accepts any path in the git dir.

Other scripts still open the path as given. Keep body files in a private directory such as the session scratchpad.

These readers differ on purpose:

- `new_pr.py --prepare-body-file` still allocates a unique, random file name in the repo's scratch directory, which passes the rule. Use it when several sessions share one scratch directory: a fixed name such as `body.md` lets one session publish another's text, and the rule does not prevent that (owner decision D14, 2026-10-24, issue #6667).
- `validate_pr_description.py` only reads the file and posts nothing, so it has no containment check.
- `new_validated_pr.py` (the repo-level PR wrapper, not a skill script) reads the source body path with no containment check, then copies it into the allocated scratch file that `new_pr.py` reads.
- CI-only scripts in the workflow scripts directory are outside the rule. Its own `post_issue_comment.py` reads any `--body-file`; workflows (`ai-spec-review.yml`, `investigation-claim-backstop.yml`, `pr-validation.yml`) supply the path.

## Troubleshooting

### "Could not infer repository info"

Run from within a git repository, or provide `-Owner` and `-Repo` explicitly.

### "gh CLI not authenticated"

Run `gh auth login` and authenticate with GitHub.

### Comment with `-Marker` already exists

The script skips the post and exits 0. This is idempotency working correctly.

### "Milestone not found"

The milestone must already exist in the repository. Create it via GitHub UI or `gh api`.

### "PR is not mergeable"

Check for merge conflicts or failing required checks. Use `get_pr_context.py` to see `Mergeable` status.

## update_pr_branch.py details

- The script merges the base branch into the PR head through the GitHub update-branch API. It does not rebase.
- Exit 0 with `already_up_to_date: true` means the head already contains the base.
- With `--wait`, the wait ends only when compare shows the PR is not behind. A timeout exits 3.
- Exit 1 with `reason: head_moved` means the head differs from `--expected-head-sha`.

## new_pr_review_comment.py

Starts a new review thread on a diff line. Use `post_pr_comment_reply.py` to reply to an existing thread.

- `--side RIGHT` (default) targets added or unchanged lines. `--side LEFT` targets removed lines.
- `--line` is the file line number on that side, and it must fall inside the PR diff.
- The script reads the PR head commit and sends it as `commit_id`, so the comment anchors to the current head.
- `body`, `path`, `commit_id`, and `side` go out as raw `-f` fields. Only `line` is a typed `-F` field. Do not switch `body` to `-F`, because a body that starts with `@` would then be read as a file.
- Output uses the standard skill envelope. Pass `--output-format json` to force JSON.
- Exit 0: created. `Data` carries `comment_id`, `html_url`, `pull_request`, `path`, `line`, `side`, `commit_id`, `created_at`.
- On an API failure, `Error.Code` is the exit code and `Error.Type` names the cause. `Data` echoes the PR, path, line, and side.
- Argument and body errors happen before any API call. They print plain text to stderr and exit 2.
- Exit 2: the PR is not found, the body is invalid, or the API returned 400 or 422 (line or path not in the diff).
- A `--body-file` that is empty, unreadable, or not UTF-8 also exits 2. The literal backslash-n check applies to an inline `--body` only.
- Exit 2 also covers a session whose network policy refuses GitHub.
- Exit 3: another API failure, a quota refusal, or a timeout.
- A timeout on the POST can still create the comment. Before retrying after exit 3, run `get_pr_review_comments.py` and look for the body, or a retry can post a duplicate thread.
- Exit 4: not authenticated, or the token cannot write to the PR.

## Skills Applied

| Skill ID | Description | Script |
|----------|-------------|--------|
| Skill-PR-001 | Enumerate all reviewers before triaging | `get_pr_reviewers.py` |
| Skill-PR-004 | Use `in_reply_to` for thread replies | `post_pr_comment_reply.py` |

## Related

- **Agent**: `pr-comment-responder` - Full PR comment handling workflow
- **Module**: `.github/scripts/AIReviewCommon.psm1` - Simple wrappers for workflows
- **Memory**: `usage-mandatory` - Enforcement rules for using skills
