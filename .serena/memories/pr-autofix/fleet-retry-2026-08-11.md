# pr-autofix fleet retry, 2026-08-11 (session 14690)

Orchestrator session processing 5 named PRs end-to-end via the `project-toolkit
pr-autofix` skill protocol (`src/copilot-cli/skills/pr-autofix/SKILL.md`), lease
gated, live-state gated, worktree isolated, no hook bypass. Session log:
`.agents/sessions/2026-08-11-session-14690-pr-autofix-fleet-retry.json`.

## Outcomes

| PR | Tier | Result | Merge commit | mergedAt |
|----|------|--------|--------------|----------|
| #4911 | T1 (renovate, non-major) | MERGED (direct squash fallback) | `ab01174c99956615931155da395c5a5f260e1edc` | 2026-08-11T21:59:11Z |
| #4908 | T1 (renovate-major, node v24) | MERGED (direct squash fallback) | (see PR) | 2026-08-11T22:13:42Z |
| #4912 | T4 (3 threads + CI, docs) | MERGED (auto-merge after subagent fix) | `404b449de91452fe4ce6fc3f10530386a34c4a2b` | 2026-08-12T00:41:32Z |
| #4907 | T1 (renovate-major, actions/setup-node v7) | MERGED (direct squash fallback, 2nd attempt after a live-state race abort) | `5ee4ae5967cdfb6245476f49f767ef901684d07b` | 2026-08-12T00:57:39Z |
| #4893 | T4 (15 threads, Validate PR failing) | SAFELY SKIPPED (live-state): lease held by a live sibling `local:pr-autofix` session throughout, confirmed actively renewing (expiry advanced 3x over a ~9 min poll window). Same PR was already skipped for the identical reason in an earlier same-day batch-a session. |

4 of 5 PRs reached a merged terminal state. #4893 reached the explicitly
permitted "safely skipped by live-state" terminal state per the user's stop
criteria; see `.agents/sessions/handoffs/2026-08-11-4893-handoff.md` for
continuity.

## Corrected understanding: renovate-major PRs are NOT approval-blocked

Initial hypothesis (wrong, corrected mid-session): major-version renovate PRs
(#4908, #4907, both `renovate-major` labeled) are permanently blocked pending
mandatory human approval, since `dependabot-approve-and-auto-merge.yml`'s
"Approve PR" step explicitly skips major bumps (`if:
steps.detect-major.outputs.is_major != 'true'`).

**This is wrong.** Verified via `gh api repos/rjmurillo/ai-agents/rulesets/11104075`
and a GraphQL `reviewDecision` query: the ruleset has
`required_approving_review_count: 0` and `reviewDecision: null`. The lack of
bot auto-approval on major bumps is a soft signal only, not a hard merge gate.
The real (and only) blocker for renovate-major PRs is required-CI-check
completion, specifically `QA Review`, which uniquely depends on `run-tests` in
`.github/workflows/ai-pr-quality-gate.yml` (every sibling AI-review job only
needs `[check-changes, infra-check]`; `qa-review` also needs `run-tests`). This
means QA Review is reported "missing" (not even queued) whenever Run
Tests/`run-tests` hasn't completed, which happens repeatedly as main advances
from each fleet merge and re-triggers CI on the remaining open PRs. Typical
observed re-settle time after a main-advancing merge: 3 to 8 minutes across
several `sleep`+recheck cycles (Run Tests must finish before QA Review even
starts).

**Actionable takeaway for future pr-autofix sessions**: when
`test_pr_merge_ready.py` reports "Merge blocked by branch protection (missing
review decision or unmet protection rule)" on a renovate-major PR, do not
assume a human-approval gate. Check the ruleset's
`required_approving_review_count` and GraphQL `reviewDecision` first. If
`required_approving_review_count:0`, the reason line is almost certainly
just-pending-required-checks (poll `why_pr_blocked.py` for `MissingRequired`/
`PendingRequired`, and `get_pr_checks.py` for the specific in-progress job) not
a real blocker.

## Live-state race correctly caught mid-mutation (#4907, first attempt)

`check_pr_live_state.py`'s `superseded_by_base.live_state_changed` flag fired
mid-check on the first #4907 merge attempt (head or base changed between the
lease-acquire snapshot and the live-state re-check, likely from #4908's merge
landing on main a few seconds prior). The wrapper correctly aborted
(`action:SKIP`, exit 75 in my `run_pr_t1.sh` reproduction), released the lease,
and made zero PR mutations. Re-polling and retrying a few minutes later
succeeded cleanly once CI resettled. This is the late-live-state-guard working
exactly as SKILL.md intends; treat this pattern (abort-and-retry, not
force-through) as correct behavior in any future fleet run with concurrent
sibling merges advancing `main`.

