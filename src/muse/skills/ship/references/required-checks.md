# Required Checks Gate Ship, Optional Checks Never Wait

Ship's GitHub pipeline check waits on the checks the base-branch ruleset
requires, and on nothing else. An optional check never holds the gate.

## Why

A plain `get_pr_checks.py --wait` polls until every check settles. Some
optional checks never settle on their own. A job in a GitHub environment with
required reviewers stays in `WAITING` until an owner approves it. With every
required check green, GitHub reports `mergeStateStatus: UNSTABLE`, and an
agent that waits on all checks stalls there.

## The command

```bash
python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request <number> \
  --wait --required-only --timeout-seconds 300
```

`--required-only` reads the ruleset, keeps only required checks, and makes
`--wait` stop once those settle.

PASS needs all three:

- Exit code 0.
- `Data.RequiredState == "SUCCESS"`.
- `Data.AllPassing == true`.

A PR with no checks is never green: `AllPassing: false` and
`RequiredState: UNKNOWN`. It exits 0 when the ruleset requires nothing, and 1
(or 7 under `--wait` inside the grace window) when the ruleset names a check.

## Edge cases

| Result | Meaning | Action |
|---|---|---|
| Exit 7 | Required checks still pending when the budget ran out | Re-run the same command. Keep `--timeout-seconds` at or below 570 |
| Exit 7 with `Data.DataSource == "rest"` | GraphQL is rate limited. REST cannot prove a pending check is optional, so pending checks outside the ruleset still hold the wait | Do not loop. Re-run once the GraphQL rate limit resets; report BLOCKED with the pending names if it has not |
| `RequiredState` is `UNKNOWN` | The ruleset or merge ref could not prove the required set | FAIL. Name the reason from `MergeStateWarning` or the error |
| Exit 3, ruleset read failed | The branch rules could not be read; the flag does not matter | Re-run once; a timeout or rate limit can clear. FAIL on a repeat and report the error. Dropping the flag does not help |
| Exit 3 under `--required-only`, REST fallback | GraphQL was rate limited and the ruleset lists no required checks | Re-run without `--required-only` and require `AllPassing == true` |
| Exit 0, `Data.Checks` is empty, `RequiredState` is `SUCCESS` | The ruleset requires no checks; the wait settles at once. Classic branch protection, which the ruleset lookup cannot see, may still require one | Re-run without `--required-only` and require `AllPassing == true` |
| A required check is missing | The ruleset names a check that never reported | FAIL after the grace window. Do not wait longer |

The REST fallback row and the empty `Data.Checks` row matter in a consumer repo
with no ruleset. There, every
check is the gate, because nothing else says which ones matter.

## What an optional check is

Ship does not judge optional checks. The github skill's
`references/required-vs-optional-checks.md` owns the policy: what counts as
optional, how to treat an advisory failure, and how to run a gated smoke
locally.
