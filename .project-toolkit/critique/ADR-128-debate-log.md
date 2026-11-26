# ADR Debate Log: ADR-128 receipts Copilot block-once hook

## Summary

- **Rounds**: 3 of 10
- **Prior debate log**: none. This is the first debate on ADR-128.
- **Claims ledger**: `.project-toolkit/critique/ADR-128-claims-ledger.md`
- **Outcome**: Consensus (round 3: 6 of 6 Accept or Disagree-and-Commit). Under ADR-101 the panel counts as one vote; owner acceptance is the binding gate.
- **Final Status**: proposed. The owner has not accepted ADR-128. Frontmatter stays `status: proposed`.
- **Subject**: new ADR-128, drafted 2026-11-25 from REQ-050. It adds a `receipts` `agentStop` hook on Copilot CLI that blocks once per contradicted claim.
- **Trigger**: owner decision D9 on 2026-11-25 ("Block, gate, ADR"), tracked in issue #7633.
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). The ADR governs a blocking hook and a rule that tests read.
- **Companion log**: `.project-toolkit/critique/ADR-084-debate-log-3.md` covers ADR-084 rule 2b, which this ADR depends on.

## Phase 0 and seat limits

- The author searched related work before drafting. Draft PR #7631 holds the spike record. Issue #7633 tracks the work. Ledger row 37 records that `origin/main` held no ADR-128 on 2026-11-25.
- The analyst seat had no GitHub or git tool. The Phase 0 GitHub search did not run in that seat.
- No seat could read the author's local Copilot logs. Ledger rows 5, 7, 8, and 9 are UNAVAILABLE to a reviewer.
- The security seat did not read the full ledger in round 2.
- One author wrote the ADR, answered the findings, and ran the panel. The panel is not independent proof.

## Gate escapes

None. No panel finding contradicted a VERIFIED ledger row.

One error escaped the generator gates and the panel. Ledger rows 5, 7, 8, and 9 first rested on a scan capped at 3,000 files (2,115 runs, 49 blocks, 25 false). The author found the cap on 2026-11-25 while answering round 1. A full count of 11,160 files replaced it under owner decision D12. No seat could have caught it, because the logs are outside the repository.

## Round 1 Summary

### Agent Positions

| Agent | Position | Head finding |
|-------|----------|--------------|
| architect | Block | The ADR contradicts ADR-084 rule 2a and names no amendment vehicle. |
| critic | Block | Same rule 2a conflict. |
| independent-thinker | Disagree-and-Commit | The registration gate may be unreachable. |
| security | Disagree-and-Commit | No P0. Six P1 items. |
| analyst | Disagree-and-Commit, else Block | ADR-084 conflict and gate reachability. |
| high-level-advisor | Block | The open question is owner acceptance, not drafting. |

Tally: 3 Block, 3 Disagree-and-Commit. No consensus.

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| P0-1 | P0 | architect, critic, analyst, security, high-level-advisor | ADR-128 said it did not amend ADR-084, yet a blocking Copilot hook breaks rule 2a. Owner decision D10 on 2026-11-25 added rule 2b to ADR-084 in the same change. |
| P0-2 | P0 | independent-thinker, analyst | Zero contradicted stamps in 678 spike runs. Thirty real contradictions may never arrive. Owner decision D11 on 2026-11-25 set an offline replay of the owner's own logs, with `review-by` 2027-02-25. If unmet, the hook stays unregistered and the ADR is reviewed again. |

### Major Changes Made

- ADR-084 gained rule 2b and an amendment entry.
- ADR-128 Decision 7 now names the offline replay and the date.
- ADR-128, REQ-050, the ledger, and the issue #7633 draft body now carry the full-count numbers (D12).

### Strategic checklist

| Lens | Assessment |
|------|------------|
| Chesterton's Fence | FAIL. The ADR changed rule 2a's effect without saying so. |
| Path Dependence | PASS |
| Core vs Context | N/A |
| Second-System Effect | FAIL |
| Overall | CONCERNS |

## Round 2 Summary

### Agent Positions

| Agent | ADR-128 | ADR-084 rule 2b |
|-------|---------|-----------------|
| architect | Disagree-and-Commit | Disagree-and-Commit |
| critic | Disagree-and-Commit | Disagree-and-Commit |
| independent-thinker | Disagree-and-Commit | Disagree-and-Commit |
| security | Disagree-and-Commit | Disagree-and-Commit |
| analyst | Disagree-and-Commit | Disagree-and-Commit |
| high-level-advisor | Disagree-and-Commit | Accept |

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| P0-1 | P0 | round 1 | Resolved. Rule 2b is the vehicle. |
| P0-2 | P0 | round 1 | Resolved by procedure only. The date ends the wait. The pool may still hold fewer than 30 contradicted stamps. |
| R2-1 | P1 | architect, critic, analyst | Rule 2b said the hook met condition c, yet the message carries a tool name. Rule 2b now names the bounded tool-name echo as a departure from c for both registrations. |
| R2-2 | P1 | independent-thinker, security, critic | The bound is one block per claim, not per session. Rule 2b and ADR-128 now say so, with no session cap. The cap itself is deferred (below). |
| R2-3 | P1 | architect, analyst, critic | Rule 2b cited owner decision D10, and REQ-050 stopped at D9. REQ-050 Open questions now lists D3 to D12. |
| R2-4 | P2 | architect | Rule 2b now gives the reason for `copilotExclude` and names the owning record. |
| R2-5 | P2 | high-level-advisor | ADR-128 Decision 1 now agrees with rule 2b on the 80-character claim echo. |
| R2-6 | P2 | analyst | Three ADR claims had no ledger row. Rows 34 to 36 cover them. |
| R2-7 | P2 | architect, critic, analyst | Both ADRs cited debate logs that did not exist. This log and the companion log close that. |
| R2-8 | P2 | security | An oversized transcript suppresses all checks. That fails safe. Documented. |

