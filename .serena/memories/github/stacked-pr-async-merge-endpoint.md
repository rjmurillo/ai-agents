# Stacked PRs merge only through the async REST endpoint

## Statement

A pull request GitHub considers part of a stack cannot be merged by GraphQL
`mergePullRequest`, by `gh pr merge`, or by the synchronous REST endpoint
`PUT /repos/{owner}/{repo}/pulls/{n}/merge`. All three refuse. The only working
path is:

```
PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge-async
    header: X-GitHub-Api-Version: 2026-03-10
    body:   commit_title, commit_message, sha, merge_method, merge_action
```

then poll

```
GET /repos/{owner}/{repo}/pulls/{pull_number}/merge-async/{uuid}
```

until `status` leaves `pending`. `202` means enqueued, `200` means already
merged or already queued, `409` returns the UUID of an in-flight request,
`400` means the PR is not mergeable (closed or draft).

The verb is PUT. `POST` to the same path returns 404, which is what made the
endpoint look nonexistent during the first investigation.

## Why this is not obvious

`merge_pr.py` has a `_rest_merge` fallback that calls the SYNCHRONOUS
`PUT .../merge`. PR #5474 routed the stack refusal to it and the merge still
failed, because that is a different endpoint. The synchronous one now answers
with an explicit pointer:

```
403 Merging stacked PRs via this endpoint is not supported.
    Use the asynchronous merge endpoint instead.
```

## The gate this endpoint needs

GitHub's docs: "all pull requests in the stack up to and including the
requested PR will be merged into the base branch." One call can land several
PRs. Before calling it, enumerate the stack and prove every member at or below
the requested position is merge-ready:

- `GET /repos/{owner}/{repo}/pulls/{n}` carries a `stack` object
  (`{"id":..., "number":..., "base":..., "size":..., "position":...}`).
  The key is absent on unstacked PRs, which is the cheap test for whether the
  async path is needed at all.
- `GET /repos/{owner}/{repo}/stacks/{stack_number}` lists members with state
  and `merged_at`.

Branch protection and repository rules are NOT evaluated at enqueue time, only
basic PR state checks, so a 202 is not evidence the merge will succeed.

## Measured

2026-09-02, PR #5471 (T1, CLEAN, base main, 101 checks passed, 0 unresolved
threads). Stack #5472 held #5470 (already merged) and #5471, so the call landed
one PR. Squash merge produced `ef34453af203206cc69e0aa4ab4ff8c3c86395b9` at
2026-09-02T03:48:13Z.

Recorded on issue #5473, which tracks wiring this into `merge_pr.py`. Until
that lands, `pr-autofix` dead-ends on any stacked PR and the operator has to
call the endpoint directly.

Docs: https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request-asynchronously
