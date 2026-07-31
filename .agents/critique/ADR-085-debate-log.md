# ADR Debate Log: Cross-Harness Permission-Surface Asymmetry

## Summary

- **Review date**: 2026-07-20
- **Scope**: Lefthook framework amendment, then superseding security amendment
- **Rounds**: 2 framework rounds plus 4 security rounds
- **Outcome**: Consensus
- **Final status**: accepted

This log combines two accepted-state amendment reviews. PR #3259 first updated
D-A after Lefthook replaced the custom Git-hook framework. The later security
review followed the owner's explicit decision to supersede D-B. The historical
initial review remains at
`.agents/analysis/ADR-085-permission-surface-debate.md`. That file records why
the first decision kept test auto-approval. It is not rewritten to imply that
the later runner-name trust finding existed during the initial review.

## 2026-07-31 Issue #3217 and #3218 Closure Amendment

### Scope

Issue #3217 closed on 2026-07-28 after repository evidence showed
`observation_sync` is absent from plugin registrations and vendored trees, while
Git hooks and CI cannot observe its MCP event. Issue #3218 closed the same day
after repository evidence showed its retirement premise was wrong. The
amendment records both reviews as complete and requires a new architecture
decision for future simplification.

Sources:
<https://github.com/rjmurillo/ai-agents/issues/3217> and
<https://github.com/rjmurillo/ai-agents/issues/3218>.

### Roles and Vote Record

| Agent | Vote |
|-------|------|
| architect | Accept |
| critic | Disagree-and-Commit |
| independent-thinker | Accept |
| security | Accept |
| analyst | Accept |
| high-level-advisor | Accept |

### Resolution

The amendment corrected stale issue state and ownership language, retained
`implemented: true`, and preserved all prior owner decisions and security
findings. The critic accepted the result while recording that `implemented`
covers this ADR's terminal states, not future dispatcher simplification under a
new decision. Existing debate history remains unchanged.

## Related Work

| Item | State on 2026-07-20 | Relevance |
|------|---------------------|-----------|
| #2295 | Closed | Original Copilot hook spawn incident and dispatcher motivation |
| #3197 | Open, blocked | Vendored-hook reduction program |
| #3217 | Open | Owns the remaining `skill_first_guard` terminal state |
| #3218 | Open, blocked | Owns retirement of machinery with zero active hook consumers |
| PR #3259 | Merged | Replaced `.githooks` with Lefthook and triggered the D-A framework amendment |
| PR #3293 | Merged | Selected and implemented D-A Retirement |
| ADR-086 | Accepted | Records the Lefthook migration and makes custom-hook paths historical evidence |

This table preserves the 2026-07-20 review snapshot. The 2026-07-31 amendment
above records the current #3217 and #3218 states.

## Lefthook Framework Amendment Review

### Phase 1 Findings

The six reviewers agreed that active references to the deleted custom Git-hook
framework had to change. Five reviewers also found that replacing the path with
Lefthook or CI implied behavior equivalence that does not exist:

- `skill_first_guard` runs before a raw `gh` command through PreToolUse.
- Lefthook runs on Git events.
- CI runs after repository or pull-request events.
- Neither replacement can observe or prevent an arbitrary raw `gh` command
  before execution.

Reviewers also found stale #3218 survivor accounting, unresolved owner-decision
wording, incomplete ADR-083 security-control inventory, and no canonical debate
artifact under `.agents/critique/`.

### Framework Round 1

Changes made:

- Added a PR #3259 amendment record.
- Reframed D-A as removal from the vendored surface, not an equivalent
  relocation.
- Required #3217 to identify any observable repository-state invariant, its
  trigger, failure behavior, and acceptance test.
- Required #3217 to record retirement of pre-execution blocking when no approved
  agent-time carrier exists.
- Corrected #3218 retained-consumer accounting and included ADR-083 security
  controls.
- Corrected owner-decision wording, trade-offs, consequences, dependent
  components, and implementation notes.

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | Structure, traceability, and survivor accounting were corrected. |
| critic | Accept | False carrier equivalence and stale decision wording were removed. |
| independent-thinker | Block | ADR-084 still appeared to require relocation without an observable invariant. |
| security | Accept | Timing loss and required evidence were explicit. |
| analyst | Accept | Claims aligned with ADR-083, ADR-084, ADR-086, and repository state. |
| high-level-advisor | Accept | The amendment stayed within the owner-ratified D-A decision. |

