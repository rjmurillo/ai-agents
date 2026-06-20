---
id: ADR-076
status: accepted
date: 2026-06-17
decision-makers: [rjmurillo, architect, critic, independent-thinker, security, analyst, high-level-advisor]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-076: PR-Autofix Branch-Ownership Lease

## Status

Accepted (2026-06-20). Requested by issue #2615 (labels `bug`, `agent-qa`, `agent-devops`, `area-workflows`, `priority:P1`, `priority:P2`, `automation`). The maintainer's backlog evaluation (issue #2615 comment 2026-06-17) deferred the epic and named the precondition directly: "Requires an ADR on lease storage + concurrency semantics before implementation." This ADR is that precondition. It records the coordination protocol and the lease contract; it ships no code.

The standard 6-agent adr-review debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) ran on 2026-06-19 and is recorded at `.agents/critique/ADR-076-debate-log.md` (tally: 6 APPROVE-WITH-CHANGES, 0 BLOCK). The must_fix items from that debate are addressed in this revision. Accepted 2026-06-20 by repo-owner authorization (rjmurillo, issue #2615), bound to the 6-agent debate consensus at `.agents/critique/ADR-076-debate-log.md` (6 APPROVE-WITH-CHANGES, 0 BLOCK; all must_fix applied in this revision). Phase-1 tooling (`pr_autofix_lease.py`) ships with this acceptance under #2615.

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

2. **The repo already has the verdict-gate pattern this needs.** `check_pr_live_state.py` (issue #2455) is the pre-action probe `pr-autofix` calls immediately before acting on each PR. It returns `{"action": "ACT" | "SKIP", "reason": "..."}` and exits 0 on ACT / 1 on SKIP. A lease check is the same shape of gate: a cheap probe, run before the expensive work, that returns ACT or SKIP. The protocol reuses that verdict shape and exit-code convention, not the probe's storage. `check_pr_live_state.py` reads PR state fields and git supersession (see part 1), not the comment timeline; the lease adds a new comment-timeline read path. The reuse is the gate *pattern*, not a shared store.

3. **The auto-PRD already sketched a design that needs an architecture decision to bind it.** The issue's auto-generated PRD (#2615 comment 2026-06-16) proposed a lease via PR comments, 15-minute TTL, fail-open on missing lease, reuse of the `check_pr_live_state.py` ACT/SKIP pattern, and ADR-035 exit codes. It also flagged two open questions: the session-ID source for local sessions, and the BOT_PAT permissions for remote (Phase 2) integration. The PRD is an implementation sketch. The lease storage choice, the concurrency semantics, and the fail-open boundary are architecture decisions that bind every future implementer. That is what this ADR fixes.

### What a lease must and must not do

The coordination primitive here is a *lease*: a short-lived, advisory claim that one automation loop is actively working a fix on a specific PR branch. The lease is advisory because the SHA gate remains the hard safety boundary. The lease's job is to make the common case (two loops about to collide) resolve to "the second loop waits or skips" instead of "the second loop does the work, then collides at push time."

A lease is not a lock. A distributed lock that both loops trust would require a consistent store, fencing tokens, and a liveness protocol that survives a crashed holder. That is the wrong cost for an ergonomics fix on top of a safety gate that already prevents the dangerous outcome. The lease must fail open: if the lease store is unreachable, the lease is malformed, or no lease exists, the loop proceeds exactly as it does today and the SHA gate catches any real collision. A lease that fails closed would convert a store outage into a workflow outage, which is worse than the conflict it prevents.

## Decision

Adopt a **PR-comment-backed, advisory, fail-open branch-ownership lease** that `pr-autofix` (local) and remote review/autofix routines acquire before committing fix work to a shared PR branch, and release when done. The lease coordinates; the existing Force-Push Safety SHA gate continues to enforce. The lease never replaces the SHA gate and never relaxes it.

The decision has five binding parts.

### 1. Lease storage: a marker comment on the PR

The lease lives in hidden-marker comments on the PR timeline (the PR issue-comment stream, `GET /repos/{owner}/{repo}/issues/{pr}/comments`). This is a new read path the lease introduces; it is not a store `check_pr_live_state.py` already reads. That probe's GraphQL query reads only PR state fields (`state`, `merged`, `isDraft`, `closed`, `headRefName`, `baseRefName`) plus `git cherry` supersession; it reads zero comments. The justification for the comment store is not storage reuse: it is that the timeline is human-visible (satisfying acceptance criterion 3 directly), needs no new infrastructure, and is the cheapest store that records ownership where a maintainer already looks. Each marker comment body carries a machine-parseable block:

```text
<!-- PR-AUTOFIX-LEASE -->
owner: <automation-id>           # e.g. "local:pr-autofix", "remote:coderabbit-autofix", "ci:autofix-workflow"
session: <session-id>            # the holder's session identity (see part 4)
acquired_at: <RFC3339-UTC>       # lease start
expires_at: <RFC3339-UTC>        # acquired_at + TTL
base_sha: <40-hex>               # PR head.sha the holder fetched before acquiring
```

The **latest marker comment wins**: acquire scans the PR timeline for `<!-- PR-AUTOFIX-LEASE -->` comments and treats the most-recent one as authoritative. If that marker's `expires_at` is in the future and its `owner` is not `none`, the lease is live (held). In all other cases (expired, tombstoned, absent) the lock is free. When the lock is free, acquire posts a new marker comment to claim ownership. When the current actor authored the existing live lease comment, it may edit it in place instead (for example, to renew). Release writes a tombstone (`owner: none`, `expires_at` in the past) by editing the actor's own comment or by posting a new tombstone comment when the actor cannot edit the existing marker (different token owner). Because the latest-marker rule evaluates the tombstone directly, the tombstone's `expires_at` being in the past is sufficient to signal the lock is free on the next scan, without relying on the tombstone itself being non-expired. The marker `<!-- PR-AUTOFIX-LEASE -->` makes all lease comments findable by a single bounded timeline scan (latest N comments, see part 3). Acquire keys self-renewal on the *verified GitHub comment author* (the `user.login` the API returns for each comment), not on the body's self-declared `owner`/`session` strings, which are forgeable (see part 3 and Security).

This choice satisfies acceptance criterion 3 directly: "The PR timeline records which automation owns the current fix loop." The lease *is* a timeline record.

### 2. Lease TTL: short, fixed, self-expiring

The lease TTL is 15 minutes. A lease whose `expires_at` is in the past is dead, regardless of any release step. TTL-based expiry is the liveness mechanism: a crashed or killed holder cannot wedge the branch, because the lease evaporates on its own clock. The acquiring loop reads `expires_at`, not a separate heartbeat. A holder that needs more than 15 minutes re-acquires (renews) by editing the comment with a new `expires_at`; renewal is the same operation as acquire and carries the same `base_sha` freshness check (part 3).

15 minutes is chosen to bound the worst-case wait for a blocked loop while comfortably covering a normal autofix cycle (read review, edit, test, commit, push). It is a fixed constant in this decision, not a tunable, to keep the protocol legible. A future ADR may parameterize it if evidence shows the constant is wrong; this ADR commits to the constant so implementers do not each pick their own.

### 3. Concurrency semantics: read-check-write with a SHA freshness guard, fail-open

The lease is advisory and the PR-comment store gives no atomic compare-and-set, so the protocol does not pretend to provide mutual exclusion. It provides a best-effort claim plus a hard freshness guard that defers the real safety decision to the SHA gate.

Acquire (`acquire_lease`):

1. Fetch the PR `head.sha` and the latest N lease comments in one bounded read (N is fixed at 100, the most-recent timeline page; an unbounded scan is rejected so a PR flooded with forged `<!-- PR-AUTOFIX-LEASE -->` comments cannot become an unbounded parse-cost DoS). Note: `check_pr_live_state.py` scans no comments at all, so this bound is a new control this lease adds, not a value copied from that probe.
2. Compute liveness from the **reader's clock**. A marker is live only when `expires_at` is in the future relative to reader-now AND `expires_at <= reader-now + MAX_TTL` (15 minutes). The second condition rejects a forged marker whose timestamps are both far in the future (which would pass a body-relative `expires_at <= acquired_at + MAX_TTL` check yet read as live indefinitely). Any marker claiming liveness beyond `reader-now + MAX_TTL` is treated as "no live lease."
3. If a live lease exists and its **verified comment author** (the `user.login` the API returns for that comment) is not this credential, return `SKIP` with reason `held-by:<owner>` and the `expires_at` so the caller knows when to retry.
4. If a live lease exists and its verified comment author matches this credential (self-renewal), write a new marker comment with `expires_at=reader-now+15m` and `base_sha=<the head.sha just fetched>`. Return `ACT`. Self-renewal keys on the verified author, never on the body's `owner`/`session` fields, which are display/traceability only and forgeable.
5. If no live lease exists (absent, tombstoned, expired, beyond-MAX_TTL, or malformed/unparseable), write the lease comment with this loop's identity, `acquired_at=reader-now`, `expires_at=reader-now+15m`, and `base_sha=<the head.sha just fetched>`. Return `ACT`. A malformed lease is treated as "no live lease" and superseded (see Security).
6. **Fail open.** If the read or write fails (API error, auth error), log the failure and return `ACT` with reason `lease-store-unavailable`. The loop proceeds; the SHA gate is the backstop.

Push-time guard (unchanged plus one addition):

- The existing Force-Push Safety SHA gate runs exactly as today. A lease never authorizes a push; the SHA match still must hold.
- Addition: if this loop holds a live lease whose `base_sha` no longer matches the current PR `head.sha`, the remote advanced under the lease (a racing writer that ignored or did not see the lease, or a fail-open peer). The loop MUST re-sync to the new head and re-run its checks before pushing, and MUST NOT force-push over the newer commit. This is the same recovery path #2615 describes, now reached deliberately rather than by surprise, and reached *before* the fix work in the common case.

Release (`release_lease`): edit the lease comment to a tombstone. Release is best-effort; a missed release is covered by TTL expiry.

Because the store has no atomic CAS, two loops can both pass step 2 and both write in step 4 (a true race in the milliseconds between read and write). This is acceptable: the loser's write simply overwrites the winner's lease comment, both believe they hold the lease, and the SHA gate still prevents the dangerous push. The lease reduces collisions in the overwhelmingly common case (loops staggered by seconds or minutes); it does not claim to eliminate the sub-second race, and the safety gate does not depend on it doing so.

### 4. Owner and session identity

`owner` is a small, fixed vocabulary of automation identities (`local:pr-autofix`, `remote:coderabbit-autofix`, `ci:autofix-workflow`, plus any future loop), so a human reading the timeline sees which automation holds the branch. `session` is the holder's session identity: for a local `pr-autofix` run, the session-log session id already created by `new_session_log.py` (for example `session-2587`); for a CI run, the workflow run id. This resolves the PRD's first blocking question (session-ID source): local runs reuse the existing session-log id rather than generating a fresh UUID, so the lease is traceable back to a session log and its evidence.

`owner` and `session` are display and traceability fields only. They are forgeable (anyone who can comment on the PR can write any `owner`/`session`), so no trust decision keys on them. The trust decision for self-renewal keys on the **verified GitHub comment author** (the `user.login` field the API returns for each comment), which a forger cannot spoof without the holder's credential. The body fields tell a human reader which automation claims the branch; the verified author tells the protocol whose lease it actually is.

### 5. Scope: a phased, reversible rollout; only the protocol is committed here

This ADR commits the protocol and the lease contract. It does not commit an implementation timeline beyond naming the phases, and each phase is independently shippable and reversible:

- **Phase 0 (this ADR).** Record the decision; run the full adr-review debate; obtain human approval. No code.
- **Phase 1 (local-only, additive).** Ship `acquire_lease` / `release_lease` / lease-read helpers and wire them into local `pr-autofix` only. Local runs acquire before fixing and release when done. A local run that sees a remote lease it cannot interpret fails open. Remote loops are unchanged and simply do not participate yet; a non-participating remote loop is exactly today's behavior, so Phase 1 is safe to ship before any remote integration exists.
- **Phase 2 (remote integration, gated on a BOT_PAT permissions audit).** Teach the remote review/autofix routine to acquire and check the lease before pushing. This requires a CodeRabbit/CI capability and credential review (the PRD's second blocking question: BOT_PAT permissions to post and edit lease comments from CI). Phase 2 does not start until that audit confirms the remote loop can both read and write the lease comment. Until then, remote loops are the unleased writers that Phase 1's fail-open and SHA gate already tolerate.

This phasing answers the "remote integration is uncertain" objection: the local half delivers value on its own (a local run that sees a fresh remote-CI lease, once Phase 2 exists, waits instead of colliding), and even before Phase 2, two *local* sessions on the same branch coordinate. The expensive, externally-gated remote half is deferred behind an explicit audit, not assumed.

**Honest Phase 1 value (scope and frequency).** Phase 1 prevents exactly one collision case: two *local* `pr-autofix` sessions working the same PR branch at the same time. That is the only case Phase 1 covers. The single evidenced incident (#2611) is local-vs-remote-CI, which is the Phase 2 case and is *not* prevented by Phase 1. The two-local-session frequency is currently unmeasured; for a single operator it is plausibly rare. The implementer and the human approver buy Phase 1 with eyes open: it is cheap, additive, fully reversible, and lays the protocol groundwork for Phase 2, but its standalone payoff is unproven and may be near zero until Phase 2 lands. The repo's own memory (`pr-review-pr1873-observations`) already recommends "commit and push immediately after each fix" as a local mitigation; the lease is still worth the local-only code because that discipline does not let a *second* local session detect a *first* before doing duplicate work, which the lease does.

**Phase 1 kill criterion (GO/NO-GO).** Baseline: 1 evidenced collision incident (PR #2611) before Phase 1. Observation window: the first 30 days after Phase 1 ships, or the first 50 shared-branch autofix runs, whichever comes first. Success metric source: a structured `lease_collision_blocked` event emitted on each SKIP verdict (the acquire path already returns SKIP with `held-by:<owner>`; instrument it to the session log so the count is queryable). GO (keep Phase 1, proceed to Phase 2 scoping): at least one real two-local-session collision is blocked in the window, OR the Phase 2 BOT_PAT audit completes and Phase 2 work begins. NO-GO (revert Phase 1 rather than carry dead coordination code): zero collisions blocked in the window AND the Phase 2 audit has not started by the window's end. NO-GO removes the lease helpers and the `pr-autofix` wiring; because Phase 1 is additive and fail-open, removal returns the workflow to exactly today's behavior with no migration.

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
- **What are the risks of change?** A fail-closed lease could turn a comment-store outage into a workflow outage. Mitigated by the mandatory fail-open semantics (part 3, step 5). A lease that callers trust as a hard lock would create a false safety story. Mitigated by keeping the SHA gate as the only hard boundary and documenting the lease as advisory.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep only the SHA gate (status quo) | Zero new machinery; safety already guaranteed; nothing to fail open | Does not coordinate; wasted work and conflict cost recur every collision (#2611) | Does not address the stated problem; the cost issue #2615 names is real and unmitigated |
| Pre-fix SHA recheck (re-fetch `head.sha` immediately before starting fix work; abort/re-sync if it advanced) | Zero new store, zero parser, zero injection surface; moves the existing SHA check earlier in the loop; captures the loser-detects case | The SHA only advances *after* the first loop pushes, so a pre-fix recheck cannot detect a peer that has started but not yet pushed; both loops still start duplicate work and only the second-to-push detects | Insufficient on its own: it is a strict subset of the lease's value. The lease's load-bearing edge is exactly this gap, the second loop sees the first is *active* before either pushes, which a SHA recheck cannot. The lease should run the pre-fix SHA recheck as its Phase 1 floor and add the active-claim signal on top |
| Git-notes lease (`refs/notes/pr-autofix-lease`) | Lives with the repo; survives without the API; diffable | Notes are not in the PR timeline (fails acceptance criterion 3); fetch/push of the notes ref adds git plumbing both loops must run; remote CI rarely fetches notes | Invisible to the timeline; heavier for the remote loop than a comment |
| External lock store (Redis, a DB, a lock service) | Real atomic CAS; fencing tokens possible | New infra to operate; an outage fails the workflow unless it fails open, at which point it is no stronger than a comment; disproportionate to an ergonomics fix on a working safety gate | Wrong cost; the SHA gate already prevents the dangerous outcome, so strong mutual exclusion is not required |
| Branch-name convention / protected branches | No store; GitHub-native | Cannot express "actively being fixed right now" with a TTL; blocks pushes wholesale rather than coordinating a short fix window | Does not model a short-lived, expiring claim |
| **PR-comment lease, advisory, fail-open, TTL (chosen)** | Reuses the ACT/SKIP verdict-gate *pattern* from `check_pr_live_state.py` (not its store); satisfies the "timeline records owner" criterion directly; human-visible store with no new infra; fail-open keeps a store outage from becoming a workflow outage; TTL self-heals a crashed holder | Adds a new comment-timeline read path; no atomic CAS, so the sub-second acquire race is possible; dual representation (lease comment plus SHA gate); release is best-effort | Chosen: matches the existing gate pattern, meets all three acceptance criteria, and the residual race is fully absorbed by the unchanged SHA gate |

### Trade-offs

The chosen design accepts that the lease is best-effort, not a true lock. It buys collision *reduction* in the common case (loops staggered by seconds to minutes) for near-zero cost and zero new infrastructure, and it deliberately does not attempt the much more expensive *elimination* of the sub-second race, because the SHA gate already makes that race harmless to safety. It accepts a dual representation (the advisory lease comment plus the authoritative SHA gate) and keeps the SHA gate as the single hard boundary, so a reader never has to ask "which mechanism actually protects the branch." The TTL trades a bounded worst-case wait (up to 15 minutes for a blocked loop) for crash-safety without a heartbeat protocol.

## Consequences

### Positive

- The common collision (two loops about to fix the same branch, staggered by more than a sub-second) is resolved before the fix work: the second loop sees the lease and SKIPs or waits, instead of doing duplicate work and colliding at push time. This directly removes the #2611 cost.
- The PR timeline records which automation owns the current fix loop (acceptance criterion 3), via the lease comment itself.
- The coordination layer reuses the `check_pr_live_state.py` ACT/SKIP probe *pattern* (exit 0 = ACT, exit 1 = SKIP, within the ADR-035 range), so it is legible to anyone who already understands the pre-action gate. It does not reuse that probe's storage; the lease adds its own comment-timeline read path.
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
- **Enforce MAX_TTL against the reader's clock, not the forgeable `acquired_at`.** Liveness is computed at the reader. A marker is live only when `expires_at` is in the future relative to reader-now AND `expires_at <= reader-now + MAX_TTL` (15 minutes). A body-relative check (`expires_at <= acquired_at + MAX_TTL`) alone is bypassable: a forger sets `acquired_at` and `expires_at` 15 minutes apart but both far in the future (for example 2030-01-01), passing the relative check while reading as live indefinitely (CWE-400 resource exhaustion / CWE-367 time-of-check). The reader-clock bound caps any marker to at most one TTL of liveness from the instant it is read, so the "self-DoS bounded to one TTL" guarantee actually holds. The parser still applies the relative `expires_at <= acquired_at + MAX_TTL` check to reject internally-inconsistent markers; the reader-clock bound is the one that defeats far-future forgery.
- **Key self-renewal on the verified comment author (CWE-345 origin validation).** The "is this my lease" decision keys on the GitHub comment author (`user.login` from the API, the credential that posted the comment), never on the body's self-declared `owner`/`session` strings. Those body fields are forgeable: anyone who can comment can write `owner: local:pr-autofix, session: session-2587`. If self-renewal trusted the body, a forger could get its comment edited or trusted as the holder's own lease. Keying on the verified author means a forged body can at most appear as a *foreign* live lease (causing the legitimate loop to SKIP, a bounded self-DoS), never as the loop's own lease.
- **Bound the timeline scan.** Acquire reads at most the latest N (100) comments, not the full timeline. A PR flooded with forged `<!-- PR-AUTOFIX-LEASE -->` comments cannot turn the acquire path into an unbounded parse-cost DoS (CWE-400). This is a new control the lease adds; `check_pr_live_state.py` scans no comments, so there is no existing window to inherit.
- **The lease is not an authorization.** Acquiring a lease never authorizes a push. The SHA gate, which compares real git SHAs, is the only thing that gates a push. A forged lease (anyone who can comment on the PR can write `<!-- PR-AUTOFIX-LEASE -->`) can at most cause a peer loop to SKIP or wait, a denial-of-service on the autofix loop, bounded by MAX_TTL enforcement above. It can never cause an overwrite, because the SHA gate is independent of the lease. This is the deliberate reason the lease is advisory: it keeps the forgeable signal away from the safety decision.
- **No auto-fetch of lease content.** The lease carries no URLs and the parser fetches nothing. `base_sha` is compared, not dereferenced.
- **Bounded blast radius of forgery.** With MAX_TTL parse enforcement, the worst a forged lease achieves is a self-DoS on the fix loop for at most one TTL (15 minutes). Phase 2's BOT_PAT audit must confirm the remote loop's credential can edit lease comments without escalating any other permission.

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
2. **Phase 1 (local-only).** Ship the lease helpers and wire them into local `pr-autofix`. Acquire before fix work, release after push (or on early exit). Fail open on any store error. pytest covers: live lease held by another owner returns SKIP; expired lease returns ACT and overwrites; missing lease returns ACT; malformed lease returns ACT and overwrites (treated as "no live lease"); self-renewal of own live lease returns ACT and extends `expires_at`; store error returns ACT (fail-open); `base_sha` mismatch at push time triggers re-sync. Document in `pr-autofix.md` and `autonomous-pr-monitor.md`.
3. **Phase 2 (remote integration, gated).** After a BOT_PAT permissions audit confirms the remote loop can read and write lease comments, teach the remote routine to acquire/check the lease before pushing. Do not start until the audit passes.

**Success metric.** Count of two-local-session collisions blocked, measured from a structured `lease_collision_blocked` event emitted on each acquire SKIP verdict and written to the session log (the acquire path already returns SKIP with `held-by:<owner>`; Phase 1 instruments it so the count is queryable, establishing the baseline that does not exist today). Target: at least one real collision blocked within the kill-criterion window (Decision part 5), with zero force-push overwrites in any phase (the SHA gate guarantee preserved). The kill criterion in Decision part 5 is the GO/NO-GO rule tied to this metric. If Phase 2's audit fails and Phase 1 blocks zero collisions in the window, Phase 1 is reverted, not carried as dead code.

## Related Decisions

- ADR-035 (exit-code standardization): the lease helpers stay within the ADR-035 range (0 success, 2 usage/config, 3 external, 4 auth). The exit-1 = SKIP meaning is NOT from ADR-035 (ADR-035 defines exit 1 as "General error / Validation failure / logic"); it is the script-specific ACT/SKIP convention defined by `check_pr_live_state.py`'s own docstring (exit 0 = ACT, exit 1 = SKIP), which itself overloads ADR-035's exit 1. The lease mirrors that sibling's convention, not a literal ADR-035 1=skip mapping. **Different than canonical:** ADR-035's exit 1 = logic error is overloaded here to exit 1 = SKIP, matching `check_pr_live_state.py`; do not re-derive ADR-035's literal table for this script. PR-not-found uses exit 2 (usage/config), aligning with ADR-035.
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
- `.agents/critique/ADR-076-debate-log.md`. The 6-agent adr-review debate (2026-06-19, 6 APPROVE-WITH-CHANGES, 0 BLOCK) whose must_fix items this revision addresses.
- RFC 3339 (timestamp format for `acquired_at` / `expires_at`): <https://www.rfc-editor.org/rfc/rfc3339>
