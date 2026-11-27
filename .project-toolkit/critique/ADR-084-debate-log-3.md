# ADR Debate Log: ADR-084 rule 2b (receipts Copilot block)

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-084-debate-log-2.md` (closed, rule 2a)
- **Outcome**: Consensus (round 2: 6 of 6 Accept or Disagree-and-Commit). Under ADR-101 the panel counts as one vote; owner acceptance is the binding gate.
- **Final Status**: rule 2b is proposed and not yet binding. The owner has not accepted it. ADR-084 frontmatter stays `status: accepted` for the rest of the record.
- **Subject**: 2026-11-25 amendment to ADR-084 adding rule 2b. It permits one blocking `agentStop` hook on Copilot CLI: the REQ-050 `receipts` hook.
- **Trigger**: owner decision D10 on 2026-11-25 ("Add rule 2b to ADR-084"), made after the ADR-128 panel blocked on the rule 2a conflict.
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). Rule 2b is a rule that tests read: `tests/hooks/test_plugin_stop_registration.py` pins the advisory set and the empty Copilot Stop list.
- **Companion log**: `.project-toolkit/critique/ADR-128-debate-log.md`. The same panel reviewed both documents together. This log's round 1 is that log's round 2.
- **Claims ledger**: `.project-toolkit/critique/ADR-128-claims-ledger.md`, rows 2 to 4, 19, 22, 25, 26, and 30 cover ADR-084 text.

## Background

ADR-128 round 1 ended 3 Block, 3 Disagree-and-Commit. All six seats found that ADR-128 broke rule 2a while claiming not to amend ADR-084. Four rated it P0, and two rated it P1. Rule 2a says the nudge "MUST stay out of the Copilot tree" and that any other advisory hook needs its own amendment. Rule 2b is that amendment.

## Round 1 Summary

### Agent Positions

| Agent | Position | Head finding |
|-------|----------|--------------|
| architect | Disagree-and-Commit | Rule 2b claims condition c is met, yet the message echoes a tool name. |
| critic | Disagree-and-Commit | The bound is once per claim, not once per session. |
| independent-thinker | Disagree-and-Commit | Condition g is claimed but not met. |
| security | Disagree-and-Commit | No session cap on blocks. |
| analyst | Disagree-and-Commit | Same condition c finding as the architect. |
| high-level-advisor | Accept | Rule 2b names each departure and keeps the reflect nudge excluded. |

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| B-1 | P1 | architect, critic, analyst | Rule 2b now names the bounded tool-name echo as a departure from condition c for both registrations. |
| B-2 | P1 | independent-thinker, security, critic | Rule 2b now states the bound: one block per claim per session, no session cap. |
| B-3 | P1 | independent-thinker, security, critic | A hard session cap. Deferred with justification (below). |
| B-4 | P1 | architect, analyst, critic | Rule 2b cited owner decision D10, which REQ-050 did not record. REQ-050 now lists D3 to D12. |
| B-5 | P1 | architect | The sunset ties all of rule 2b to ADR-128. A separate sunset per registration is deferred (below). |
| B-6 | P2 | architect | Rule 2b now gives the reason for `copilotExclude` and names the owning record. |
| B-7 | P2 | security, critic | The 80-character echo can carry control characters. Stripping them is a build slice item in the companion log. |

### Strategic checklist

| Lens | Assessment |
|------|------------|
| Chesterton's Fence | PASS. The amendment gives both reasons for the Copilot exclusion and says which still holds. Both documents separate receipts from the PR #3372 hook. |
| Path Dependence | PASS. Rollback is stated in both documents, and both have a sunset condition. The marker is inert without the hook. |
| Core vs Context | PASS, with a caveat: the amendment admits there is no consumer demand evidence, so value is asserted. |
| Second-System Effect | PASS. The scope is one hook, one gate, and one amendment. Twelve decisions surround a stamp with 0 observed occurrences, but the work has a sunset. |

## Round 2 Summary

Round 2 was a convergence check on the text changed after round 1.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Disagree-and-Commit |
| independent-thinker | Accept |
| security | Disagree-and-Commit |
| analyst | Disagree-and-Commit |
| high-level-advisor | Accept |

No seat found a new factual error.

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| B-8 | P2 | independent-thinker | Rule 2b does not say whether "no session cap" meets rule 2a condition g's bounded rate. Documented. The answer depends on the deferred session cap. |
| B-9 | P2 | high-level-advisor | The seat did not verify the round 1 tally in the amendment entry. The companion log records it. |

## Deferred items

| Item | Source | Justification |
|------|--------|---------------|
| A hard cap on blocks per session | independent-thinker, security, critic | It changes owner decision D9. The hook is unregistered until the ADR-128 gate passes and the owner accepts rule 2b, so no block is live. |
| A separate sunset for each registration | architect | Owner decision. ADR-128 `review-by` 2027-02-25 already forces a re-review if the gate is unmet. |

## Dissent

- critic, security: no hard cap on blocks per session.
- security: a missing session id is not treated as an unwritable marker.
- analyst: rule 2b admits a Copilot block whose cost nobody has measured. The registration gate is the only mitigation.
- high-level-advisor (round 1, on ADR-128): the exception may sit in ADR-084 for a hook that never ships.

## Next Steps

- The owner decides whether to accept rule 2b. Until then the rule binds nothing.
- The tests in `tests/hooks/test_plugin_stop_registration.py` change only in the build slice that registers the hook.
