# github-url-intercept

Routes any `github.com` URL in your prompt to a script or `gh api` call instead of a page fetch. A GitHub HTML page is 5 to 10 MB. The API response is 1 to 50 KB of structured JSON.

## When to use it

- You paste a GitHub URL: a pull request, issue, blob, tree, commit, compare, gist, or Actions run.
- You say `analyze this PR`, `look at this issue`, or `what does this commit do`.
- Your prompt has a URL with a comment fragment such as `#discussion_r123`, `#issuecomment-123`, or `#pullrequestreview-123`, and a question about it.

## When not to use it

- You want to create a PR, post a comment, or add a label: use [`github`](github.md) instead.
- You work on the current repository and have no URL: use [`github`](github.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:github-url-intercept`. The harness loads it when a `github.com` URL appears in your prompt. To ask for it by name, say:

```text
Use the github-url-intercept skill to summarize https://github.com/owner/repo/pull/123.
```

The agent parses the URL, picks a script or `gh api` call, and answers from the JSON. It does not fetch the HTML page.

## What you get

Structured JSON from the matching call, and an answer built from it. Scripts return an envelope with `"Success": true` on a good call.

| URL shape | Route |
| --- | --- |
| `/pull/{n}` | `get_pr_context.py` (add `--include-diff` for the diff) |
| `/pull/{n}` review comments | `get_pr_review_comments.py` |
| `/pull/{n}` review threads | `get_pr_review_threads.py` |
| `/pull/{n}/checks` | `get_pr_checks.py` |
| `/issues/{n}` | `get_issue_context.py` |
| `/blob/{ref}/{path}` or `/tree/{ref}/{path}` | `gh api repos/{o}/{r}/contents/{path}?ref={ref}` |
| `/commit/{sha}` | `gh api repos/{o}/{r}/commits/{sha}` |
| `/compare/{base}...{head}` | `gh api repos/{o}/{r}/compare/{base}...{head}` |
| `gist.github.com/{owner}/{id}` | `gh api gists/{id}` |
| `/actions/runs/{run_id}/job/{job_id}` | `gh api repos/{o}/{r}/actions/jobs/{job_id}` |

The scripts come from the [`github`](github.md) skill. Raw `gh api` calls are the fallback when no script covers the URL.

## Advanced use

Routing steps: detect the URL, extract owner and repo (or gist owner and id), classify the type, and extract any fragment. If a `github` script exists for the type, use it. Otherwise use `gh api`. A fragment always goes to `gh api` with the specific endpoint.

| Fragment | Call |
| --- | --- |
| `#discussion_r{id}` or `#r{id}` | `gh api repos/{o}/{r}/pulls/comments/{id}` |
| `#issuecomment-{id}` | `gh api repos/{o}/{r}/issues/comments/{id}` |
| `#pullrequestreview-{id}` | `gh api repos/{o}/{r}/pulls/{n}/reviews/{id}` |

Gist URLs with no owner, query strings, file fragments, `.js` embed URLs, raw-content URLs, revision SHAs, and `/revisions` or `/raw` suffixes all route through the gist API. A pinned revision stays pinned. A raw file URL returns only that file. Several URLs in one prompt are parsed one by one and batched.

Check how a URL routes with the bundled validator. From the root of a checkout of this repository:

```bash
uv run python .claude/skills/github-url-intercept/scripts/test_url_routing.py --url https://github.com/octo-org/octo-repo/pull/123
```

It exits `0` when the URL routes and `1` for an invalid URL format. The skill also bundles `gist_routing.py` and `url_validation.py` next to it. The validator protects against command injection (CWE-78).

The skill forbids `web_fetch`, `curl`, or any browser fetch on a GitHub URL. It also forbids `gh pr view` without `--json`.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`github`](github.md): scripts for the actions this skill does not cover, such as creating PRs and posting comments.
- [`pr-comment-responder`](pr-comment-responder.md): work the review threads on one PR.
- Source: [`SKILL.md`](../../src/claude/skills/github-url-intercept/SKILL.md)
- Reference: [`patterns.md`](../../src/claude/skills/github-url-intercept/references/patterns.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
