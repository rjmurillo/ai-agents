---
id: ADR-074
status: proposed
date: 2026-06-17
decision-makers: []
supersedes: []
superseded-by: null
explainer: null
implemented: false
staging-note: >-
  Draft staging copy of the proposed ADR-074. The canonical path
  .agents/architecture/ADR-074-pr-autofix-branch-ownership-lease.md is guarded
  by the ADR architect PreToolUse gate (invoke_adr_architect_gate.py), which
  reads architect-review evidence from CLAUDE_PROJECT_DIR (the main checkout)
  and cannot see worktree-local evidence. Satisfying it requires the architect
  subagent or the full 6-agent adr-review debate. Rename this file to the
  canonical ADR-074 path after adr-review runs in a non-isolated checkout.
---

# ADR-074: PR-Autofix Branch-Ownership Lease

## Status

Proposed. Requested by issue #2615 (labels `bug`, `agent-qa`, `agent-devops`, `area-workflows`, `priority:P1`, `priority:P2`, `automation`). The maintainer's backlog evaluation (issue #2615 comment 2026-06-17) deferred the epic and named the precondition directly: "Requires an ADR on lease storage + concurrency semantics before implementation." This ADR is that precondition. It records the coordination protocol and the lease contract; it ships no code.

A single-reviewer architect design-review note was authored alongside this ADR (`.agents/critique/ADR-074-architect-design-review-debate-note.md`, verdict APPROVE-AS-PROPOSED). That note is NOT the full multi-agent debate. The standard 6-agent adr-review debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) and human acceptance are the required next gate. This ADR MUST clear both before its status moves to `accepted`. No tooling changes ship on this ADR alone.

## Date

2026-06-17

## Context

The `pr-autofix` workflow (`.claude/commands/pr-autofix.md`, `docs/autonomous-pr-monitor.md`) fixes review feedback on open PRs. A remote automated review/autofix routine (CodeRabbit autofix, a CI workflow, or a sibling agent) can commit to the same PR branch while a local `pr-autofix` session has staged but unpushed work. There is no coordination between the two loops today.

The existing Force-Push Safety SHA gate (`.claude/commands/pr-autofix.md` lines 100 to 105) is the only protection. Before any push it runs `git rev-parse "refs/heads/$BRANCH"` and compares it to the PR's expected `head.sha` from `get_pr_context.py`. When the remote branch has advanced, the local and remote SHAs disagree and the push is blocked. This is correct and MUST stay: it prevents the dangerous outcome (a force-push that overwrites the remote commit). But it is a post-hoc, detect-and-block gate. It fires only at push time, after the local loop has already done the fix work, and the recovery (fast-forward plus stash apply) can conflict.

Issue #2615 records the exact failure during PR #2611 autofix:

1. Local worktree had uncommitted follow-up changes on `16f507670`.
2. The remote branch advanced to `9315b86f` with `fix(guards): remove dead returncode check after check=True`.
3. The SHA gate correctly blocked the push (`expected=9315b86f... local=16f5076700... remote=9315b86f...`).
4. Fast-forward plus stash apply produced a conflict in `tests/test_hook_plugin_guards.py`.

Two automation loops fixed the same review feedback independently. The safety gate prevented the overwrite, but the operator paid a conflict-resolution cost and the system risked duplicate or contradictory fixes.

Three forces drive a decision now:

1. **Wasted work and conflict cost are structural, not incidental.** As long as both loops can start a fix on the same branch without seeing each other, the collision recurs. The SHA gate converts a silent overwrite into a visible conflict, which is strictly better, but it does not prevent the duplicated work that produced the conflict.

