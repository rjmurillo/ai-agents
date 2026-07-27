---
id: ADR-088
status: proposed
date: 2026-07-27
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-088: PR Branch Holder Lease

## Status

Proposed. This ADR amends ADR-076 for issue #3413. It records the decision before implementation because the change controls who may mutate a PR branch.

ADR review ran on 2026-07-27. The first draft had four blocking gaps: v1 to v2 rollout, generated holder fallback, latest-marker ordering, and override authorization. This revision closes those gaps before implementation starts.

## Date

2026-07-27

## Context

Multiple agents can work in this repository at the same time and push as the same GitHub author. PR #3405 showed the failure mode: branch `fix/3377-table-guards` moved through six commits between 2026-07-26T23:34:18Z and 2026-07-27T00:12:33Z, a 2,295 second window. Issue #3412 fixed transport verification so a push cannot report success while landing on the wrong ref. It did not decide who owns a PR branch while work is in flight.

ADR-076 introduced a PR comment lease for `pr-autofix`. That lease is not enough for #3413. It keys self-renewal on the verified GitHub comment author. Same-user agents share that author, so agent B can renew agent A's lease and both can believe they own the branch.

The problem is not same-file overlap across branches. A measurement on 2026-07-27 found 27 files touched by more than one open PR, including generated artifacts and plugin manifests. That is a separate contention policy and is tracked by issue #3572. This ADR only covers one active holder for one PR branch.

## Decision

Adopt a fail-closed, PR-comment-backed holder lease for PR branch mutation. The lease is keyed by repository, PR number, and branch. A holder is identified by an opaque holder id plus the verified GitHub actor. Self-renewal requires both the same holder id and the same verified actor. GitHub actor alone is never enough.

This ADR changes ADR-076 in six ways:

1. Self-renewal no longer keys on GitHub author alone. It keys on `(verified_actor, holder_id)`.
2. Branch mutation enforcement fails closed on unresolved ownership, store failure, or auth failure.
3. The lease timeout becomes 30 minutes with mandatory renewal every 5 minutes during long operations.
4. `pid` and `worktree` are not lease schema fields. They are local diagnostics only.
5. Manual override is a first-class audited lease operation, not `--no-verify`.
6. v2 code reads v1 ADR-076 markers during rollout and treats live v1 markers as foreign holders.

### Holder identity fallback order

The implementation must resolve one stable holder id before acquire, renew, release, override, or push verification. It must use this order:

1. Explicit `--lease-holder` argument.
2. Environment session id from the running agent harness, for example `AI_AGENT_SESSION_ID` or `COPILOT_SESSION_ID`.
3. GitHub Actions identity: `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, and `GITHUB_JOB` joined into one holder id.

A generated holder id must not acquire, renew, release, or verify an enforced lease. A generated id is not stable across retries, so it creates self-blocking orphan leases. If no stable holder id is available, enforcement commands exit 2.

This does not block the known legitimate callers:

| Caller | Reaches `safe_push_pr_branch.py` today | Session id present | Holder source | Verdict |
|--------|----------------------------------------|--------------------|---------------|---------|
| Local interactive raw `git push` | No | No guarantee | None | Out of scope until migrated. |
| Local agent using push workflow | No | Yes by session protocol | Harness env or explicit `--lease-holder` after migration | Enforceable after migration. |
| Local `pr-autofix` command | No | Yes by session protocol | Harness env or explicit `--lease-holder` after migration | Enforceable after migration. |
| PR maintenance workflow | Yes | No session log | `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, and `GITHUB_JOB` | Enforceable now. |
| Manual helper invocation | Yes | No guarantee | Explicit `--lease-holder` | Enforceable only with explicit holder. |
| Other workflows with raw `git push` | No | Workflow run id available | GitHub Actions identity after migration | Out of scope until migrated. |
| `.github/actions/ai-review` | No branch push | Workflow run id available | None | Read-only for this ADR's branch-mutation scope. |

### Expiry and renewal

The lease TTL is 30 minutes. Long operations must renew the lease every 5 minutes, immediately before starting a push, and while any child process such as tests or a pre-push hook is still running. If renewal fails in enforcement mode, the operation must abort and report exit 3 for store failure or exit 4 for auth failure. It must not keep working under an unrenewed lease.

Measurements collected on 2026-07-27 drove this value:

| Source | Window | Count | p50 | p75 | p90 | Max | Over 15 minutes | Over 30 minutes |
|--------|--------|-------|-----|-----|-----|-----|-----------------|-----------------|
| PR maintenance workflow runs | 2026-07-25T11:27:15Z to 2026-07-27T20:32:37Z | 49 | 538s | 794s | 1769s | 2254s | 9 | 4 |
| Recent PR commit-span windows | Sample collected 2026-07-27 from last 35 PRs | 35 | 3090s | 7386s | 11366s | 23066s | 22 | 21 |
| PR #3405 incident branch span | 2026-07-26T23:34:18Z to 2026-07-27T00:12:33Z | 1 | 2295s | 2295s | 2295s | 2295s | 1 | 1 |

The 30 minute TTL covers the PR maintenance p90 and the lower end of the known 20 to 30 minute pre-push gate. The measured max PR maintenance run and the PR #3405 incident exceed 30 minutes, so renewal is mandatory. This is deliberate: a longer fixed TTL would reduce renewal pressure but increase crash-block time. A shorter TTL would expire during real pre-push work unless renewal timing was perfect.

`base_sha` is audit data. It records the PR head the holder saw when it posted the marker. Current exact-SHA verification still comes from the live remote ref immediately before transport, not from `base_sha`.

### Lease schema

The v2 marker comment uses this schema:

```text
<!-- PR-BRANCH-HOLDER-LEASE -->
version: 2
owner: <automation-id>
holder: <opaque-holder-id>
actor: <display-github-login>
branch: <head-ref>
acquired_at: <RFC3339-UTC>
renewed_at: <RFC3339-UTC>
expires_at: <RFC3339-UTC>
base_sha: <40-hex>
operation: claim
```

An override uses the same marker with:

```text
operation: override
previous_holder: <holder-id>
reason: <human-written reason>
```

A release uses the same marker with:

```text
operation: release
previous_holder: <holder-id>
reason: completed|skipped|failed
```

`pid` and `worktree` are not part of the lease. A PID has meaning only on one host and can be reused by the operating system. A worktree path has meaning only on one machine. Neither can prove liveness across local agents, cloud agents, and GitHub Actions. `safe_push_pr_branch.py` may keep process id and worktree path in local audit output, but lease decisions must not use them.

### Comment ordering and rollout

The PR comment store is the source of record. The implementation must scan the newest 100 issue comments and parse both markers:

- v2 marker: `<!-- PR-BRANCH-HOLDER-LEASE -->`.
- v1 marker from ADR-076: `<!-- PR-AUTOFIX-LEASE -->`.

The authoritative state is the valid marker with the highest GitHub issue comment id. Comment body timestamps do not decide ordering. Edited comments do not become newer state. Renew, release, and override must post a new marker comment rather than edit an older comment.

During rollout, a live v1 marker is treated as a foreign live holder because v1 has no holder id. v2 code must not acquire over it unless the v1 lease is expired or an authorized override is posted. v2 determines v1 expiry by parsing ADR-076's `expires_at` field and treating `owner: none` as a release tombstone. After any v2 marker exists, a newer live v1 marker still blocks v2 code because an old client wrote after the v2 client. This favors a false block over two owners.

A marker is valid only when:

- The marker is within the newest 100 issue comments.
- The verified GitHub comment author is available from the API.
- `branch` matches the PR head branch under enforcement.
- `expires_at` parses as UTC and is no later than reader-now plus the maximum TTL.
- Required fields for the operation are present.

Malformed latest markers in enforcement mode are ownership ambiguity and exit 2. Store read failure exits 3. Auth failure exits 4.

### Override authorization

Override is reserved for humans or automation with repository `maintain` or `admin` permission. The implementation must verify the comment author or token actor through the GitHub API before accepting the override. Comment body `actor` is display text and cannot authorize anything.

An override must post a v2 marker with operation `override`, the previous holder, the new holder, the verified actor, the branch, the base SHA, and a human reason. An override does not bypass exact-SHA push verification. Unauthorized override attempts exit 4 when authorization cannot be proven, or 2 when the override request is malformed.

### Consistency model

The PR comment store is non-transactional. The model is at-least-once writes with idempotent readers:

- The highest valid GitHub issue comment id wins.
- A duplicate acquire by the same `(verified_actor, holder)` is a no-op success and posts a renewal marker.
- A duplicate release posts another release marker and remains success.
- If release fails, the holder remains visible until expiry or override.
- If a process dies between push and release, the lease expires after the TTL.
- If two release markers race, the highest valid release marker means free.
- Exactly-once release is not claimed.

The lease is not authorization to push. The push still verifies the exact remote SHA before transport. The lease prevents known duplicate owners before the expensive work. The SHA gate remains the final safety gate.

### Exit behavior

