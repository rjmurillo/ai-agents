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

- Phase 0 GitHub search: the six round 1 seat reports record no search of issues or pull requests. The analyst reported its GitHub tools unavailable.
- Draft PR #7631 holds the spike record. Issue #7633 tracks the work. Ledger row 37 records that `origin/main` held no ADR-128 on 2026-11-25.
- The analyst seat had no GitHub or git tool. It searched repository files only. It listed the PR #2205 retro, PR #3372, two Serena memories, and the harness contract reference.
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
| P0-1 | P0 | architect, critic, analyst, high-level-advisor as P0; security, independent-thinker as P1 | ADR-128 said it did not amend ADR-084, yet a blocking Copilot hook breaks rule 2a. Owner decision D10 on 2026-11-25 added rule 2b to ADR-084 in the same change. The independent-thinker proposed shipping under rule 1 with no amendment. D10 chose rule 2b. |
| P0-2 | P0 | independent-thinker, analyst | Zero contradicted stamps in 678 spike runs. Thirty real contradictions may never arrive. Owner decision D11 on 2026-11-25 set an offline replay of the owner's own logs, with `review-by` 2027-02-25. If unmet, the hook stays unregistered and the ADR is reviewed again. |
| R1-1 | P1 | security, analyst; architect as P2 | A tool name from the transcript enters the block reason. Resolved. Decision 6 prints a name only when it matches `^[A-Za-z0-9_.-]{1,48}$`. The architect's closed list of names is deferred. |
| R1-2 | P1 | security, critic; analyst as P2 | The marker had no permission, symlink, naming, cap, or pruning rule. Partly resolved. Decision 4 sets modes 0700 and 0600, `O_NOFOLLOW`, an atomic append, and a size cap. The cap value, file naming, pruning, value normalization, and a location test are deferred. |
| R1-3 | P1 | security | Decision 4 says the marker holds no claim value. A plain SHA-256 over guessable inputs lets a local reader confirm a guess. Not resolved. Decision 4 keeps its wording. The keyed digest is deferred. |
| R1-4 | P1 | security, critic | No cap on blocks per session, and the reason asserts a contradiction. Not resolved. The cap is deferred to the owner. The softer reason wording is deferred. |
| R1-5 | P1 | security | The 5 s deadline and the read cap sit outside the Decision list. No Copilot hook timeout is set. Partly resolved. REQ-050 AC-6 and AC-7 carry the byte cap and the deadline. A 64 MB cap value and a registration timeout are deferred. |
| R1-6 | P1 | architect | Two pinned tests in `tests/hooks/test_plugin_stop_registration.py` fail when a registration lands. Resolved. Prior Art and the Impact table name both tests. Rule 2b requires the update in the same change. |
| R1-7 | P1 | architect | ADR-128 applies ADR-084 rules 1 and 5 only. Rules 3 and 4 are not walked. Not resolved. Deferred. |
| R1-8 | P1 | architect | The rule 1 claim rests on argument. Partly resolved. The ADR-084 amendment entry says it claims no consumer demand. ADR-128 "Why Change Now" was not changed. |
| R1-9 | P1 | architect, high-level-advisor, analyst | The gate did not name its pool. Resolved by D11. Decision 7 names an offline replay of the owner's Copilot `events.jsonl` logs. |
| R1-10 | P1 | architect, high-level-advisor, analyst, critic; security as P2 | `review-by` was null, and an unmet gate had no end. Resolved by D11. `review-by` is 2027-02-25. Two seats asked that an unmet gate reject the Copilot half. D11 chose a second review. |
| R1-11 | P1 | architect | ADR-085 Decision 7 governs every `copilotExclude` use. ADR-128 does not cite its items. Not resolved. Deferred. |
| R1-12 | P1 | high-level-advisor, analyst, critic | No live probe ran on Copilot 1.0.116. Partly resolved. Implementation Notes require a live probe before registration. Making it a gate item is deferred to the owner. |
| R1-13 | P1 | high-level-advisor, critic, analyst | Decision 8's "judged stamps" can be met with no judged contradiction. Ten stamps with none false gives a Wilson upper bound of 0.278. Not resolved. Deferred to the owner. |
| R1-14 | P1 | high-level-advisor, critic | ADR-084 rule 5 requires restored tests when the surface fills. Partly resolved. The Impact table and rule 2b say the rule 5 tests must cover both registrations. Neither says the PR waits on them. |
| R1-15 | P1 | high-level-advisor | Decisions 6, 9, 10, and 11 are spec detail. A stateless guard that reads `transcriptPath` is a missing alternative. Not adopted. Deferred to the owner. |
| R1-16 | P1 | critic, analyst | One judge, no distinct-session rule, and no rule that a false block removes the hook. Not resolved. All three are deferred. |
| R1-17 | P1 | critic | The model never sees a call index, and the gate does not measure whether a block changes the reply. Not resolved. Deferred. |
| R1-18 | P1 | critic | Stderr on an exit 0 hook may be invisible. The final reply may not be on disk at stop time. Not resolved. Deferred. |
| R1-19 | P1 | critic | No decision kept the Claude shim out of the Copilot tree. Resolved. Decision 1 sets `copilotExclude: true`. |
| R1-20 | P1 | independent-thinker | Alternative B was rejected on a guess. Resolved. Row B now says the docs are silent and nothing was tested. Context says no live probe ran. |
| R1-21 | P1 | independent-thinker; analyst named shadow mode in its options answer only | Shadow mode and a `userPromptTransformed` notice are missing alternatives. Not adopted. The offline replay in Decision 7 counts would-block stamps with no hook registered. The notice option is deferred to the owner. |
| R1-22 | P1 | independent-thinker | The flag figure does not show that the same reply blocks again. Partly resolved. Context now calls the "next stop" pairing an inference. The log was not split by cause. |
| R1-23 | P2 | security | The off switch should come from the process environment only. Documented. Decision 11 does not say so. |
| R1-24 | P2 | security | The judging location was unstated. Documented. Implementation Notes keep judged sets outside the repository. |
| R1-25 | P2 | architect | Decisions 7 and 8 repeat REQ-050 AC-27 and AC-30. Documented, not changed. D9 put the gate in the ADR. |
| R1-26 | P2 | high-level-advisor, analyst | Ledger rows 7, 8, 9, and 18 cited REQ-050 lines off by one. Fixed. The rows now cite lines 75, 77, 78, and 80. The analyst also questioned row 10's line 215. Two other seats verified that line. |
| R1-27 | P2 | analyst | Decision 11 did not name the variable, and the record had no `## Status` section. Fixed in both places. |
| R1-28 | P2 | independent-thinker | Alternative D was rejected by restating the scope. Fixed. Row D now gives the turn cost. |