2. **The repo already has the verdict-gate pattern this needs.** `check_pr_live_state.py` (issue #2455) is the pre-action probe `pr-autofix` calls immediately before acting on each PR. It returns `{"action": "ACT" | "SKIP", "reason": "..."}` and follows ADR-035 exit codes. A lease check is the same shape of gate: a cheap probe, run before the expensive work, that returns ACT or SKIP. The protocol should reuse that pattern, not invent a new one.

3. **The auto-PRD already sketched a design that needs an architecture decision to bind it.** The issue's auto-generated PRD (#2615 comment 2026-06-16) proposed a lease via PR comments, 15-minute TTL, fail-open on missing lease, reuse of the `check_pr_live_state.py` ACT/SKIP pattern, and ADR-035 exit codes. It also flagged two open questions: the session-ID source for local sessions, and the BOT_PAT permissions for remote (Phase 2) integration. The PRD is an implementation sketch. The lease storage choice, the concurrency semantics, and the fail-open boundary are architecture decisions that bind every future implementer. That is what this ADR fixes.

### What a lease must and must not do

The coordination primitive here is a *lease*: a short-lived, advisory claim that one automation loop is actively working a fix on a specific PR branch. The lease is advisory because the SHA gate remains the hard safety boundary. The lease's job is to make the common case (two loops about to collide) resolve to "the second loop waits or skips" instead of "the second loop does the work, then collides at push time."

A lease is not a lock. A distributed lock that both loops trust would require a consistent store, fencing tokens, and a liveness protocol that survives a crashed holder. That is the wrong cost for an ergonomics fix on top of a safety gate that already prevents the dangerous outcome. The lease must fail open: if the lease store is unreachable, the lease is malformed, or no lease exists, the loop proceeds exactly as it does today and the SHA gate catches any real collision. A lease that fails closed would convert a store outage into a workflow outage, which is worse than the conflict it prevents.

## Decision

Adopt a **PR-comment-backed, advisory, fail-open branch-ownership lease** that `pr-autofix` (local) and remote review/autofix routines acquire before committing fix work to a shared PR branch, and release when done. The lease coordinates; the existing Force-Push Safety SHA gate continues to enforce. The lease never replaces the SHA gate and never relaxes it.

The decision has five binding parts.

### 1. Lease storage: a marker comment on the PR

The lease lives as a single hidden-marker comment on the PR, in the same store as `check_pr_live_state.py` already reads (the PR timeline). The comment body carries a machine-parseable block:

```text
<!-- PR-AUTOFIX-LEASE -->
owner: <automation-id>           # e.g. "local:pr-autofix", "remote:coderabbit-autofix", "ci:autofix-workflow"
session: <session-id>            # the holder's session identity (see part 4)
acquired_at: <RFC3339-UTC>       # lease start
expires_at: <RFC3339-UTC>        # acquired_at + TTL
base_sha: <40-hex>               # PR head.sha the holder fetched before acquiring
```

One PR carries at most one live lease comment. Acquire updates (edits) the existing lease comment or creates it if absent; release edits it to a tombstone (`owner: none`, `expires_at` in the past). The marker `<!-- PR-AUTOFIX-LEASE -->` makes the comment findable by a single timeline scan, exactly as `check_pr_live_state.py` scans the timeline today.

This choice satisfies acceptance criterion 3 directly: "The PR timeline records which automation owns the current fix loop." The lease *is* a timeline record.

### 2. Lease TTL: short, fixed, self-expiring

The lease TTL is 15 minutes. A lease whose `expires_at` is in the past is dead, regardless of any release step. TTL-based expiry is the liveness mechanism: a crashed or killed holder cannot wedge the branch, because the lease evaporates on its own clock. The acquiring loop reads `expires_at`, not a separate heartbeat. A holder that needs more than 15 minutes re-acquires (renews) by editing the comment with a new `expires_at`; renewal is the same operation as acquire and carries the same `base_sha` freshness check (part 3).

15 minutes is chosen to bound the worst-case wait for a blocked loop while comfortably covering a normal autofix cycle (read review, edit, test, commit, push). It is a fixed constant in this decision, not a tunable, to keep the protocol legible. A future ADR may parameterize it if evidence shows the constant is wrong; this ADR commits to the constant so implementers do not each pick their own.

### 3. Concurrency semantics: read-check-write with a SHA freshness guard, fail-open

The lease is advisory and the PR-comment store gives no atomic compare-and-set, so the protocol does not pretend to provide mutual exclusion. It provides a best-effort claim plus a hard freshness guard that defers the real safety decision to the SHA gate.

Acquire (`acquire_lease`):

1. Fetch the PR `head.sha` and the lease comment in one read.
2. If a live lease exists (`expires_at` in the future) and its `owner`/`session` is not this loop, return `SKIP` with reason `held-by:<owner>` and the `expires_at` so the caller knows when to retry.
3. If no live lease exists (absent, tombstoned, or expired), write the lease comment with this loop's identity, `acquired_at=now`, `expires_at=now+15m`, and `base_sha=<the head.sha just fetched>`. Return `ACT`.
4. **Fail open.** If the read or write fails (API error, auth error, malformed existing comment), log the failure and return `ACT` with reason `lease-store-unavailable`. The loop proceeds; the SHA gate is the backstop.

Push-time guard (unchanged plus one addition):

- The existing Force-Push Safety SHA gate runs exactly as today. A lease never authorizes a push; the SHA match still must hold.
- Addition: if this loop holds a live lease whose `base_sha` no longer matches the current PR `head.sha`, the remote advanced under the lease (a racing writer that ignored or did not see the lease, or a fail-open peer). The loop MUST re-sync to the new head and re-run its checks before pushing, and MUST NOT force-push over the newer commit. This is the same recovery path #2615 describes, now reached deliberately rather than by surprise, and reached *before* the fix work in the common case.

Release (`release_lease`): edit the lease comment to a tombstone. Release is best-effort; a missed release is covered by TTL expiry.

Because the store has no atomic CAS, two loops can both pass step 2 and both write in step 3 (a true race in the milliseconds between read and write). This is acceptable: the loser's write simply overwrites the winner's lease comment, both believe they hold the lease, and the SHA gate still prevents the dangerous push. The lease reduces collisions in the overwhelmingly common case (loops staggered by seconds or minutes); it does not claim to eliminate the sub-second race, and the safety gate does not depend on it doing so.

### 4. Owner and session identity

`owner` is a small, fixed vocabulary of automation identities (`local:pr-autofix`, `remote:coderabbit-autofix`, `ci:autofix-workflow`, plus any future loop), so a human reading the timeline sees which automation holds the branch. `session` is the holder's session identity: for a local `pr-autofix` run, the session-log session id already created by `new_session_log.py` (for example `session-2587`); for a CI run, the workflow run id. This resolves the PRD's first blocking question (session-ID source): local runs reuse the existing session-log id rather than generating a fresh UUID, so the lease is traceable back to a session log and its evidence.

### 5. Scope: a phased, reversible rollout; only the protocol is committed here

This ADR commits the protocol and the lease contract. It does not commit an implementation timeline beyond naming the phases, and each phase is independently shippable and reversible:

- **Phase 0 (this ADR).** Record the decision; run the full adr-review debate; obtain human approval. No code.
- **Phase 1 (local-only, additive).** Ship `acquire_lease` / `release_lease` / lease-read helpers and wire them into local `pr-autofix` only. Local runs acquire before fixing and release when done. A local run that sees a remote lease it cannot interpret fails open. Remote loops are unchanged and simply do not participate yet; a non-participating remote loop is exactly today's behavior, so Phase 1 is safe to ship before any remote integration exists.
- **Phase 2 (remote integration, gated on a BOT_PAT permissions audit).** Teach the remote review/autofix routine to acquire and check the lease before pushing. This requires a CodeRabbit/CI capability and credential review (the PRD's second blocking question: BOT_PAT permissions to post and edit lease comments from CI). Phase 2 does not start until that audit confirms the remote loop can both read and write the lease comment. Until then, remote loops are the unleased writers that Phase 1's fail-open and SHA gate already tolerate.

This phasing answers the "remote integration is uncertain" objection: the local half delivers value on its own (a local run that sees a fresh remote-CI lease, once Phase 2 exists, waits instead of colliding), and even before Phase 2, two *local* sessions on the same branch coordinate. The expensive, externally-gated remote half is deferred behind an explicit audit, not assumed.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: There is no branch-ownership coordination today. The only mechanism touching this problem is the Force-Push Safety SHA gate in `.claude/commands/pr-autofix.md` (lines 100 to 105) and `docs/autonomous-pr-monitor.md` (line 716), which compares `git rev-parse "refs/heads/$BRANCH"` to the PR `head.sha` and uses `git push ... --force-with-lease`.
- **When introduced**: Force-Push Safety predates this issue; `--force-with-lease` usage and the SHA audit are established in the autonomous PR monitor. The pre-action live-state probe `check_pr_live_state.py` was added for issue #2455.
- **Original author and context**: The SHA gate exists to prevent a force-push from overwriting a remote commit. `check_pr_live_state.py` exists to skip PRs that went merged/closed or were superseded by main mid-run.

The maintainer's #2615 evaluation confirmed by search that no lease, branch-ownership, or active-fix mechanism exists in `.claude/commands/pr-autofix.md`, `.claude/skills/`, or `scripts/` (only `git --force-with-lease`, which is the git safety flag, not a coordination lease).

### Historical Rationale

- **Why was it built this way?** The SHA gate solves the safety problem (no overwrite) at the cheapest possible point (push time) with a primitive git already provides (`--force-with-lease`). It deliberately does not coordinate the two loops, because coordination was not needed to make the push *safe*, only to make it *non-wasteful*.
- **What alternatives were considered?** None recorded for coordination; the SHA gate was scoped to safety, not ergonomics.
- **What constraints drove the design?** Git's `--force-with-lease` and the PR `head.sha` were already available and sufficient for the safety goal.

### Why Change Now

- **Has the original problem changed?** The safety problem has not. A new, distinct problem (wasted work plus conflict-resolution cost from uncoordinated loops) is now evidenced by PR #2611. The SHA gate does not address it because it is not a coordination mechanism.
- **Is there a better solution now?** Yes. `check_pr_live_state.py` established a reusable ACT/SKIP pre-action probe pattern. A lease check fits that pattern exactly, so the coordination layer can be added without inventing new machinery.
- **What are the risks of change?** A fail-closed lease could turn a comment-store outage into a workflow outage. Mitigated by the mandatory fail-open semantics (part 3, step 4). A lease that callers trust as a hard lock would create a false safety story. Mitigated by keeping the SHA gate as the only hard boundary and documenting the lease as advisory.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep only the SHA gate (status quo) | Zero new machinery; safety already guaranteed; nothing to fail open | Does not coordinate; wasted work and conflict cost recur every collision (#2611) | Does not address the stated problem; the cost issue #2615 names is real and unmitigated |
| Git-notes lease (`refs/notes/pr-autofix-lease`) | Lives with the repo; survives without the API; diffable | Notes are not in the PR timeline (fails acceptance criterion 3); fetch/push of the notes ref adds git plumbing both loops must run; remote CI rarely fetches notes | Invisible to the timeline; heavier for the remote loop than a comment |
| External lock store (Redis, a DB, a lock service) | Real atomic CAS; fencing tokens possible | New infra to operate; an outage fails the workflow unless it fails open, at which point it is no stronger than a comment; disproportionate to an ergonomics fix on a working safety gate | Wrong cost; the SHA gate already prevents the dangerous outcome, so strong mutual exclusion is not required |
| Branch-name convention / protected branches | No store; GitHub-native | Cannot express "actively being fixed right now" with a TTL; blocks pushes wholesale rather than coordinating a short fix window | Does not model a short-lived, expiring claim |
| **PR-comment lease, advisory, fail-open, TTL (chosen)** | Reuses the timeline store `check_pr_live_state.py` already reads; satisfies the "timeline records owner" criterion directly; fail-open keeps a store outage from becoming a workflow outage; TTL self-heals a crashed holder; no new infra | No atomic CAS, so the sub-second acquire race is possible; dual representation (lease comment plus SHA gate); release is best-effort | Chosen: matches the existing gate pattern, meets all three acceptance criteria, and the residual race is fully absorbed by the unchanged SHA gate |

### Trade-offs

The chosen design accepts that the lease is best-effort, not a true lock. It buys collision *reduction* in the common case (loops staggered by seconds to minutes) for near-zero cost and zero new infrastructure, and it deliberately does not attempt the much more expensive *elimination* of the sub-second race, because the SHA gate already makes that race harmless to safety. It accepts a dual representation (the advisory lease comment plus the authoritative SHA gate) and keeps the SHA gate as the single hard boundary, so a reader never has to ask "which mechanism actually protects the branch." The TTL trades a bounded worst-case wait (up to 15 minutes for a blocked loop) for crash-safety without a heartbeat protocol.

## Consequences

### Positive

- The common collision (two loops about to fix the same branch, staggered by more than a sub-second) is resolved before the fix work: the second loop sees the lease and SKIPs or waits, instead of doing duplicate work and colliding at push time. This directly removes the #2611 cost.
- The PR timeline records which automation owns the current fix loop (acceptance criterion 3), via the lease comment itself.
- The coordination layer reuses the `check_pr_live_state.py` ACT/SKIP probe pattern and ADR-035 exit codes, so it is legible to anyone who already understands the pre-action gate.
- Fail-open means a comment-store outage degrades to exactly today's behavior (no coordination, SHA gate still enforcing), never to a workflow outage.
- TTL expiry means a crashed or killed holder cannot wedge a branch; no operator intervention is needed to clear a dead lease.

### Negative

- No atomic compare-and-set on PR comments, so two loops can race between read and write and both believe they hold the lease. Residual risk is bounded to the sub-second window and is fully absorbed by the unchanged SHA gate; the lease never claims mutual exclusion.
- Best-effort release plus TTL means a stale lease comment can persist for up to the TTL after a holder dies, briefly blocking a peer that respects it. Bounded by the 15-minute constant.
- Dual representation (advisory lease plus authoritative SHA gate) is one more mechanism for a maintainer to understand. Mitigated by stating explicitly that the SHA gate is the only hard boundary.
- Phase 2 (remote integration) depends on an external capability and a BOT_PAT permissions audit that may constrain or delay it. Until Phase 2, remote loops are unleased writers; the fail-open and SHA gate already tolerate them, so the local half still ships.
- A malformed or attacker-authored lease comment is an input the acquire path parses. Mitigated below (Security).

### Neutral

- Adds a `<!-- PR-AUTOFIX-LEASE -->` marker comment to PRs under active autofix, alongside the existing bot comments already on the timeline.
- The lease constant (15 minutes) is fixed by this ADR; a future ADR may parameterize it if evidence warrants.

## Security

The lease comment is untrusted input read from the PR timeline, so the acquire path is an integration point (per `.claude/rules/release-it.md`) and an injection surface.

- **Parse defensively.** The lease block is parsed with a strict, anchored format (the five known keys, RFC3339 timestamps, a 40-hex `base_sha`, an `owner` from the fixed vocabulary). A malformed or unparseable lease comment is treated as "no live lease" and the loop fails open to `ACT`; it is never executed, evaluated, or used to drive a shell command. This blocks the lease comment becoming a command-injection (CWE-78) or deserialization vector.
- **The lease is not an authorization.** Acquiring a lease never authorizes a push. The SHA gate, which compares real git SHAs, is the only thing that gates a push. A forged lease (anyone who can comment on the PR can write `<!-- PR-AUTOFIX-LEASE -->`) can at most cause a peer loop to SKIP or wait, a denial-of-service on the autofix loop, bounded by the TTL. It can never cause an overwrite, because the SHA gate is independent of the lease. This is the deliberate reason the lease is advisory: it keeps the forgeable signal away from the safety decision.
- **No auto-fetch of lease content.** The lease carries no URLs and the parser fetches nothing. `base_sha` is compared, not dereferenced.
- **Bounded blast radius of forgery.** The worst a forged lease achieves is a self-DoS on the fix loop for at most one TTL. Phase 2's BOT_PAT audit must confirm the remote loop's credential can edit lease comments without escalating any other permission.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/commands/pr-autofix.md` | Direct | Document the lease acquire/release steps in the autofix flow; clarify the lease is advisory and the SHA gate remains authoritative (Phase 1) | Medium |
| `docs/autonomous-pr-monitor.md` | Direct | Document the lease as a pre-action coordination step alongside `check_pr_live_state.py`; keep the Force-Push Safety section unchanged (Phase 1) | Medium |
| New lease helper scripts (for example `scripts/pr_autofix_lease.py` with `acquire_lease`/`release_lease`/read) | Direct (new) | Implement the read-check-write, fail-open, TTL, and strict parser; ADR-035 exit codes; pytest coverage per `.claude/rules/testing.md` | Medium |
| `check_pr_live_state.py` | Indirect | No change required; the lease check is a sibling probe, not a modification, but should run in the same pre-action position | Low |
| Force-Push Safety SHA gate | Indirect | No relaxation. One addition: when a held lease's `base_sha` no longer matches `head.sha`, re-sync before push (already the recovery path) | Low |
| Remote review/autofix routine (CodeRabbit autofix / CI) | Direct (Phase 2) | Acquire and check the lease before pushing; requires a BOT_PAT permissions audit before Phase 2 starts | High |
| `src/copilot-cli/` mirrors of the github skill | Indirect | Regenerate via `build/scripts/build_all.py` if any shared script changes | Low |

## Implementation Notes

Phased rollout, each phase a separate PR.

1. **Phase 0 (this ADR).** Decision recorded; full adr-review debate and human acceptance pending.
2. **Phase 1 (local-only).** Ship the lease helpers and wire them into local `pr-autofix`. Acquire before fix work, release after push (or on early exit). Fail open on any store error. pytest covers: live lease held by another owner returns SKIP; expired lease returns ACT and overwrites; missing lease returns ACT; malformed lease returns ACT (fail-open); store error returns ACT (fail-open); `base_sha` mismatch at push time triggers re-sync. Document in `pr-autofix.md` and `autonomous-pr-monitor.md`.
3. **Phase 2 (remote integration, gated).** After a BOT_PAT permissions audit confirms the remote loop can read and write lease comments, teach the remote routine to acquire/check the lease before pushing. Do not start until the audit passes.

**Success metric.** A `pr-autofix` collision rate on shared branches that drops measurably after Phase 1 for two-local-session cases, and after Phase 2 for local-vs-remote-CI cases, with zero force-push overwrites in either phase (the SHA gate guarantee preserved). If Phase 2's audit fails, Phase 1 still stands as the committed, shippable slice.

## Related Decisions

- ADR-035 (exit-code standardization): the lease helpers follow the `0=ok, 1=skip, 2=not-found, 3=external, 4=auth` contract, matching `check_pr_live_state.py`.
- ADR-066 (hook fail-open reconciliation): precedent that a coordination gate fails open rather than blocking the workflow on store failure.
- ADR-009 (parallel-safe multi-agent design): the lease is a parallel-safety primitive for two automation loops sharing one branch.
- ADR-014 (distributed handoff architecture): related coordination context for cross-session ownership; the lease is a short-lived, branch-scoped analog of a handoff claim.
- Issue #2455 (`check_pr_live_state.py`): the ACT/SKIP pre-action probe pattern this lease reuses.
- Issue #2611: the triggering collision incident.
- Issue #2615: origin of this proposal; the auto-PRD (#2615 comment 2026-06-16) is the implementation sketch this ADR binds.

## References

- `.claude/skills/github/scripts/pr/check_pr_live_state.py`. Pre-action ACT/SKIP probe; pattern and exit-code precedent.
- `.claude/commands/pr-autofix.md` (Force-Push Safety, lines 100 to 105). The authoritative SHA gate this lease sits beside.
- `docs/autonomous-pr-monitor.md` (line 716). `--force-with-lease` push path.
- `.agents/architecture/ADR-035-exit-code-standardization.md`. Exit-code contract.
- `.claude/rules/release-it.md`. Integration-point, fail-open, and timeout guidance for the lease store call.
- `.agents/critique/ADR-074-architect-design-review-debate-note.md`. Single-reviewer architect design-review (pre-debate).
- RFC 3339 (timestamp format for `acquired_at` / `expires_at`): <https://www.rfc-editor.org/rfc/rfc3339>