### Framework Round 2

Decision 2 narrowed ADR-084 rule 4 for this guard. Moving internal policy to
Lefthook or CI applies only when Git or workflow state exposes an enforceable
invariant. When none exists, explicit retirement satisfies the non-vendoring
purpose. A post-execution gate that cannot observe or prevent the original
action does not.

All six roles voted Accept after this correction. A final consistency pass also
returned 6 Accept votes. The framework amendment reached consensus with no open
P0 or P1 findings.

## Decision Sequence

1. The initial review established that Copilot lacks a documented,
   repo-committed fine-grained permission file and that Claude
   `permissions.allow` loses the hook's metacharacter screening.
2. The owner initially chose keep-as-hook for D-B.
3. The security amendment added Finding 3: runner names do not establish a
   trust boundary because runners load and execute repository-controlled code.
4. The owner reviewed the direct conflict and selected deletion for D-B.
5. The implementation removed the producer, both harness registrations,
   generated PermissionRequest artifacts, and producer-specific tests. It did
   not add a `permissions.allow` replacement.

## Round 1

### Agent Positions

| Agent | ADR-085 position | Main finding |
|-------|------------------|--------------|
| architect | Disagree-and-Commit | Missing amendment log, incomplete safety criterion, and ambiguous D-A completion |
| critic | Block | Accepted status lacked the required critique artifact |
| independent-thinker | Accept | Decision and evidence were sound; MADR shape remained a P2 concern |
| security | Accept | Unsafe approval path was removed and no replacement policy remained |
| analyst | Disagree-and-Commit | Missing amendment log and incomplete `#3218` consumer inventory |
| high-level-advisor | Disagree-and-Commit | Missing amendment log prevented a clean audit trail |

Round 1 tally: **2 Accept, 3 Disagree-and-Commit, 1 Block**.

### Consolidated Issues

| Issue | Priority | Resolution |
|-------|----------|------------|
| The superseding amendment cited a missing critique log | P0 | This file supplies the required accepted-state evidence |
| Portability and fidelity could admit an unsafe underlying policy | P1 | Decision 1 now requires policy safety as a third condition |
| D-A allowed two outcomes without a completion contract | P1 | Decision 2 now defines two terminal states and evidence for each |
| `#3218` named only the hooks discussed by ADR-085 | P1 | Confirmation now requires inventory from every active registration and manifest |
| The original 2027-01-20 timer no longer fit deletion | P2 | ADR records that deletion retires the keep-as-hook timer |
| Full MADR headings and metadata are not used | P2 | Existing repository ADR format retained; no decision ambiguity results |

## Corrections Before Convergence

- Added the official Copilot permission guide, configuration guide, and a
  bounded 1.0.72-1 help inventory to the harness reference.
- Added policy safety to the hook-to-permissions eligibility test.
- Defined repository-only-carrier and retirement as the only valid D-A terminal
  states. A git-hook or CI claim of raw-command equivalence qualifies as neither.
- Required `#3218` to derive its consumer inventory from all current source
  registrations and generated manifests.
- Added semantic tests that reject any Claude or Copilot PermissionRequest event
  registration, not only the removed producer file name.

## Convergence

### Round 2

| Agent | Position | Remaining position |
|-------|----------|--------------------|
| architect | Accept | No unresolved P0 |
| critic | Accept | No unresolved P0 |
| independent-thinker | Block | The provisional log still said the accepted-state review was pending |
| security | Block | The provisional log still said the accepted-state review was pending |
| analyst | Disagree-and-Commit | No unresolved P0 |
| high-level-advisor | Block | The provisional log still said the accepted-state review was pending |

Round 2 did not converge. The three blockers identified one process-state
contradiction, not a technical or security defect. ADR-085 is temporarily marked
`proposed` while the amendment review remains open. Round 3 decides whether the
record may return to `accepted`.

### Round 3

Round 3 found that the log header still said `Final status: accepted` while the
review remained open. Four roles accepted or disagreed-and-committed on the
substance. The remaining blockers rejected the premature status claim. The
header was corrected to `Current status: proposed`.

### Round 4 Final Votes

| Agent | Position | Remaining position |
|-------|----------|--------------------|
| architect | Accept | No unresolved P0 |
| critic | Accept | No unresolved P0 |
| independent-thinker | Disagree-and-Commit | Original output did not enumerate the reservation; this evidence loss is recorded rather than reconstructed |
| security | Accept | Unsafe approval path remains removed |
| analyst | Accept | Evidence and current artifacts align |
| high-level-advisor | Accept | Ready to return to accepted status |

