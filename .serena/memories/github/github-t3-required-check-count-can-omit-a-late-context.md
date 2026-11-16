# A watcher's "all required checks passed" can omit a context that has not reported yet

## Statement

On PR #7402, the T3 PR watcher said "All 8 required checks passed".
The ruleset listed 9 required contexts on 2026-11-16.
The ninth, `Run Python Tests`, had not reported at all.
So the watcher count and a `merge_pr.py --dry-run` PASS do not prove the ruleset is met.
`get_pr_checks.py` reads the ruleset and reports the gap as `MissingRequiredChecks`.

## Practice

- Read `MissingRequiredChecks` and the required state from `get_pr_checks.py`.
- Inside the grace window after a push, it reports an absent aggregate check as queued (#6389).
- Fallback: diff the PR's checks against `fetch_ruleset_required_contexts` in `scripts/github_core/checks_rollup.py`.
- That function returns `None` when the API call fails. Treat `None` as unknown, not as an empty list.
- With the head reviewed and a context still missing, arm auto-merge.
- Use `merge_pr.py --strategy squash --auto --expected-head-sha <full head SHA>`.
- GitHub then merges once the last context reports.

## How this differs from nearby memories

- `diagnosing-a-blocked-pr.md` covers what `get_pr_checks.py` reports for a late context.
- This memory covers two signals that do not see it: the T3 watcher count and `--dry-run`.
- `github-merge-rest-is-authoritative-blocked-is-not.md` saw the same error with every check green (#4362).

## Evidence (PR #7402, head a75fc4dd7, 2026-11-16)

- OBSERVED 15:42:32Z: the T3 notification said "All 8 required checks passed on a75fc4d".
- OBSERVED 15:43:33Z: `merge_pr.py --dry-run` returned "PR #7402 would be merged".
- OBSERVED 15:44:07Z: the real call failed with "the base branch policy prohibits the merge".
- OBSERVED 15:44:58Z: the ruleset listed 9 contexts. `get_pr_checks.py` showed 8 required rows.
- OBSERVED: `Run Python Tests` was not among those rows.
- NOT RECORDED: the `MissingRequiredChecks` value at 15:44:58Z was not printed.
- OBSERVED 15:45:13Z: auto-merge was armed on the full head SHA. The PR merged as 0b070c14b.
- INFERRED: the context reports late because the `test-result` job in `.github/workflows/pytest.yml` waits on 7 other jobs.
- INFERRED: the refusal came from the missing context, not from the #4362 case.

## Related

- `diagnosing-a-blocked-pr.md`
- `github-a-new-push-turns-off-auto-merge-armed-with-an-expected-head.md`
- `github-expected-head-sha-must-be-the-full-sha.md`
