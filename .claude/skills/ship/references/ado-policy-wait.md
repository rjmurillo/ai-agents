# ADO first-PR policy wait

`/ship` Process step 4 runs this block for `host=ado` after `az repos pr create` returns `pullRequestId` as `pr_id`.
It waits until the PR has at least one applied blocking build evaluation and none is `queued` or `running`.
A `notApplicable` row does not count, because the evaluation skips it too.
ADO may list no evaluation for a moment after creation, so an empty list keeps waiting.

The total wait is 30 minutes.
One call returns within 8 minutes, so an agent shell tool cap (often 10 minutes) cannot kill it.
Before the first call, compute the deadline once with `echo $(( $(date +%s) + 1800 ))`.
Pass that number as `ADO_WAIT_DEADLINE` on every call.

```bash
deadline="${ADO_WAIT_DEADLINE:?set ADO_WAIT_DEADLINE once to the epoch second 30 minutes from the first call}"
call_end=$(( $(date +%s) + 480 ))
while :; do
  statuses="$(az repos pr policy list --id "$pr_id" \
    --query "[?configuration.isBlocking && configuration.isEnabled && configuration.type.displayName=='Build'].status" \
    --output tsv)" || exit 3
  total=0
  pending=0
  while read -r status; do
    case "$status" in ""|notApplicable) continue ;; esac
    total=$((total + 1))
    case "$status" in queued|running) pending=$((pending + 1)) ;; esac
  done <<< "$statuses"
  if [ "$total" -gt 0 ] && [ "$pending" -eq 0 ]; then
    exit 0
  fi
  now=$(date +%s)
  if [ "$now" -ge "$deadline" ]; then
    echo "FAIL: after 30 minutes, $total blocking build evaluations exist and $pending are queued or running" >&2
    exit 1
  fi
  if [ "$now" -ge "$call_end" ]; then
    echo "WAITING: $pending of $total still queued or running; run this block again with the same ADO_WAIT_DEADLINE" >&2
    exit 75
  fi
  sleep 30
done
```

## Exit codes

| Exit | Meaning | Next step |
|---|---|---|
| 0 | At least one applied blocking build evaluation exists, and none is `queued` or `running` | Run the pre-flight check 1 ADO policy evaluation with the same `pr_id` |
| 1 | The 30-minute deadline passed | `DEFERRED->FAIL` |
| 3 | An `az` query failed | `DEFERRED->FAIL`, report the `az` stderr |
| 75 | Still waiting, not a result | Run the same block again with the same `ADO_WAIT_DEADLINE` |

A build policy with a manual trigger stays `queued` until someone queues it.
It surfaces as the 30-minute timeout.
Queue it with `az repos pr policy queue --id "$pr_id" --evaluation-id <id>`, or name it in the report.