| Case | Exit | Reason |
|------|------|--------|
| Lease acquired, renewed, released, overridden, or verified | 0 | Holder may proceed. |
| Live lease held by a different holder | 1 | Logic-level skip. The caller must not mutate the branch. |
| Missing PR, branch, actor, holder, malformed latest marker, or unauthorized generated holder | 2 | Configuration or usage error. |
| Lease store read or write failure in enforcement mode | 3 | External failure. Fail closed for branch mutation. |
| GitHub authentication or authorization failure in enforcement mode | 4 | Auth failure. Fail closed for branch mutation. |

This reuses the existing `safe_push_pr_branch.py` taxonomy. Its exit 1 already means verification failed and the branch must not be mutated. A foreign live holder is one more verification failure. Implementers must print a machine-readable reason such as `lease_held`, `lease_malformed`, or `lease_store_unavailable` so callers can distinguish subcases without changing exit-code semantics.

ADR-076 allowed fail-open because it treated the lease as advisory. This ADR changes that for branch mutation paths. A gate that cannot determine ownership must not mutate the branch.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure or pattern being changed**: ADR-076 and `pr_autofix_lease.py` define a PR-comment-backed lease with 15 minute TTL, fail-open store errors, and self-renewal keyed on verified comment author.
- **When introduced**: ADR-076 was accepted on 2026-06-20 for issue #2615. Phase 1 tooling shipped under that ADR.
- **Original author and context**: The design reduced duplicate local `pr-autofix` work while keeping the SHA gate as the hard safety boundary.

### Historical Rationale

- **Why was it built this way?** ADR-076 targeted wasted work, not repository-wide branch ownership. Fail-open avoided turning a comment-store outage into a workflow outage.
- **What alternatives were considered?** ADR-076 rejected external lock stores, git notes, branch naming, and the SHA-only status quo.
- **What constraints drove the design?** The store had to be visible on the PR timeline, require no new infrastructure, and tolerate a best-effort release.

### Why Change Now

- **Has the original problem changed?** Yes. Issue #3413 covers same-user agents and workflows that share one GitHub author. GitHub-author self-renewal cannot distinguish them.
- **Is there a better solution now?** Yes. PR #3483 added `safe_push_pr_branch.py`, a Python push helper that can verify lease ownership next to exact-SHA transport checks.
- **What are the risks of change?** A fail-closed lease can block real work if identity fallback is wrong or the store is down. The stable holder order, expiry, renewal, and authorized override bound that risk.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep ADR-076 unchanged | No new schema. No workflow break from store failures. | Same-user agents can renew each other's leases because author is shared. 15 minute TTL expires during real pushes. | It does not solve #3413. It only reduces some duplicate `pr-autofix` work. |
| Pre-push hook enforcement | Runs before any normal push. Already installed locally. | Cannot reliably see PR number, lease holder, or GitHub auth. Raw git hooks are also bypassed by forbidden `--no-verify`. | It cannot observe the conflict at the decision point and would block unrelated pushes. |
| Repository lock file | Easy to inspect in git. Could use normal merge conflict rules. | The lock races through the same branch transport it is meant to protect. It pollutes history and can conflict with real content changes. | It uses git as the lock store for a git race. That is circular. |
| Branch protection or labels | GitHub-native. Visible to maintainers. | Cannot express a short active owner with expiry and renewal. Labels and assignees go stale. | It cannot see whether another agent is active right now. |
| External lock service | Could provide compare-and-set and fencing tokens. | Adds infrastructure, credentials, and outage modes. Fail-open would erase the value. Fail-closed would stop PR work. | Too much machinery for a repo-local branch mutation gate. |
| PR-comment holder lease with exact-SHA push gate | Visible on PR timeline. No new infrastructure. Can fail closed at mutation points. Works for local and GitHub Actions callers that provide stable holder ids. | No atomic compare-and-set. Comment writes can race. Requires renewal and an override path. | Chosen. It sees the conflict, has bounded staleness, and preserves exact-SHA push safety. |

### Trade-offs

This decision accepts a best-effort store and compensates with exact-SHA push verification. It blocks more often than ADR-076 because store and auth failures now stop branch mutation. That is intentional. The cost of a false allow is unreachable work or branch churn. The cost of a false block is a visible retry, expiry, or audited override.

The decision rejects generated holder ids for enforcement. That makes manual use less convenient, but it prevents a retry from blocking itself behind an orphaned one-shot id.

## Consequences

### Positive

- A same-user second agent sees a live holder and exits before mutating the branch.
- PR maintenance gets a holder id without a session log because GitHub Actions run identity is available.
- A legitimate long run can hold ownership through pre-push and tests by renewing the lease.
- A crashed agent releases ownership through expiry without manual deletion.
- Overrides leave a PR timeline record with previous holder, new holder, actor, reason, and time.

