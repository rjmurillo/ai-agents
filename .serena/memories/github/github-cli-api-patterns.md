# GitHub CLI API Patterns

## Skill-GH-API-001: Direct API Access (96%)

**Statement**: Use `gh api` for endpoints not covered by built-in commands; `--paginate` for complete results.

```bash
# POST request with data
gh api repos/{owner}/{repo}/issues -f title="Bug" -f body="Description"

# Pagination (all results)
gh api --paginate repos/{owner}/{repo}/issues

# JSON filtering with jq
gh api repos/{owner}/{repo}/issues --jq '.[].title'

# Slurp paginated results
gh api --paginate --slurp repos/{owner}/{repo}/issues --jq 'flatten | length'

# Cache responses
gh api --cache 1h repos/{owner}/{repo}/contributors

# GraphQL queries
gh api graphql -f query='query { viewer { login } }'
```

## Skill-GH-GraphQL-001: Single-Line Mutation Format (97%)

**Statement**: Use single-line query format (no newlines) for GraphQL mutations to avoid parsing errors.

```bash
# CORRECT - Single-line format
gh api graphql -f query='mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { id } } }' -f id="PRRT_xxx" -f body="Reply"

# WRONG - Multi-line format causes parsing errors
gh api graphql -f query='
mutation($id: ID!, $body: String!) {
  addPullRequestReviewThreadReply(...) { ... }
}'
```

**Evidence**: PR #212 - 20 threads resolved using single-line format.

## Skill-GH-Auth-001: Authentication Management (91%)

**Statement**: Use `gh auth refresh` to add scopes without re-login.

```bash
# Add scopes
gh auth refresh -s workflow
gh auth refresh -s project
gh auth refresh -s read:packages

# Check auth status
gh auth status

# View token
gh auth token
```

**Required Scopes**: Minimum: `repo`, `read:org`. Add `workflow` for Actions, `project` for Projects.

### `gh auth status` reports a rate limit as an invalid token

Measured 2026-08-04 during a heavy PR sweep. `gh auth status` printed:

```
X Failed to log in to github.com account <user>
- The token in $HOME/.config/gh/hosts.yml is invalid.
- To re-authenticate, run: gh auth refresh -h github.com
```

The account name and home directory above are redacted from the verbatim output.

The token was fine. `gh auth status` validates by calling `/user`, and `/user`
was returning `403 API rate limit exceeded for user ID <id>`. The error handling
maps that 403 to the same message as a 401, so a secondary rate limit is
indistinguishable from a revoked credential in this output.

Three facts make the misread expensive:

1. `gh api rate_limit` showed `core.remaining: 4746` at the same moment. Secondary
   limits never appear there, so the headroom reading looks like it exonerates the
   rate limit and points back at the token.
2. Wrapper scripts inherit the confusion. `.claude/skills/github/scripts/` helpers
   print `GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login'
   first.` for the same condition.
3. The suggested remedy is destructive. Running `gh auth refresh` or `gh auth login`
   against a working credential to fix a rate limit can cost the session its token.

**Discriminating test**, cheaper than any re-auth:

```bash
gh api /user --jq .login          # 403 with "rate limit exceeded" => not an auth problem
gh api rate_limit --jq '.resources.graphql'   # does not consume quota, see caveat below
```

`rate_limit` is exempt from primary rate limiting, so it keeps answering after a
bucket empties, which is what makes it usable as the discriminator here. That is
the only guarantee it carries. It still fails on network errors and on a genuinely
bad credential, and it does not report secondary limits at all, so a healthy
reading from it never proves the request you care about will succeed.

If `/user` returns a rate-limit 403, back off and retry. Do not touch the credential.
A concurrent `git push` over HTTPS plus its hooks is usually what drained the bucket.

## Skill-GH-JSON-001: JSON Output Patterns (94%)

**Statement**: Use `--json` with field names, pipe to `jq` for transformations.

```bash
# With jq filtering
gh pr list --json number,title --jq '.[].title'

# Complex transformation
gh pr list --json number,title,labels \
  --jq '.[] | select(.labels | any(.name == "bug")) | .number'

# Raw output (no quotes)
gh pr view 123 --json title --jq '.title'
```

## Job Logs Refuse To Print Without An Explicit Flag

`gh api repos/OWNER/REPO/actions/jobs/<id>/logs` exits non-zero and prints
only `the response contains terminal escape sequences; pass
--allow-escape-sequences to output it anyway`. Actions logs always carry ANSI
colour, so this fires on every job. It reads like an API or permission
failure and is neither.

```bash
gh api repos/OWNER/REPO/actions/jobs/<id>/logs --allow-escape-sequences > job.log
sed 's/\x1b\[[0-9;]*m//g' job.log      # strip colour for grepping
```

## GraphQL And REST Are Separate Buckets, And Zero Is A Window Not A State

`remaining: 0` on `graphql` does not mean the token is broken and does not
mean waiting is open ended. The window is hourly and refills to the full
5000. Read the reset directly rather than guessing:

```bash
gh api rate_limit --jq '.resources.graphql | "remaining=\(.remaining) in \(.reset - now | floor)s"'
```

`core` and `search` are independent buckets and keep working while `graphql`
is exhausted, so a duplicate-issue search can still run over REST:

```bash
gh api "search/issues?q=repo:OWNER/REPO+is:issue+<terms>&per_page=8" \
  --jq '.total_count, (.items[]? | "#\(.number) [\(.state)] \(.title)")'
```

This matters because most of this repo's skill scripts use GraphQL. When one
returns an empty result set under load, confirm it was not a rate-limit
error before concluding the thing you searched for does not exist. A
rate-limited search that reads as "no duplicates" is how duplicate issues get
filed.

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)
- [github-cli-labels-cache](github-cli-labels-cache.md)
