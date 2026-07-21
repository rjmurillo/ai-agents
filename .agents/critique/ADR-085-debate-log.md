# ADR Debate Log: Cross-Harness Permission-Surface Asymmetry

## Summary

- **Review date**: 2026-07-20
- **Scope**: Superseding security amendment to ADR-085
- **Rounds**: 4
- **Outcome**: Consensus
- **Final status**: accepted

This log records the review that followed the owner's explicit decision to
supersede D-B. The historical initial review remains at
`.agents/analysis/ADR-085-permission-surface-debate.md`. That file records why
the first decision kept test auto-approval. It is not rewritten to imply that
the later runner-name trust finding existed during the initial review.

## Related Work

| Item | State on 2026-07-20 | Relevance |
|------|---------------------|-----------|
| #2295 | Closed | Original Copilot hook spawn incident and dispatcher motivation |
| #3197 | Open, blocked | Vendored-hook reduction program |
| #3217 | Open | Owns the remaining `skill_first_guard` terminal state |
| #3218 | Open, blocked | Owns retirement of machinery with zero active hook consumers |
| PR #3259 | Open, conflicting | Replaces `.githooks` with Lefthook, so git hooks cannot be named as a raw-command interceptor |

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
| independent-thinker | Disagree-and-Commit | Accepted the decision with non-blocking reservations |
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

- D-A remains unimplemented. #3217 must select and prove one terminal state.
- The generic PermissionRequest adapter remains dormant. Any producer requires a
  new security review and refreshed host-contract evidence.
- #3218 remains blocked until it derives a zero-consumer inventory from every
  active source registration and generated manifest.
- Full MADR headings were not added because the repository's current ADR format
  already carries the decision, consequences, rollback, and confirmation data.

## Strategic Assessment

- **Chesterton's Fence**: Pass. The initial auto-approval purpose and later trust
  failure are both recorded.
- **Path dependence**: Pass. The decision separates current Copilot evidence from
  future permission-surface changes.
- **Core vs context**: Pass. Dogfood-only steering and unsafe prompt reduction do
  not justify vendored customer surface.
- **Second-system effect**: Pass. The ADR rejects a dual-surface replacement and
  does not add a new permission framework.