### Negative

- Store or auth failure blocks branch mutation in enforcement mode.
- A crashed holder can block a branch for up to 30 minutes.
- The PR timeline gets more machine comments.
- Implementers must preserve a renewal loop around long commands and pushes.
- The non-transactional store can still have sub-second acquire races. The SHA gate must stay.
- Manual helper users must pass a stable holder id.

### Neutral

- `pid` remains in local push audit records, not the lease.
- Worktree path is not recorded in the lease.
- Same-file overlap across branches remains out of scope and is tracked by issue #3572.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|-----------------|-----------------|------|
| `.agents/architecture/ADR-076-pr-autofix-branch-ownership-lease.md` | Direct | Treat this ADR as an amendment for self-renewal, fail-closed mutation, expiry, and override semantics. | Medium |
| `.claude/skills/github/scripts/pr/pr_autofix_lease.py` | Direct | Add v2 parser, v1 coexistence, holder identity fallback, strict exit behavior, renewal, release, status, and override operations. | High |
| `.github/scripts/safe_push_pr_branch.py` | Direct | Verify current holder before transport, renew while long child processes run, and keep exact-SHA checks. | High |
| `.github/workflows/pr-maintenance.yml` | Direct | Pass GitHub Actions holder identity to Python helpers without adding logic to YAML. | Medium |
| `.claude/commands/pr-autofix.md` | Direct | Acquire before branch mutation, renew during long work, verify before push, release after completion. | Medium |
| Tests under `tests/` | Direct | Add exit-code and concurrency tests selected by the pre-push `-m "not integration"` command. | Medium |
| Issue #3572 | Related | Track file-overlap and duplicate-branch hazards outside this branch-owner policy. | Low |

## Implementation Notes

- Implement the ADR in a later PR after this ADR is accepted.
- Keep logic in Python. Workflow YAML may pass environment variables only.
- Add tests for second agent blocked, stale claim reclaimed, crashed claim expiry, audited override, missing identifier fail-closed, and duplicate acquire by the same holder as no-op success.
- Prove tests are selected by the pre-push pytest selector with `--collect-only`.
- For RED/GREEN proof, run each new test on the implementation branch, then revert the implementation and prove it fails.
- Use a renewal interval of 5 minutes. Renew before push and while tests, pre-push hooks, or transport are running.
- Abort long work if renewal fails in enforcement mode.
- Do not trust `pid`, worktree path, body-declared owner, or body-declared actor for authorization.
- Keep exact remote SHA verification as the final safety gate before transport.
- Control `TMPDIR` and pytest `--basetemp` during failure-set measurement so issue #3511's old in-tree temp failure does not pollute results.
- Scan at most the newest 100 issue comments. If the scan fails, exit 3 or 4 rather than allowing mutation.
- Post a new marker for claim, renew, release, and override. Do not edit older marker comments for state transitions.

## Rollback and Kill Criteria

Rollback is to stop calling lease enforcement from `safe_push_pr_branch.py` and `pr-autofix` while leaving old PR comments as inert timeline records. Because enforcement lives in Python callers, workflows can stop passing lease arguments without changing historical comments.

Kill the implementation and revert enforcement if any of these hold during the first 30 days after merge:

- Two unauthorized overrides are observed in PR timeline v2 override markers or helper audit logs.
- More than three branch mutations are blocked for over 30 minutes by malformed or ambiguous lease state, measured by PR comment timestamps plus workflow retry logs.
- Store or auth failure blocks PR maintenance for more than two consecutive scheduled runs, measured from workflow run conclusions and helper reason codes.
- A same-branch collision still reaches push transport while both participants used the helper and no store outage occurred, measured from helper audit logs and exact-SHA failure output.

The implementation must emit one structured lease event for every acquire, renew, release, override, and verify result. Local agents write it to the session log. GitHub Actions writes it to workflow logs. Keep the implementation if at least one real second-holder collision is blocked, or if PR maintenance produces no same-branch branch churn for the 30 day window.

## Related Decisions

- ADR-035: Exit code standardization.
- ADR-042: Python migration strategy.
- ADR-076: PR-Autofix branch-ownership lease.
- Issue #3412 and PR #3483: Transport-verified safe push.
- Issue #3413: Enforce one active agent per PR branch.
- Issue #3572: File-overlap hazards outside branch ownership.

## References

- `.agents/architecture/ADR-076-pr-autofix-branch-ownership-lease.md`
- `.github/scripts/safe_push_pr_branch.py`
- `.github/workflows/pr-maintenance.yml`
- `.claude/skills/github/scripts/pr/pr_autofix_lease.py`
- `.claude/commands/pr-autofix.md`