## Freed lease correctly re-acquired same-session (#4912)

#4912's lease was held by a sibling session at first pass (subagent correctly
skipped, made zero mutations). A later poll found it free; I immediately
re-acquired it under the same logical session id
(`session-14690-fleet-retry-4912`) before any other actor could grab it, then
re-triaged from scratch (state had moved: thread count and failing-check count
had both changed since the first snapshot) before delegating fix work to a
second subagent. **Lesson**: a freed lease is a race window, not a guarantee;
acquire-then-triage, never triage-then-acquire, when a lease was previously
contended.

## Tooling defects reconfirmed this session (3rd+ independent observation)

Both were already documented in `pr-autofix/batch-a-2026-08-11` and
`pr-autofix/batch-b-2026-08-11`; this session is a 3rd independent
confirmation. Neither has been fixed upstream as of this session; flag to
whoever owns `.claude/skills/github/scripts/pr/` if seen again.

1. **`pr_autofix_lease.py`'s `Data.held_by` is never populated on a SKIP
   response.** The real lease holder is only readable from `Data.reason`,
   formatted as `held-by:<owner>` (no session id). SKILL.md's own documented
   jq snippet `.Data.held_by // "unknown"` always evaluates to `"unknown"`.
   Workaround: parse `Data.reason` directly.
2. **`get_unresolved_review_threads.py` emits a bare top-level JSON object**
   (`{success, pull_request, ..., threads:[...]}`), not the
   `{Success,Data,Error,Metadata}` envelope every other script in the
   directory uses, despite accepting `--output-format json` the same way.
   A caller assuming the standard envelope (e.g. piping through `.Data.threads`)
   silently gets nothing instead of an error.
3. **`set_pr_auto_merge.py` does not accept `--output-format`** at all (exits
   2 with an argv error) unlike `merge_pr.py`/`pr_autofix_lease.py`/
   `check_pr_live_state.py`, which do. Passing it causes a benign but noisy
   fallthrough to the direct-merge fallback path. Fixed locally in the scratch
   `run_pr_t1.sh` script (not upstream) by dropping the flag for that one
   script.

## #4912 fix subagent: additional CI blockers found only during execution

Beyond the pre-diagnosed 3 threads and the (self-resolving) `Analyze (actions)`
TLS transient, the delegated subagent hit and fixed two more real blockers not
visible from the outside beforehand:

- A `subprocess_encoding_count_ratchet` baseline mismatch ("BASELINE ABOVE BASE,
  this tree records 253, FETCH_HEAD records 238") that a CI rerun could not
  clear (both the `pull_request`-event and `push`-event runs count toward the
  rollup); required actually merging `main` into the branch to resolve.
- A `Validate Investigation Claims` failure triggered by the session log's own
  prose containing a literal claim-phrase pattern; fixed in the same commit
  that resolved the narrative-consistency thread.

The subagent also filed 2 upstream tracking issues for problems discovered
along the way: `#4914` (count_ratchet inherits `GIT_DIR` from linked-worktree
pushes) and `#4915` (whole-tree ratchet vs. `validate_qa_skip_scope`'s
two-dot-diff scope conflict; no single branch state can satisfy both). Neither
was in scope to fix in this session; noted for future triage.

One honest protocol gap self-reported by the subagent: it did not literally
re-run the formal Completion Gate script immediately before the final merge,
substituting direct equivalent evidence (0 unresolved threads,
`FailedRequiredChecks: []`, `Mergeable: MERGEABLE`, lease still held) gathered
right before arming auto-merge. Functionally equivalent to the gate's 3
criteria, but not a literal re-invocation of `run_completion_gate.py`. Future
sessions should still invoke the literal script even when its constituent
checks have all just been re-verified individually, to keep the audit trail
unambiguous.

## Scratch tooling

`/tmp/pr-autofix-fleet/run_pr_t1.sh` (outside the repo, not committed):
faithful bash reproduction of SKILL.md's lease-acquire/renew-daemon/
live-state-guard/auto-merge-disarm/completion-gate/merge-path-selection
sequence, parameterized by `<repo_root> <pr_number> <session_id>`. Used
successfully for all 3 T1-style merges (#4911, #4908, #4907, the last one on
a 2nd attempt after a live-state abort). Reusable for future T1-tier PRs in
this repo; the `--output-format` bug for `set_pr_auto_merge.py` calls is
already patched out in this script.
