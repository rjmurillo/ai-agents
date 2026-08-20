---
name: pr-autofix
description: Fix PRs autonomously. Triage open PRs by tier, address thread feedback, fix CI failures, and enable auto-merge when the 4-condition Ready-to-Merge gate passes.
argument-hint: '[pull-request|mode]'
allowed-tools: Bash, Read, Edit, Write, Skill
size-exception: true
user-invocable: true
---

<!-- # taste-lint: ignore file-size, this command is one end-to-end PR workflow; splitting it would hide required lease and mutation gates from the agent. -->

# /pr-autofix

<!--
size-exception rationale (Issue #4016).

What the check wants: the command_size validator blocks a command over 200 lines
and tells you to convert it to a skill.

Why the idiomatic fix does not apply: this command carries the entire Ready-to-Merge
protocol in one file by design ("Nothing outside it is needed to run the command").
The 301-line body includes the tier ladder, Ready-to-Merge gate definition,
thread-lifecycle state machine, and CI-failure triage procedure. Splitting these
into a skill or references/ requires changing how the command is invoked and loaded,
which is a structural change that must be measured against the eval harness before
shipping (Issue #3953 doctrine). Until that measurement is done, the exception is
the safer choice over unmeasured content removal.
Preserved invariant: One loaded workflow owns lease, mutation safety, live-state revalidation, and merge readiness.
Behavioral tests: `tests/test_pr_autofix_late_live_state_gate.py`, `tests/test_pr_autofix_force_push_lease.py`, `tests/test_pr_autofix_worktree_identity.py`, `tests/skills/pr-autofix/test_check_pr_round_cap.py`
Review trigger: Revisit when a measured split keeps those tests green and Ready-to-Merge behavior unchanged.
vendor-portability: upstream-only. Test paths reference rjmurillo/ai-agents contributor fixtures; installed plugin consumers do not have these files.
-->

Autonomous PR monitor and fixer. This file carries the whole protocol,
including the Ready-to-Merge definition below. Nothing outside it is needed
to run the command.

## Triggers

| Trigger phrase | Operation |
|----------------|-----------|
| `pr-autofix` | Triage all open PRs by tier and act |
| `autofix this pr` | Single-PR mode on the current branch's open PR |
| `monitor open prs` | Periodic triage without merging |
| `auto-merge ready prs` | Tier 1 only: enable auto-merge on land-ready PRs |
| `address pr feedback` | Tier 3/4 only: walk thread lifecycle |

## Process

Three phases. Tier-based dispatch decides which actions apply per PR.

### Phase 1: Triage

Run `test_pr_merge_ready.py` for every open PR. Classify each into a tier (T1-T5) using the table below. Sort the queue by tier ascending.

### Phase 2: Act per tier

Walk the queue. For each PR, apply the tier's action set. T1 first (land-ready), then T2 (CI fix), then T3/T4 (threads), then T5 (bot).

**Per-PR live-state gate (BLOCKING, issue #2455).** Before any action runs on a PR (any tier: arming auto-merge, pushing a CI fix, posting a thread reply), call `check_pr_live_state.py` and branch on the JSON envelope `Data.action` field. The session-start triage snapshot is stale by the time the walk reaches each row in a repo with heavy merge automation, and the consequences of acting on a stale row are concrete: armed auto-merge on a redundant PR, conflict merges into a closed branch, duplicate logic landed twice.

```bash
# One outer fetch covers all per-PR calls; --skip-fetch keeps the loop cheap.
git fetch --quiet origin "+refs/heads/main:refs/remotes/origin/main"
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \
    "${COPILOT_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "$repo_root/.claude" \
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
  printf '%s\n' ".claude/skills/github/scripts/pr"
}
SCRIPTS_DIR="$(resolve_pr_scripts_dir)"

# late-live-state-guard:start
# lease-renewal:start
LEASE_RENEW_PID=""
LEASE_RENEW_FAILURE_FILE=""
LEASE_RENEW_INTERVAL_SECONDS="${LEASE_RENEWAL_INTERVAL_SECONDS:-300}"
LEASE_CLEANUP_DONE=0

renew_lease_once() {
    python3 "$SCRIPTS_DIR/pr_autofix_lease.py" renew \
        --pull-request "$PR" --session "$SESSION_ID" --output-format json >/dev/null
}

stop_lease_renewal() {
    if [ -z "$LEASE_RENEW_PID" ]; then
        return 0
    fi
    kill -- "-$LEASE_RENEW_PID" 2>/dev/null || true
    kill "$LEASE_RENEW_PID" 2>/dev/null || true
    wait "$LEASE_RENEW_PID" 2>/dev/null || true
    LEASE_RENEW_PID=""
}

lease_renewal_failed() {
    [ -n "$LEASE_RENEW_FAILURE_FILE" ] && [ -s "$LEASE_RENEW_FAILURE_FILE" ]
}

start_lease_renewal() {
    stop_lease_renewal
    LEASE_CLEANUP_DONE=0
    LEASE_RENEW_INTERVAL_SECONDS="${LEASE_RENEWAL_INTERVAL_SECONDS:-300}"
    LEASE_RENEW_FAILURE_FILE="$(mktemp)"
    (
        current_child=""
        stop_current_child() {
            if [ -n "$current_child" ]; then
                kill "$current_child" 2>/dev/null || true
                wait "$current_child" 2>/dev/null || true
            fi
        }
        trap stop_current_child EXIT INT TERM
        while true; do
            sleep "$LEASE_RENEW_INTERVAL_SECONDS" &
            current_child=$!
            wait "$current_child" || break
            current_child=""
            renew_lease_once >/dev/null &
            current_child=$!
            if ! wait "$current_child"; then
                printf '%s\n' "renewal failed while holding the lease" > "$LEASE_RENEW_FAILURE_FILE"
                break
            fi
            current_child=""
        done
    ) &
    LEASE_RENEW_PID=$!
    trap cleanup_pr_autofix EXIT
    trap 'cleanup_pr_autofix; exit 130' INT
    trap 'cleanup_pr_autofix; exit 143' TERM
}

cleanup_pr_autofix() {
    if [ "$LEASE_CLEANUP_DONE" -eq 1 ]; then
        return 0
    fi
    LEASE_CLEANUP_DONE=1
    stop_lease_renewal
    python3 "$SCRIPTS_DIR/pr_autofix_lease.py" release \
        --pull-request "$PR" --session "$SESSION_ID" --output-format json || true
}

release_pr_lease() {
    cleanup_pr_autofix
}

prepare_lease_for_mutation() {
    stop_lease_renewal
    if ! renew_lease_once; then
        printf '%s\n' "renewal failed before mutation" > "$LEASE_RENEW_FAILURE_FILE"
        return 1
    fi
    start_lease_renewal
}

stop_mutation_group() {
    local mutation_pid=$1 stop_attempt
    kill -TERM -- "-$mutation_pid" 2>/dev/null || true
    for stop_attempt in 1 2 3 4 5 6 7 8 9 10; do
        if ! kill -0 -- "-$mutation_pid" 2>/dev/null; then
            break
        fi
        sleep 0.05
    done
    kill -KILL -- "-$mutation_pid" 2>/dev/null || true
}

run_mutation_with_lease_monitor() {
    local mutation_pid mutation_pgid mutation_rc mutation_state start_attempt
    python3 -c \
        'import errno, os, sys
try:
    os.setsid()
except OSError as exc:
    if exc.errno != errno.EPERM or os.getpgrp() != os.getpid():
        raise
os.execvp(sys.argv[1], sys.argv[1:])' \
        "$@" &
    mutation_pid=$!
    mutation_pgid=""
    for start_attempt in 1 2 3 4 5 6 7 8 9 10; do
        mutation_pgid=$(ps -o pgid= -p "$mutation_pid" 2>/dev/null | tr -d ' ')
        if [ "$mutation_pgid" = "$mutation_pid" ]; then
            break
        fi
        mutation_state=$(ps -o stat= -p "$mutation_pid" 2>/dev/null | tr -d ' ')
        if ! kill -0 "$mutation_pid" 2>/dev/null || [ "${mutation_state#Z}" != "$mutation_state" ]; then
            if wait "$mutation_pid"; then
                mutation_rc=0
            else
                mutation_rc=$?
            fi
            if lease_renewal_failed; then
                stop_mutation_group "$mutation_pid"
                echo "Mutation completed as lease ownership was lost for #$PR"
                cleanup_pr_autofix
                return 75
            fi
            stop_mutation_group "$mutation_pid"
            return "$mutation_rc"
        fi
        sleep 0.01
    done
    if [ "$mutation_pgid" != "$mutation_pid" ]; then
        mutation_state=$(ps -o stat= -p "$mutation_pid" 2>/dev/null | tr -d ' ')
        if ! kill -0 "$mutation_pid" 2>/dev/null || [ "${mutation_state#Z}" != "$mutation_state" ]; then
            if wait "$mutation_pid"; then
                mutation_rc=0
            else
                mutation_rc=$?
            fi
            if lease_renewal_failed; then
                stop_mutation_group "$mutation_pid"
                echo "Mutation completed as lease ownership was lost for #$PR"
                cleanup_pr_autofix
                return 75
            fi
            stop_mutation_group "$mutation_pid"
            return "$mutation_rc"
        fi
        kill "$mutation_pid" 2>/dev/null || true
        wait "$mutation_pid" 2>/dev/null || true
        echo "Stopping mutation for #$PR: process group setup failed"
        cleanup_pr_autofix
        return 75
    fi
    if lease_renewal_failed; then
        stop_mutation_group "$mutation_pid"
        wait "$mutation_pid" 2>/dev/null || true
        echo "Stopping mutation for #$PR: lease ownership lost"
        cleanup_pr_autofix
        return 75
    fi
    while kill -0 "$mutation_pid" 2>/dev/null; do
        if lease_renewal_failed; then
            sleep 0.02
            mutation_state=$(ps -o stat= -p "$mutation_pid" 2>/dev/null | tr -d ' ')
            if ! kill -0 "$mutation_pid" 2>/dev/null || [ "${mutation_state#Z}" != "$mutation_state" ]; then
                stop_mutation_group "$mutation_pid"
                if wait "$mutation_pid"; then
                    mutation_rc=0
                else
                    mutation_rc=$?
                fi
                echo "Mutation completed as lease ownership was lost for #$PR"
                cleanup_pr_autofix
                return 75
            fi
            stop_mutation_group "$mutation_pid"
            wait "$mutation_pid" 2>/dev/null || true
            echo "Stopping mutation for #$PR: lease ownership lost"
            cleanup_pr_autofix
            return 75
        fi
        sleep 0.05
    done
    if wait "$mutation_pid"; then
        mutation_rc=0
    else
        mutation_rc=$?
    fi
    if lease_renewal_failed; then
        stop_mutation_group "$mutation_pid"
        echo "Mutation completed as lease ownership was lost for #$PR"
        cleanup_pr_autofix
        return 75
    fi
    stop_mutation_group "$mutation_pid"
    return "$mutation_rc"
}
# lease-renewal:end

recheck_pr_live_state() {
    local late_live late_rc late_action late_reason late_state late_head late_base
    if late_live=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" \
        --pull-request "$PR" --skip-fetch \
        --expected-head-sha "${EXPECTED_HEAD_SHA:-}" \
        --expected-base-ref "${EXPECTED_BASE_REF:-}" \
        --expected-base-sha "${EXPECTED_BASE_SHA:-}" \
        --output-format json); then
        late_rc=0
    else
        late_rc=$?
    fi

    late_action=$(printf '%s' "$late_live" | jq -r '.Data.action // empty' 2>/dev/null)
    if [ "$late_rc" -eq 0 ] && [ "$late_action" = "ACT" ]; then
        return 0
    fi

    late_reason=$(printf '%s' "$late_live" | jq -r '.Data.reason // "live-state check failed"' 2>/dev/null)
    late_state=$(printf '%s' "$late_live" | jq -r '.Data.state // "UNKNOWN"' 2>/dev/null)
    late_head=$(printf '%s' "$late_live" | jq -r '.Data.head_sha // "unknown"' 2>/dev/null)
    late_base=$(printf '%s' "$late_live" | jq -r '.Data.base_ref // "main"' 2>/dev/null)
    echo "Skipping mutation for #$PR: $late_reason"
    if [ "$late_state" = "MERGED" ]; then
        echo "Merged head SHA: $late_head"
        echo "Preserve unpushed commits or a net patch. Reapply them on a follow-up branch from current origin/$late_base."
    elif [ "$late_state" = "CLOSED" ]; then
        echo "Closed PR head SHA: $late_head"
        echo "Preserve unpushed commits or a net patch before leaving the old branch."
    fi
    cleanup_pr_autofix
    return 75
}

run_pr_mutation_if_live() {
    if lease_renewal_failed; then
        echo "Skipping mutation for #$PR: lease renewal failed"
        cleanup_pr_autofix
        return 75
    fi
    if ! prepare_lease_for_mutation; then
        echo "Skipping mutation for #$PR: lease renewal failed"
        cleanup_pr_autofix
        return 75
    fi
    if recheck_pr_live_state; then
        run_mutation_with_lease_monitor "$@"
        return $?
    fi
    return 75
}
# late-live-state-guard:end

# SESSION_ID must be set before the loop (e.g. from the session log or a uuid).
# Per PR, immediately before any per-tier action:

# Step 1: Acquire the branch-ownership lease (issue #3413, ADR-076 Phase 1).
# Exit 1 = SKIP. Branch on .Data.reason so a lease-store outage is surfaced as
# a distinct diagnostic instead of being silently misreported as contention
# (issue #4966 MEDIUM). .Data.held_by does not exist in the envelope; the
# machine-readable field is .Data.reason (held-by:<owner> or
# lease-store-unavailable).
LEASE=$(python3 "$SCRIPTS_DIR/pr_autofix_lease.py" acquire \
    --pull-request "$PR" --session "$SESSION_ID" --output-format json) || {
    LEASE_RC=$?
    if [ "$LEASE_RC" -eq 1 ]; then
        LEASE_REASON=$(echo "$LEASE" | jq -r '.Data.reason // "unknown"')
        case "$LEASE_REASON" in
            lease-store-unavailable)
                # Store unreachable: ownership is unknown and acquire fails
                # CLOSED (issue #4966). This is NOT contention. Surface a clear
                # diagnostic so a persistent outage cannot make every PR SKIP
                # forever with no alert; investigate the API/network path.
                echo "Lease store unreachable for #$PR (reason=$LEASE_REASON); ownership unknown, failing closed and skipping. Check GitHub API/network before retrying." >&2
                ;;
            held-by:*)
                echo "Lease held by ${LEASE_REASON#held-by:} for #$PR; skipping."
                ;;
            *)
                echo "Lease acquire returned SKIP for #$PR (reason=$LEASE_REASON); skipping."
                ;;
        esac
        continue
    fi
    echo "Lease acquire failed (exit $LEASE_RC) for #$PR; skipping to avoid racing."
    continue
}
start_lease_renewal

# Step 2: Live-state gate (BLOCKING, issue #2455).
LIVE=$(python3 "$SCRIPTS_DIR/check_pr_live_state.py" \
    --pull-request "$PR" --skip-fetch --output-format json)
ACTION=$(echo "$LIVE" | jq -r '.Data.action')
if [ "$ACTION" = "SKIP" ]; then
    REASON=$(echo "$LIVE" | jq -r '.Data.reason')
    echo "Skipping #$PR: $REASON"
    cleanup_pr_autofix
    # If Data.superseded_by_base.fully_superseded == true, recommend close
    # via the queue's close-handling path; do NOT push or merge.
    continue
fi
EXPECTED_HEAD_SHA=$(echo "$LIVE" | jq -r '.Data.head_sha // empty')
EXPECTED_BASE_REF=$(echo "$LIVE" | jq -r '.Data.base_ref // empty')
EXPECTED_BASE_SHA=$(echo "$LIVE" | jq -r '.Data.base_sha // empty')
if [ -z "$EXPECTED_HEAD_SHA" ] || [ -z "$EXPECTED_BASE_REF" ] || [ -z "$EXPECTED_BASE_SHA" ]; then
    echo "Cannot bind mutation to the live PR identity for #$PR; skipping."
    cleanup_pr_autofix
    continue
fi
# ACTION == "ACT": proceed with the tier's planned action set.

# tier-dispatch:start
# Step 2.5: Round-cap circuit breaker (BLOCKING for T3/T4, issue #5056).
# T3/T4 PRs iterate: post a fix, wait for CI or a bot review, repeat. Nothing
# capped how many times that loop could run, and prose caps have been
# ignored repeatedly (the documented failure mode, not a hypothetical one):
# PR #1887 ran 11+ bot review rounds over 46 hours wall clock before a human
# intervened (see the pr-1887-iteration-paradox retrospective in this repo's
# rjmurillo/ai-agents source, contributor-only); PRs #1965 and #1979 each ran
# 18 rounds (see the CI-FEEDBACK-SUBLOOP governance doc, same source, line
# 11). check_pr_round_cap.py records one round per call against a
# hidden marker comment on the PR (same storage pattern as
# pr_autofix_lease.py's ADR-076 lease) and returns Data.action=ESCALATE when
# either the round count or the wall-clock budget is exceeded. Call it once
# per pass through this loop for a T3/T4 PR, immediately after the tier is
# known, before any thread-lifecycle or CI-fix action.
# Tier comes from test_pr_merge_ready.py, the authoritative tier source;
# check_pr_live_state.py emits no tier field, so reading $LIVE here pins TIER
# at UNKNOWN. Computed once, also consumed by the auto-merge disarm gate below.
# Read `.Tier`, not `.Data.Tier`: unlike the github_core.output emitters,
# test_pr_merge_ready.py has no --output-format flag and prints its result
# dict directly (`print(json.dumps(result, indent=2))`), so there is no Data
# envelope to traverse.
# A pinned UNKNOWN breaks the two gates in OPPOSITE directions, so do not
# read it as "the gates turn off": this gate tests TIER = T3 or T4, which
# UNKNOWN never satisfies, so it goes inert; the disarm gate below tests
# TIER != T1, which UNKNOWN always satisfies, so it fires on every armed PR
# and strips auto-merge from genuine T1 PRs too.
# tests/commands/test_pr_autofix_field_contract.py checks every read in this
# file against its producer's real schema, and
# tests/commands/test_pr_autofix_tier_dispatch_runtime.py executes the block
# between the tier-dispatch markers under bash with fake producers, so the two
# gate directions below are asserted behavior rather than described behavior.
MERGE_READY=$(python3 "$SCRIPTS_DIR/test_pr_merge_ready.py" --pull-request "$PR" 2>/dev/null)
# Deliberately no 2>/dev/null on either jq below. The producer's stderr is
# suppressed above, so a jq parse error is the only signal an operator gets that
# the producer emitted something unreadable, and both guards below would
# otherwise skip the PR with no explanation. Adding the redirect here was tried
# and the runtime suite failed it by name; see the malformed-producer case.
TIER=$(printf '%s' "$MERGE_READY" | jq -r '.Tier // "UNKNOWN"')
# Captured once and read twice, because the tier alone does not say whether the
# evidence behind it was complete. classify_tier returns T1 on CanMerge, and
# CanMerge is `len(reasons) == 0` with fetched_pages_complete computed after it
# and never appended to reasons (test_pr_merge_ready.py, check_merge_readiness).
# So a fetch truncated at the pagination cap that happens to surface no
# unresolved thread and no failing required check classifies T1, which the
# producer's own docstring warns about: "a partial fetch that happens to find no
# failing checks is not evidence that no failing checks exist."
# This mattered only after the tier read above was fixed. While TIER was pinned
# at UNKNOWN, TIER != T1 held for every PR, so the disarm gate below stripped
# auto-merge from the truncated-fetch case by accident. Making T1 reachable
# removes that accident, so the exemption has to be earned rather than assumed.
# Anything other than the literal `true` denies the exemption: the real producer
# always emits the boolean, so healthy input is unaffected, and a missing or
# unreadable field is exactly the state that must not buy a merge.
PAGES_COMPLETE=$(printf '%s' "$MERGE_READY" | jq -r '.fetched_pages_complete // "unknown"')
# .claude/commands/pr-review-config.yaml already ANDs this field into its
# completion-gate criterion, so this is the same safety rule applied at the
# other place a merge can be armed, not a new policy.
# Fail closed on a tier the producer never declared. Without pipefail jq masks a
# producer failure, and the two failure shapes do not even agree with each other:
# empty stdout (crash, or unparseable JSON) leaves TIER empty, while a JSON error
# object leaves it UNKNOWN. Both skip the T3/T4 breaker below AND satisfy
# TIER != T1 in the disarm gate, so the loop would strip auto-merge and keep
# acting on a PR whose tier it never learned. Do not gate on exit status instead:
# test_pr_merge_ready.py exits 1 for any not-merge-ready PR, so T2 through T4 are
# legitimately non-zero.
# The accepted set is the producer's own, quoted verbatim from
# test_pr_merge_ready.py:1103, which classify_tier's docstring names as the
# range of its return value:
#   _TIER_ORDER = ("T1", "T2", "T3", "T4", "T5", "BEHIND", "BLOCKED", "DIRTY", "SKIP")
# The four beyond the T1-T5 ladder are real: SKIP for a draft, closed, or merged
# PR, and BEHIND/BLOCKED/DIRTY from the merge-state lookup. Listing only the
# ladder rejected those as producer failures and silently disabled the
# documented BEHIND and DIRTY handling.
# tests/commands/test_pr_autofix_tier_contract.py pins this list against the
# producer so the two cannot drift apart again.
# Recognized and actionable are two different questions, and collapsing them is
# what put SKIP on the acting path. The tier table below reads
# "| SKIP | Draft, merged, or closed | No action |", so SKIP terminates here.
# Letting it reach the disarm gate means TIER != T1 holds and auto-merge is
# stripped from a PR that went draft, merged, or closed after the live-state
# gate ran.
case "$TIER" in
    SKIP)
        echo "Tier SKIP for #$PR (draft, merged, or closed); no action."
        cleanup_pr_autofix
        continue
        ;;
    T1|T2|T3|T4|T5|BEHIND|BLOCKED|DIRTY) ;;
    *)
        echo "Cannot determine tier for #$PR (tier producer failed or emitted no tier); skipping."
        cleanup_pr_autofix
        continue
        ;;
esac
if [ "$TIER" = "T3" ] || [ "$TIER" = "T4" ]; then
    ROUND_CAP=$(python3 "$SCRIPTS_DIR/check_pr_round_cap.py" \
        --pull-request "$PR" --output-format json)
    ROUND_ACTION=$(echo "$ROUND_CAP" | jq -r '.Data.action // empty')
    if [ "$ROUND_ACTION" != "ACT" ]; then
        ROUND_REASON=$(echo "$ROUND_CAP" | jq -r '.Data.reason // "round-cap check failed"')
        echo "Stopping thread-fix loop for #$PR: $ROUND_REASON"
        # check_pr_round_cap.py already posted a human-readable PR comment
        # naming the round count, wall-clock elapsed, and both caps
        # (issue #5056 item 4: leave a note, do not just stop silently).
        # A human must review the remaining thread(s)/CI failure(s) directly.
        cleanup_pr_autofix
        continue
    fi
fi

# Step 3: Auto-merge disarm gate (BLOCKING, issue #3913).
# If the PR has auto-merge armed but is not T1-ready, a conflict refresh or CI
# fix push could immediately land a PR whose readiness was never explicitly
# verified in this session.  Disable auto-merge now, before any commit or push.
# TIER was computed at Step 2.5 (round-cap gate) above.
CTX=$(python3 "$SCRIPTS_DIR/get_pr_context.py" --pull-request "$PR" \
    --output-format json 2>/dev/null)
AUTO_MERGE=$(printf '%s' "$CTX" | jq -r '.Data.auto_merge_method // "null"' 2>/dev/null)
# Empty stdin or a jq parse error yields an empty string, not "null". Treating
# that as "armed" would fire the disarm path on no evidence, so skip instead.
if [ -z "$AUTO_MERGE" ]; then
    echo "Cannot read auto-merge state for #$PR (context fetch or parse failed); skipping."
    cleanup_pr_autofix
    continue
fi
# "Not provably T1" rather than "not T1": a T1 whose evidence came from a
# truncated fetch has not earned the exemption, so it disarms with the rest.
if [ "$TIER" = "T1" ] && [ "$PAGES_COMPLETE" = "true" ]; then
    TIER_TRUSTED_T1=yes
else
    TIER_TRUSTED_T1=no
fi
if [ "$AUTO_MERGE" != "null" ] && [ "$TIER_TRUSTED_T1" != "yes" ]; then
    if [ "$TIER" = "T1" ]; then
        echo "Auto-merge armed on #$PR and the tier is T1, but the merge-readiness fetch was incomplete (fetched_pages_complete=$PAGES_COMPLETE); disabling before acting."
    else
        echo "Auto-merge armed on non-T1 PR #$PR (method: $AUTO_MERGE); disabling before acting."
    fi
    if run_pr_mutation_if_live \
        python3 "$SCRIPTS_DIR/set_pr_auto_merge.py" \
        --pull-request "$PR" --disable --output-format json; then
        :
    else
        MUTATION_RC=$?
        if [ "$MUTATION_RC" -ne 75 ]; then
            echo "Failed to disable auto-merge on #$PR; skipping to avoid unguarded merge."
        fi
        cleanup_pr_autofix
        continue
    fi
fi
# tier-dispatch:end

# Release the lease after all per-PR work (push + post-push CI wait + merge).
# Pattern:
#   ... (tier actions) ...
#   cleanup_pr_autofix
```

Lease SKIP verdicts: when exit code is 1 the lease was not acquired. Branch on
the `reason` field: `held-by:<owner>` means another autofix loop holds the
lease (real contention), and `lease-store-unavailable` means the lease store
was unreachable so ownership could not be verified and acquire failed CLOSED
(issue #4966). In both cases do NOT push, do NOT arm auto-merge, do NOT post
threads. A persistent `lease-store-unavailable` is an infrastructure signal,
not contention: investigate the GitHub API or network path.

LIVE-STATE SKIP verdicts are binding: do NOT push commits, do NOT arm
auto-merge, do NOT run `merge_pr.py` on a PR this gate classifies as SKIP.
The verdict's `reason` field names the cause (merged, closed, draft, fully
superseded by base) for the autofix log. An ACT verdict only proves the PR is
still actionable; the four-condition Ready-to-Merge gate still applies before
any merge.

Every command that mutates a branch or PR MUST run through
`run_pr_mutation_if_live`. This includes base fetches, merges, rebases, pushes,
auto-merge changes, and direct merges. The wrapper performs a new GitHub query
immediately before the command and compares the result with the head and base
identity captured by the current readiness cycle. A gate from an earlier review
or validation phase is stale. Exit 75 means the wrapper logged the live-state skip
and released the lease. Other nonzero exits come from the mutation command and
retain their existing error handling.

### Phase 3: Verify and gate

After all queued actions, re-check the 4-condition Ready-to-Merge gate. Enable
auto-merge only when all four conditions hold. Release each PR's lease after its
merge command (or skip) completes:

```bash
python3 "$SCRIPTS_DIR/run_completion_gate.py" \
    --pull-request "$PR" \
    --json \
    --evidence-path ".agents/pr-comments/PR-$PR/gate-evidence.json"

cleanup_pr_autofix
```

Dispatcher exit contract (CWE-829 trust boundary, Issue #5072): exit 0 all criteria passed; exit 1 a criterion failed; exit 2 config error INCLUDING a `pr-review-config.yaml` that diverges from or is absent at the trusted ref (`origin/main`); exit 3 trust verification impossible (no git work tree, trusted ref missing or not remote-tracking). A trust halt (stderr starts with `HALT: completion-gate config`, statuses diverged/missing-base, and every exit 3) occurs before any dispatch, so NO criterion command was executed. Other exit-2 config errors (a malformed later criterion, an evidence-write failure) can fire mid- or post-dispatch, so earlier criterion commands may already have run; treat exit 2 as "verdict unusable", not "nothing happened". Neither exit is transient: do NOT retry, do NOT treat exit 3 as a passing external outage, and do NOT pass `--approve-untrusted-config` autonomously. The flag only applies to a trust-halt exit 2 (diverged or missing-at-base); an exit-3 halt cannot be overridden at all. Surface the stderr diff to a human and skip the PR.

## Workflow

1. Triage all open PRs into tiers T1-T5 using `test_pr_merge_ready.py`.
2. Process T1 (land-ready) first, then T2 (CI fix), T3/T4 (threads), T5 (bot).
3. **Before acting on any PR, call `check_pr_live_state.py`** and skip the row when it returns `Data.action=SKIP` (issue #2455). The triage snapshot from step 1 goes stale fast in a repo with heavy merge automation; the gate catches PRs merged/closed mid-walk and PRs whose diff is already on `main` via a sibling consolidated PR.
4. **Before any branch mutation, acquire the branch lease** via `pr_autofix_lease.py acquire` (issue #3413). A SKIP result means another session holds the branch; exit before creating a worktree or pushing. Release the lease via `pr_autofix_lease.py release` when done or on error. The lease is advisory; the Force-Push Safety SHA gate is the hard backstop. For any remote mutation that can outlive the final pre-mutation poll, keep renewal supervision active through the whole critical section and re-verify lease ownership immediately before the mutation. If renewal ownership is lost, block the mutation and release the lease before continuing.
5. **On every pass through a T3/T4 PR, call `check_pr_round_cap.py`** and stop working that PR when it returns `Data.action=ESCALATE` (issue #5056). It caps how many fix/review rounds and how many wall-clock hours the thread-fix loop may run before it hands the PR back to a human; PR #1887 ran 11+ rounds over 46 hours with no cap in place. The script posts the escalation reason as a PR comment itself; the agent does not need to.
6. For each PR that the live-state gate and round-cap gate cleared: address review threads, fix CI failures using known patterns, then choose the merge path from the four-condition gate.

## Ready-to-Merge Definition (4 conditions, ALL required)

1. Branch up to date with `main` (`mergeStateStatus` not `BEHIND`).
2. All required checks pass.
3. All conversations addressed: READ, TRIAGED, SOLVED (if Blocking), REPLIED with course of action, RESOLVED.
4. `mergeStateStatus == CLEAN` (or `UNSTABLE` with documented non-required failures).

`CanMerge=True` from `test_pr_merge_ready.py` alone is insufficient. Cross-check all four conditions.

**Checkout ownership for the readiness helper (issue #2443)**: when a PR modifies files under `.claude/skills/github/scripts/pr/`, run `test_pr_merge_ready.py` from that PR's own worktree, not from a shared checkout. A shared checkout runs whatever helper version is on its disk, which may predate the branch's fix and yield a stale `CanMerge` verdict. The readiness output records a `ScriptCommit` field with the helper revision that produced the verdict; if it does not match the PR branch's helper commit, re-run from the PR worktree before trusting the result.

## Tier Definitions

The `Tier` field in `test_pr_merge_ready.py` output is the authoritative
classifier.  Pass `--is-bot` when the PR author is a bot.

### Work-needed tiers

| Tier | Criteria | Action |
|------|----------|--------|
| T1 | `CanMerge=true` (`CLEAN` or `UNSTABLE` with all non-required failures disposed) | Merge via the appropriate merge path |
| T2 | CI failures only (required or undisposed non-required), no threads | Fix CI, verify required checks pass |
| T3 | Threads only (CI passing) | Walk full thread lifecycle, then merge |
| T4 | Both CI failures + threads | Fix CI first, then lifecycle threads |
| T5 | Bot PR with any failure or threads | Handle individually |

### Merge-path states (not work tiers)

| State | Criteria | Action |
|-------|----------|--------|
| BEHIND | `MergeStateStatus == "BEHIND"` | Update branch against main, then reclassify |
| BLOCKED | `MergeStateStatus == "BLOCKED"` (branch protection, pending reviews) | Wait for external gate (review approval, etc.) |
| DIRTY | `MergeStateStatus == "DIRTY"` (merge conflict) | Resolve conflict via the merge-resolver agent, then reclassify |
| SKIP | Draft, merged, or closed | No action |

## Fix Patterns

- **CI-failure triage step 1 (issue #5073)**: for every failing check name, run `triage_red_check.py --check-name "<name>" --pull-request {pr}` before any log reading or local investigation. `RED_ON_MAIN` (exit 1) means the failure is inherited from main: cite the `EvidenceUrl` main run, do not debug the PR, and re-run checks after main recovers. `GREEN_ON_MAIN` (exit 0) means the PR introduced it: proceed to logs. `UNKNOWN` (exit 3) is a probe failure, never evidence of green.
- **PR description mismatch**: Remove file references not in the diff (use GitHub API to PATCH body).
- **Branch behind main**: Run each base refresh command through the late live-state wrapper:

  ```bash
  run_pr_mutation_if_live git fetch origin "$BASE"
  run_pr_mutation_if_live git merge origin/"$BASE" --no-edit
  run_pr_mutation_if_live git push origin "$BRANCH"
  ```

- **Stale merge-state cache**: `test_pr_merge_ready.py` sets `StaleDirtySuspected=true` when GitHub reports `mergeable == "CONFLICTING"` or `mergeStateStatus == "DIRTY"`. This is advisory, not authoritative. A PR can merge or close during the review-fix cycle; acting on an earlier ACT result triggers a conflict merge into a deleted branch. In a worktree, use `run_pr_mutation_if_live git fetch origin "$BASE"`, then `git merge-base --is-ancestor "origin/$BASE" HEAD` (exit 0 = ancestor) and a guarded `run_pr_mutation_if_live git merge --no-commit --no-ff "origin/$BASE"` trial merge. Both clean means the conflict is stale. Disable existing auto-merge through the wrapper and verify `autoMergeRequest` is null before the final guarded merge and push (issue #3913). A failing trial merge means the conflict is real: resolve via merge-resolver agent. Evidence required: both live-state verdicts, the ancestry exit code, and the trial-merge result. See doc Stale merge-state cache section (issue #2368).
- **Stale CI check**: Push fresh commit to re-trigger; avoid `--no-verify` if possible.
- **Bot review threads**: Read, triage per Thread Severity, reply with disposition, resolve via `add_pr_review_thread_reply.py --resolve`.
- **Armed auto-merge + final thread**: `add_pr_review_thread_reply.py --resolve` posts the reply, disables armed auto-merge when that thread is the final unresolved one, then resolves the thread. If the guard cannot prove the unresolved count, the script exits 3 after posting the reply and leaves the thread unresolved so GitHub cannot merge before the completion gate.
- **Session validation failure**: Hand-edit the log to satisfy the session-log schema, then re-validate it.

## Force-Push Safety

Before any push: verify `git rev-parse "refs/heads/$BRANCH"` matches the PR's expected `head.sha` from `get_pr_context.py`. (Prefer `rev-parse` over plain-file reads of `.git/refs/heads/<branch>`: rev-parse resolves loose refs AND refs that have been compacted into `.git/packed-refs`; a plain-file read returns "missing ref" when the branch lives only in `packed-refs`.) If the local ref points to a bootstrap/sandbox commit, STOP. Investigate corruption before pushing. Force-push only with explicit user authorization, using SHA-pinned source with quoted refspec:

```bash
SHA="<known-good-sha>"
BRANCH="<branch-name>"
# The head.sha you already read from get_pr_context.py before starting work.
EXPECTED_REMOTE_SHA="<observed-head-sha>"
run_pr_mutation_if_live env FORCE_PUSH_OK=1 git push origin "${SHA}:refs/heads/${BRANCH}" \
  --force-with-lease="refs/heads/${BRANCH}:${EXPECTED_REMOTE_SHA}"
```

`FORCE_PUSH_OK=1` is required, not optional. A pre-push hook cannot read argv,
so the repository's non-fast-forward guard sees a rewrite and exits 1 whether
or not a lease is pinned. The variable is the one escape the force-push rule
sanctions for a pinned lease, and it narrows that single guard while every
other pre-push job runs (issue #4293). This repository's safe-push helper sets
it for you, so prefer that helper over the raw command.

Pin the lease to an explicit SHA; never use bare `--force-with-lease` here.
Bare `--force-with-lease` takes its expected value from
`refs/remotes/origin/$BRANCH`, and any concurrent `git fetch`, including one run
by a sibling agent in the same checkout, silently advances that ref to the other
agent's commit. The lease then passes and the push destroys their work. Measured
on a two-clone repro: with a fetch between the two pushes the bare form
overwrote a sibling's commit, while
`--force-with-lease=refs/heads/$BRANCH:<observed-sha>` rejected the identical
push with `stale info` (issues #3653, #3413). The `rev-parse` check above is a
separate read and cannot close the window between check and push; only the
pinned lease is atomic.

Quote every variable expansion. The shell does not treat `:` specially in a refspec; the real reason to quote is that branch names can contain characters the shell DOES treat specially (`*`, `?`, `[`, whitespace), and unquoted `$BRANCH` will word-split or glob on those.

## Scripts

```bash
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \
    "${COPILOT_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "$repo_root/.claude" \
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
  printf '%s\n' ".claude/skills/github/scripts/pr"
}
SCRIPTS_DIR="$(resolve_pr_scripts_dir)"

# Check merge readiness
python3 "$SCRIPTS_DIR/test_pr_merge_ready.py" --pull-request {pr}

# Per-PR live-state gate (BLOCKING per Phase 2; issue #2455). Returns
# exit 0 + Data.action=ACT when safe to proceed, exit 1 + Data.action=SKIP when
# the PR is merged/closed/draft or fully superseded by base.
python3 "$SCRIPTS_DIR/check_pr_live_state.py" --pull-request {pr} --skip-fetch --output-format json

# Round-cap circuit breaker (BLOCKING for T3/T4 per Phase 2; issue #5056).
# Records one round against a hidden marker comment and returns exit 0 +
# Data.action=ACT when both the round-count and wall-clock caps hold, exit 1
# + Data.action=ESCALATE when either is exceeded. Defaults: 5 rounds / 4
# hours, each overridable via --max-rounds/--max-hours or
# $PR_AUTOFIX_MAX_ROUNDS/$PR_AUTOFIX_MAX_ROUND_HOURS.
python3 "$SCRIPTS_DIR/check_pr_round_cap.py" --pull-request {pr} --output-format json

# CI-failure triage step 1 (BLOCKING, issue #5073): before reading any log or
# starting any local investigation, ask whether the same check is red on
# origin/main. Exit 0 = green on main (the PR introduced it; investigate the
# PR). Exit 1 = red on main (inherited; cite Data.EvidenceUrl and fix or wait
# out main instead of debugging the PR). Exit 3 = cannot determine (probe
# failure is not absence; never treat UNKNOWN as green).
python3 "$SCRIPTS_DIR/triage_red_check.py" --check-name "<failing check name>" --pull-request {pr}

# Get CI check logs (step 2, only when the check is green on main)
python3 "$SCRIPTS_DIR/get_pr_checks.py" --pull-request {pr} | \
  python3 "$SCRIPTS_DIR/get_pr_check_logs.py" --pull-request {pr} --checks-input -

# CLEAN path: try auto-merge only when there is pending branch-protection work to wait on.
# If GitHub rejects an already-CLEAN PR with "clean status", use the printed direct-merge fallback.
run_pr_mutation_if_live python3 "$SCRIPTS_DIR/set_pr_auto_merge.py" --pull-request {pr} --enable --merge-method SQUASH

# Direct merge: already-CLEAN fallback or UNSTABLE state with documented non-required failures.
run_pr_mutation_if_live python3 "$SCRIPTS_DIR/merge_pr.py" --pull-request {pr} --strategy squash
```

### Merge path by `mergeStateStatus`

GitHub refuses auto-merge for `UNSTABLE` PRs (issue #2439) and may also reject an already-`CLEAN` PR because there is nothing left to wait on (issue #2450). Pick the path that matches the state:

| `mergeStateStatus` | Path | Script |
|---|---|---|
| `CLEAN` | Auto-merge when waiting is useful; direct merge if GitHub returns the already-clean rejection | Guard `set_pr_auto_merge.py --enable`, then guard the `merge_pr.py --strategy squash` fallback |
| `UNSTABLE` with documented non-required failures | Direct merge (immediate) | Guard `merge_pr.py --strategy squash` |
| `BEHIND` | Update branch first, then re-classify | Guard the fetch, merge, and push separately |
| `DIRTY`/`CONFLICTING` | See Stale merge-state cache pattern below | merge-resolver agent if real conflict |

`set_pr_auto_merge.py` detects the `UNSTABLE` and already-`CLEAN` rejections from GitHub's GraphQL API and emits the direct-merge fallback command in its error output (exit 3) so the operator never has to translate the generic "GraphQL request failed" message themselves.

### Merge-check exit codes: `test_pr_merged.py`

As of issue #2308, `test_pr_merged.py` exits **0** on any successful query
and reports merge state in the JSON `merged` field. This makes the script
behave like every other shell-friendly probe: exit 0 means "I answered your
question". Branch on the JSON, not the exit code.

Earlier history: the script used to exit **100** when the PR was merged
(Skill-PR-Review-007). Treating 100 as a failure caused wasted polling loops
on PRs #2240, #2269 (#2277), and made successful merge verification look
failed on PR #2289 (#2308).

When invoking from autofix code:

```bash
PR_NUMBER="123"
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \
    "${COPILOT_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "$repo_root/.claude" \
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
  printf '%s\n' ".claude/skills/github/scripts/pr"
}
SCRIPTS_DIR="$(resolve_pr_scripts_dir)"
python3 "$SCRIPTS_DIR/test_pr_merged.py" --pull-request "$PR_NUMBER" | jq -e '.merged == true'
```

To restore the legacy skip-review sentinel (only for callers that already
encoded "100 = merged"):

```bash
PR_NUMBER="123"
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \
    "${COPILOT_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "$repo_root/.claude" \
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
  printf '%s\n' ".claude/skills/github/scripts/pr"
}
SCRIPTS_DIR="$(resolve_pr_scripts_dir)"
python3 "$SCRIPTS_DIR/test_pr_merged.py" --pull-request "$PR_NUMBER" --exit-100-on-merged
```

The legacy `--exit-zero-on-merged` flag (from #2277) still parses as a no-op
for backward compatibility.

## Completion Gate

Run after all threads resolved and CI passes:

```bash
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \
    "${COPILOT_PLUGIN_ROOT:-}" \
    "${CLAUDE_PLUGIN_ROOT:-}" \
    "$repo_root/.claude" \
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \
    "${HOME:-}/.copilot/installed-plugins"/*/project-toolkit \
    "${HOME:-}/.claude/plugins/cache"/*/project-toolkit; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
  printf '%s\n' ".claude/skills/github/scripts/pr"
}
SCRIPTS_DIR="$(resolve_pr_scripts_dir)"
CONFIG_PATH="${PR_REVIEW_CONFIG_PATH:-.claude/commands/pr-review-config.yaml}"
python3 "$SCRIPTS_DIR/run_completion_gate.py" \
  --config "$CONFIG_PATH" \
  --pull-request {pr} --json
```

The dispatcher enforces the Issue #5072 trust boundary before dispatching anything: exit 2 also means the config diverges from or is absent at `origin/main`, and exit 3 means trust verification was impossible; in both cases no criterion command ran and the failure is not transient. `--approve-untrusted-config` requires a human who has read the surfaced diff and applies only to exit 2; an exit-3 halt (verification impossible) cannot be overridden.

## Verification

Per PR processed:

- [ ] Lease acquired before per-PR action (issue #3413): `pr_autofix_lease.py acquire --pull-request $PR --session $SESSION_ID`. Exit 1 = SKIP (reason `held-by:<owner>` is contention; reason `lease-store-unavailable` is a store outage that fails CLOSED, issue #4966); exit 0 = ACT. Lease released after PR work completes or on live-state SKIP.
- [ ] Tier classification recorded (T1-T5).
- [ ] Round-cap circuit breaker ran on every pass through a T3/T4 PR, immediately after the tier was known (issue #5056): `check_pr_round_cap.py --pull-request $PR --output-format json`. `Data.action=ACT` recorded and work continued; `Data.action=ESCALATE` stopped the thread-fix loop for that PR (round cap or wall-clock budget exceeded) and the script's own PR comment carries the reason, so nothing further was posted by the agent.
- [ ] Branch lease acquired via `pr_autofix_lease.py acquire` before any branch mutation (issue #3413). SKIP result caused early exit; ACT result recorded with `base_sha`.
- [ ] Remote mutations stayed under renewal supervision and were re-verified immediately before the mutation; if renewal ownership was lost, the mutation was blocked and the lease was released first.
- [ ] Per-PR live-state gate ran immediately before the tier's action (issue #2455): `check_pr_live_state.py --pull-request $PR --skip-fetch --output-format json`. Verdict `Data.action=ACT` recorded; `Data.action=SKIP` aborted the action and recorded the reason (merged, closed, draft, or fully superseded by base).
- [ ] Auto-merge disarm ran after live-state ACT on any non-T1 PR (issue #3913): `auto_merge_method` was null or `set_pr_auto_merge.py --disable` succeeded and returned `AutoMergeEnabled: false` before any push.
- [ ] Live-state gate re-ran immediately before any base refresh or conflict resolution (issue #4349): stale gate result from the start of the session is not sufficient; the PR can merge mid-cycle.
- [ ] Every base refresh, rebase, push, auto-merge change, and direct merge ran through `run_pr_mutation_if_live` immediately before mutation (issue #4349).
- [ ] Late mutation checks matched the head SHA, base ref, and base SHA captured by the current readiness cycle; any mismatch stopped mutation and restarted readiness checks.
- [ ] When `StaleDirtySuspected=true`: `set_pr_auto_merge.py disable` ran and `autoMergeRequest` confirmed null before any base-ref refresh push (issue #3913).
- [ ] CI-failure triage step 1 ran before any log reading (T2/T4 only, issue #5073): `triage_red_check.py --check-name "<name>"` verdict recorded per failing check; RED_ON_MAIN failures were attributed to main with the EvidenceUrl, not investigated on the PR.
- [ ] All required CI checks pass (T2/T4 only).
- [ ] Every review thread is READ, TRIAGED, SOLVED (if Blocking), REPLIED with course of action, and RESOLVED (T3/T4 only).
- [ ] `mergeStateStatus` is `CLEAN` (or `UNSTABLE` with documented non-required failures).
- [ ] Branch is up to date with `main` (`mergeStateStatus` not `BEHIND`).
- [ ] Force-push safety check ran before any push: `git rev-parse "refs/heads/$BRANCH"` matched the PR's expected `head.sha`.
- [ ] Correct merge path chosen by state: `set_pr_auto_merge.py --enable` for `CLEAN`, `merge_pr.py --strategy squash` for `UNSTABLE` with documented non-required failures (see "Merge path by `mergeStateStatus`" table; issue #2439).
- [ ] All four Ready-to-Merge conditions hold before the merge command runs (CanMerge=True is insufficient alone).