The independent-thinker rescanned `~/.copilot` and counted 19,518 stops. That did not match the capped scan. The full count under D12 confirmed it.

### Major Changes Made

- ADR-084 gained rule 2b and an amendment entry.
- ADR-128 Decision 7 now names the offline replay and the date.
- ADR-128, REQ-050, the ledger, and the issue #7633 draft body now carry the full-count numbers (D12).

### Strategic checklist

The high-level-advisor seat gave these results.

| Lens | Assessment |
|------|------------|
| Chesterton's Fence | FAIL. The ADR refuted only rule 2a's stated `transcript_path` reason. It skipped conditions a, d, and f, and the "one hook only" text. |
| Path Dependence | PASS. Registration is gated, and rollback is one registration. |
| Core vs Context | N/A. The build call is in REQ-050 D3. |
| Second-System Effect | FAIL. The trigger rate is 0 of 678. Decisions 6, 9, 10, and 11 are spec detail. A state file guards an event never observed. |
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
| R2-9 | P2 | critic | The 3,897 blocks all predate build 1.0.80, and force 3 calls the loop guard unreliable with no build limit. Documented, not changed. Context says no block was logged on 1.0.87 or later and that block behavior there is unmeasured. |

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

Justification for every deferral: the Copilot hook stays unregistered until the gate passes and the owner accepts rule 2b. No block is live while these stay open. Neither registration exists yet, and the Claude hook slice waits on owner acceptance of rule 2b. Several items would change owner decisions D9 or D11, so the panel cannot settle them.

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
| A definition of normalized claim values, and a digest rule for kinds with no values such as `pushed` and `merged` (R1-2) | critic | REQ-050, before the build slice. |
| A missing session id counts as an unwritable marker | security | Build slice. |
| Strip control characters from the 80-character claim echo | security, critic | Build slice. |
| Known-tool allowlist, keyed digest, and concurrent double-block handling | security | Build slice. |
| Acceptance criteria for ADR-128 Decisions 4 and 6 | critic | REQ-050, before the build slice. |
| A per-kind floor that counts judged `contradicted` stamps, at 10 or at 30 (R1-13) | high-level-advisor, critic, analyst | Owner decision. It changes Decision 8. |
| Remove the hook after one confirmed false block (R1-16) | critic, analyst | Owner decision. |
| A second labeler for the judged stamps (R1-16) | critic | REQ-050 Deferred already lists it. |
| Missing alternatives: a stateless transcript guard and a `userPromptTransformed` notice (R1-15, R1-21) | high-level-advisor, independent-thinker | Owner decision. |
| Move Decisions 6, 9, 10, and 11 to REQ-050 (R1-15) | high-level-advisor | Owner decision. |
| Softer block reason text, the Nth call of a tool in place of the call index, and a count of blocks that change the reply (R1-4, R1-17) | security, critic | REQ-050, before the build slice. |
| A 64 MB read cap value and a registration timeout of at most 10 s (R1-5) | security | Build slice. |
| A walk of ADR-084 rules 3 and 4, and the ADR-085 Decision 7 items for `copilotExclude` (R1-7, R1-11) | architect | Build slice that adds the Claude shim. |
| Stderr visibility on exit 0, and proof the final reply is on disk at stop time (R1-18) | critic | Build slice, with the live probe. |
| A rule that the registering PR waits on the rule 5 tests (R1-14) | high-level-advisor, critic | Build slice. |

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
- The owner decides the deferred items marked "Owner decision".
- The build slices carry the items marked "Build slice".
