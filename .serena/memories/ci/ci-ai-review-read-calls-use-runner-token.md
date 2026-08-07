# AI review read calls should use the runner token before BOT_PAT

## Question

Which token should AI review jobs use for read-only GitHub API calls?

## Decision

Use the runner-scoped `github.token` for read-only calls before falling back to
`BOT_PAT`. Keep `BOT_PAT` for writes that need bot attribution.

## Evidence

Issue #4607 showed AI review context fetches failing with:

```text
HTTP 403: API rate limit exceeded for user ID 6811113
```

The same issue verified account IDs:

```text
rjmurillo id=6811113
rjmurillo-bot id=250269933
```

The context step's credential was `bot-pat`, so a CI read consumed the same user
budget as interactive agent sessions. The fix landed in the AI review composite
actions:

- `.github/actions/ai-review/action.yml`
- `.github/actions/check-agent-infrastructure/action.yml`

Read-only steps now set:

```yaml
GH_TOKEN: ${{ inputs.github-token || github.token || inputs.bot-pat }}
```

The post-analysis write step still uses:

```yaml
GH_TOKEN: ${{ inputs.bot-pat }}
```

## Consequence

CI read traffic no longer spends the shared human PAT budget when the runner
token is available. Bot-attributed writes keep the existing audit trail.