The security seat reported on its round 1 P1 items: the tool-name pattern and the kill switch off values are resolved. Marker permissions and the marker size cap are partly resolved and are deferred (below).

### Major Changes Made

- ADR-128 Decisions 1 and 3 and the Trade-offs section were updated.
- Ledger rows 32 to 37 were added for claims the edits introduced.

### Strategic checklist

| Lens | Assessment |
|------|------------|
| Chesterton's Fence | PASS |
| Path Dependence | PASS |
| Core vs Context | PASS, with a caveat: no evidence of consumer demand. |
| Second-System Effect | PASS |

## Round 3 Summary

Round 3 was a convergence check on the text changed after round 2.

### Agent Positions

| Agent | ADR-128 | ADR-084 rule 2b |
|-------|---------|-----------------|
| architect | Disagree-and-Commit | Accept |
| critic | Disagree-and-Commit | Disagree-and-Commit |
| independent-thinker | Disagree-and-Commit | Accept |
| security | Disagree-and-Commit | Disagree-and-Commit |
| analyst | Disagree-and-Commit | Disagree-and-Commit |
| high-level-advisor | Disagree-and-Commit | Accept |

No seat found a new factual error.

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| R3-1 | P2 | critic, independent-thinker | ADR-128 Trade-offs said "stops" where other lines say "`agentStop` runs". Fixed. |
| R3-2 | P2 | critic, security, high-level-advisor | "All on builds 1.0.79 and earlier" cannot be checked by a seat. It rests on ledger row 8, which is UNAVAILABLE to a reviewer. Documented. |
| R3-3 | P2 | security, analyst | REQ-050 line 24 says "D1 to D12" and the list starts at D3. D1 and D2 predate the spec. Documented, not changed. |
| R3-4 | P2 | independent-thinker | Rule 2b does not say whether "no session cap" meets rule 2a condition g. Documented in the companion log. |
| R3-5 | P2 | high-level-advisor | The seat did not verify the round 1 tally cited in the ADR-084 amendment entry. This log records that tally above. |

## Deferred P1 and P2 items

Justification for every deferral: the Copilot hook stays unregistered until the gate passes and the owner accepts rule 2b. No block is live while these stay open. Several items would change owner decisions D9 or D11, so the panel cannot settle them.

| Item | Source | Where it lands |
|------|--------|----------------|
| A hard cap on blocks per session | independent-thinker, security, critic | Owner decision. It changes D9. |
| Limit the replay pool to runs with a readable `transcriptPath` | independent-thinker, critic, analyst, high-level-advisor | Owner decision. It changes D11. |
| Require stamps from distinct sessions | analyst | Owner decision. It changes D11. |
| Require a fresh, blind draw that excludes sessions used to tune the engine | critic, architect, independent-thinker | Owner decision. It changes D11. |
| Count contradicted stamps in the pool before the gate starts | independent-thinker, high-level-advisor | Owner decision. It changes D11. |
| A live probe on Copilot 1.0.116 as a gate item | critic | Owner decision. It changes D11. |
| A separate sunset for each registration | architect | Owner decision. |
| A generator test for the Claude tree and a pinned Copilot Stop set | architect | Build slice. |
| Marker path, ownership and symlink checks, size cap value, layout, and pruning | security, critic | Build slice. |
| A missing session id counts as an unwritable marker | security | Build slice. |
| Strip control characters from the 80-character claim echo | security, critic | Build slice. |
| Known-tool allowlist, keyed digest, and concurrent double-block handling | security | Build slice. |
| Acceptance criteria for ADR-128 Decisions 4 and 6 | critic | REQ-050, before the build slice. |

## Dissent

These reservations stand behind the Disagree-and-Commit votes.

- All six seats in round 3: one block per claim has no session cap. A reply with many contradicted claims blocks many times.
- architect, analyst, high-level-advisor: nobody has counted contradicted stamps in the pool. The gate may be unreachable.
- security: a missing session id is not yet treated as an unwritable marker.
- analyst: the registration gate is the only mitigation for a block whose cost nobody has measured.
- independent-thinker: one judge labels the stamps unblinded, and that judge is the author.
- independent-thinker: the replay reads `events.jsonl` and the live hook reads `transcriptPath`. Nothing shows the two match.
- analyst: stops in one session correlate. That weakens the independence the Wilson bound assumes.
- high-level-advisor: the Copilot half may never ship while ADR-084 carries a blocking exception for it.

## Next Steps

- The owner decides whether to accept ADR-128 and ADR-084 rule 2b.
- The owner decides the seven deferred items marked "Owner decision".
- The build slices carry the items marked "Build slice".
