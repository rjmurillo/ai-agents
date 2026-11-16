# A watcher's "all required checks passed" can omit a context that has not reported yet

## Statement

A required context that has not reported is absent, not pending.
A count of passed required checks then reads complete when it is not.
The T3 PR watcher said "All 8 required checks passed" on PR #7402.
The ruleset listed 9 required contexts on 2026-11-16.
Compare against `fetch_ruleset_required_contexts` in `scripts/github_core/checks_rollup.py`.
A non-empty set difference means a required context is still missing.

## Practice

- Read the required set from the ruleset, not from the watcher's count.
- `merge_pr.py --dry-run` passed while the real merge was refused.
- So a dry-run PASS does not prove the ruleset is met.
- With the head reviewed and a context still missing, arm auto-merge.
- Use `merge_pr.py --strategy squash --auto --expected-head-sha <full head SHA>`.
- GitHub then merges once the last context reports.
- `diagnosing-a-blocked-pr.md` covers the case with nothing missing.

## Evidence (PR #7402, head a75fc4dd7, 2026-11-16)

- OBSERVED 15:42:32Z: the T3 notification said "All 8 required checks passed on a75fc4d".
- OBSERVED 15:43:33Z: `merge_pr.py --dry-run` returned "PR #7402 would be merged".
- OBSERVED 15:44:07Z: the real call failed with "the base branch policy prohibits the merge".
- OBSERVED 15:44:58Z: the ruleset listed 9 contexts. `get_pr_checks.py` showed 8 required rows.
- OBSERVED: `Run Python Tests` was not in that list at all.
- OBSERVED 15:45:13Z: auto-merge was armed on the full head SHA. The PR merged as 0b070c14b.
- INFERRED: the context appears late because its job waits on others.
- The `test-result` job in `.github/workflows/pytest.yml` has a long `needs:` list.
- INFERRED: the refusal came from the missing context.
- `github-merge-rest-is-authoritative-blocked-is-not.md` saw the same error with every check green (#4362).
- An empty set difference points to that memory's case instead.

## Related

- `diagnosing-a-blocked-pr.md`
- `github-a-new-push-turns-off-auto-merge-armed-with-an-expected-head.md`
- `github-expected-head-sha-must-be-the-full-sha.md`
