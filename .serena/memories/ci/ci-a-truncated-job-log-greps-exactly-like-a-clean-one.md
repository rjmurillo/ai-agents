# A truncated job log greps exactly like a clean one

`gh api repos/O/R/actions/jobs/<id>/logs` redirects to
`productionresultssa*.blob.core.windows.net`. That redirect fails transiently. When it
fails, `gh` writes the connection error into your output file and exits **0**:

```
error connecting to productionresultssa12.blob.core.windows.net
check your internet connection or https://githubstatus.com
```

That file is 123 bytes. Every grep against it returns nothing. An agent looking for a
known failure signature reads that silence as "the signature is absent" and concludes the
failure has a different cause.

## What this cost

2026-08-04, PR #4567. I pulled the `Aggregate Results` log this way, grepped for
`NEEDS_REVIEW|rate limit|403|DID_NOT_RUN`, got zero hits, and published:

> "This is therefore NOT the #4547 rate-limit signature. The cause is still unknown."

The real log had `FINAL_VERDICT: DID_NOT_RUN` and **all ten** agent verdicts at
`NEEDS_REVIEW`. It was exactly the #4547 signature. The correct action (a full re-run)
was the one I had just argued against.

## The rule

Before grepping any fetched log, check its size:

```bash
wc -c "$LOG"      # < 1000 bytes on a CI job log means you fetched an error, not a log
```

## The reliable path

`gh run view <run_id> --log-failed` reads a different backend and worked on the first
try for the same job, in the same minute, when the REST endpoint was failing. Prefer it.

It emits ANSI escapes, so pipe through `grep`, never `cat` (plain `gh api` on such a
response refuses with "the response contains terminal escape sequences").

## Why the generic instinct is wrong here

The usual instinct is "empty grep means the string is absent." That holds only when the
haystack is known-good. A fetched log is not known-good until you have measured it. This
is the same failure class as trusting a detector you never proved can fail: the
instrument returned a clean reading because it was never pointed at the data.

## Related

- `.serena/memories/ci/github-rate-limit-payload-does-not-predict-service.md`
- `.serena/memories/ci/ci-job-names-collide-so-a-red-check-name-is-ambiguous.md`