Final tally: **5 Accept, 1 Disagree-and-Commit, 0 Block**. Consensus reached.

## Issue Resolution Summary

| Priority | Count | Resolved | Deferred |
|----------|-------|----------|----------|
| P0 | 1 | 1 | 0 |
| P1 | 3 | 3 | 0 |
| P2 | 2 | 2 documented | 0 |

## Accepted Residuals

- D-A was unimplemented at this review point. PR #3293 later selected and
  implemented Retirement.
- The generic PermissionRequest adapter remains dormant. Any producer requires a
  new security review and refreshed host-contract evidence.
- #3218 remains blocked until it derives a zero-consumer inventory from every
  active source registration and generated manifest.
- Full MADR headings were not added because the repository's current ADR format
  already carries the decision, consequences, rollback, and confirmation data.
- The original Round 4 D&C output did not retain its specific reservation. Later
  review records the gap but does not invent historical dissent.

## Strategic Assessment

- **Chesterton's Fence**: Pass. The initial auto-approval purpose and later trust
  failure are both recorded.
- **Path dependence**: Pass. The final decision separates current Copilot
  evidence from future permission-surface changes. The process was path-dependent
  and records the initial keep decision before the later security reversal.
- **Core vs context**: Pass. Dogfood-only steering and unsafe prompt reduction do
  not justify vendored customer surface.
- **Second-system effect**: Pass. The ADR rejects a dual-surface replacement and
  does not add a new permission framework.

## 2026-07-21 Post-Merge Reconciliation (Historical Snapshot)

The review reconciled the accepted ADR with PR #3259 and PR #3293 on
`origin/main`.

- D-A now records the implemented Retirement terminal state.
- D-B remains deleted with semantic absence regressions.
- Finding 3 now names its later discovery point and causal role.
- The reviewed dispatcher inventory was 26 source registrations across six
  events. This value is historical, not current inventory.
- Historical D&C detail remains unavailable and is labeled as evidence loss.

## 2026-07-21 Final Reconciliation Convergence (Historical Snapshot)

The six roles reviewed the accepted ADR against absolute worktree bytes after a
stale Serena/LSP index returned deleted files from another worktree. Filesystem
checks and explicit absence regressions confirm D-A Retirement and D-B deletion
across Claude registrations, Copilot registrations, source files, generated
shims, and dedicated tests.

### Final Votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | No P0 or P1 remained. |
| critic | Accept | `implemented: false` remains conservative while the #3218 rescope is open. |
| independent-thinker | Accept | The Copilot permission-surface revisit trigger remains reactive. |
| security | Accept | The dormant adapter and CVSS privilege assumption remain documented residuals. |
| analyst | Accept | Finding 3 chronology, evidence loss, and current artifacts align. |
| high-level-advisor | Accept | D-A and D-B are complete; #3218 still owns the remaining implementation state. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. No P0 or P1
finding remained.

## 2026-07-22 PR #3292 Release Convergence

The six roles reviewed the final post-purge hook inventory, dormant adapter
decision, and issue #3218 completion criteria against current registrations and
generated artifacts.

### Corrections verified

- `skill_first_guard`, `test_auto_approval`, and vendored
  `observation_sync` registrations remain absent.
- The vendored surface retains only `markdownlint_guard` and
  `markdown_auto_lint`.
- A zero-consumer component must be removed unless a named accepted decision
  plus dedicated tests retains it.
- Decision 3 explicitly retains the dormant PermissionRequest adapter. Its
  removal requires a superseding decision, not an empty current inventory.
- Inventory alone cannot complete #3218. The issue owns component retirement,
  parity, translation, and drift review.

### Final votes

| Agent | Vote | Remaining position |
|-------|------|--------------------|
| architect | Accept | Survivor disposition and completion criteria align. |
| critic | Accept | The dormant-adapter contradiction is closed. |
| independent-thinker | Accept | Inventory-only closure is no longer possible. |
| security | Accept | Unsafe approval and unrequested vendored execution stay removed. |
| analyst | Accept | Current files and absence regressions match the ADR. |
| high-level-advisor | Accept | Named-decision retention preserves accountability. |

Final tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**. No P0 or P1
finding remained.
