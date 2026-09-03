# Stacked PRs merge only through the async REST endpoint

## Statement

A pull request GitHub considers part of a stack cannot be merged by GraphQL
`mergePullRequest`, by `gh pr merge`, or by the synchronous REST endpoint
`PUT /repos/{owner}/{repo}/pulls/{n}/merge`. All three refuse. The only working
path is:

```
PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge-async
    header: X-GitHub-Api-Version: 2026-03-10
    body:   sha            REQUIRED for this caller, see below
            merge_method, merge_action, commit_title, commit_message
```

then poll

```
GET /repos/{owner}/{repo}/pulls/{pull_number}/merge-async/{uuid}
```

`sha` is optional to the API and mandatory for any caller in this repository.
It pins the merge to the head the readiness check actually validated. Without
it the API uses whatever the head is when the merge executes, so a push landing
between the readiness check and the merge gets merged unvalidated. With it, the
API cancels the merge instead. That is the invariant issue #5473 exists to
protect, and it is the one body field that is not a convenience.

The HTTP code and the body `status` are different signals. Do not read one as
the other:

- `202`: the request was accepted and will run in the background. The body
  carries `status: pending` with a `details.message` of "Merge request
  enqueued." Enqueued here describes GitHub's internal merge request, not a
  repository merge queue.
- `200`: the PR was already merged, OR it is already in a merge queue. Those
  are different outcomes and the body distinguishes them. A caller that reads
  `200` as "merged" will report success for a PR that is still queued.
- `409`: a merge request is already in flight; the body returns that request's
  UUID. Reuse it rather than issuing a second request.
- `400`: the PR is not mergeable, for example closed or still a draft.

Only the polled body `status` is terminal. `pending` means keep polling;
`merged` is the success case observed below. Never report a result from the
HTTP code alone.

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
PRs. Before calling it, enumerate the stack and prove every OPEN member at or
below the requested position is merge-ready.

Open is load bearing. A stack keeps its merged members: stack #5472 still
listed #5470 after it merged, with `state: closed` and a `merged_at`. A closed
member cannot pass a readiness check, so a gate that tests every member rejects
a stack that is perfectly safe to merge. Filter to open members first, then
gate those.

- `GET /repos/{owner}/{repo}/pulls/{n}` carries a `stack` object
  (`{"id":..., "number":..., "base":..., "size":..., "position":...}`).
  The key is absent on unstacked PRs, which is the cheap test for whether the
  async path is needed at all.
- `GET /repos/{owner}/{repo}/stacks/{stack_number}` lists members with `state`
  and `merged_at`, which is what makes the open filter possible.

Branch protection and repository rules are NOT evaluated when the request is
accepted, only basic PR state checks, so a `202` is not evidence the merge will
succeed.

## Measured

2026-09-02, PR #5471 (T1, CLEAN, base main, 101 checks passed, 0 unresolved
threads). Stack #5472 held #5470 (already merged) and #5471, so the call landed
one PR. Squash merge produced `ef34453af203206cc69e0aa4ab4ff8c3c86395b9` at
2026-09-02T03:48:13Z.

Recorded on issue #5473, which tracks wiring this into `merge_pr.py`. Until
that lands, `pr-autofix` dead-ends on any stacked PR and the operator has to
call the endpoint directly.

Docs: https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request-asynchronously
