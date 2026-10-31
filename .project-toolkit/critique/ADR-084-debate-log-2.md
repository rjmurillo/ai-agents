# ADR Debate Log: ADR-084 rule 2a (advisory nudge) and rule 5 correction

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-084-rule-6-tool-use-bar-debate-log.md`
- **Outcome**: Consensus (2/2 Accept in round 2)
- **Final Status**: proposed (consensus reached; owner acceptance pending)
- **Subject**: proposed 2026-10-31 amendment to ADR-084 adding rule 2a and correcting rule 5's enforcement record, for REQ-048.
- **Trigger**: repo-owner @rjmurillo decided on 2026-10-31 to vendor the REQ-048 friction nudge. The decision was relayed from the owner's master session and authorizes TASK-005.
- **Panel**: reduced (architect, critic), per AGENTS.md. The amendment edits policy prose in rule 2. It does not touch executable enforcement, and no gate reads rule 2. A search of `scripts/`, `build/`, `tests/`, rules, and templates found no reader of the rule 2 text (architect finding 8).

## Round 1 Summary

### Agent Positions

| Agent | Position | Head finding |
|-------|----------|--------------|
| architect | Disagree-and-Commit | P1: ADR-097 "Neutral" names four events, not `Stop`. |
| critic | Block | P0-1: condition d allowed `UserPromptSubmit`, whose output enters model context, so a fixed line could steer the agent. |

Both reviewers verified these facts against the tree at `9254b9945`:

- `b862e14e9` (2026-07-26) deleted `invoke_auto_retrospective.py`, which returned `decision: "block"`.
- `f79e70c01` (2026-08-19, #5172) deleted both rule 5 tests.
- `src/claude/hooks.json` registers `{}`.
- No dispatch group carries `surface: "plugin"`.
- Rule 6's four events exclude `Stop`.

The architect ran a Chesterton's fence check and it passed.

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| C-P0-1 | P0 | critic | Condition d now names `Stop` only. New condition f limits output to a user-visible channel that addresses the user and instructs no agent. |
| C-P1-1 | P1 | critic | New condition g requires a documented firing bound. |
| C-P1-2, A-1.2 | P1 | both | The Amendment Record now says the Stop advisory channel is undocumented on both harnesses. Claude Code rests on observed behavior and is gated by REQ-048 AC-17. Copilot is excluded because it has no `transcript_path` and no observed advisory field. |
| C-P1-3, A-1.1 | P1 | both | ADR-097's four events are now quoted. `Stop` coverage is marked INFERRED from ADR-097's stated reason and from `.claude/AGENTS.md`. |
| C-P1-4 | P1 | critic | Deferred with justification (below). |
| C-P1-5 | P1 | critic | Condition g puts the variable name and its off values in the `Customer value:` line. The variable is read before the transcript opens. REQ-048 AC-18 and AC-20 now say this. |
| A-1.3 | P1 | architect | Condition e now lists four permitted inputs. |
| A-1.4 | P1 | architect | Rule 2a now requires `copilotExclude: true` plus a generator test. REQ-048 AC-21 covers it. |
| C-P2-1 | P2 | critic | The corpus scope and the shared labeler are stated. The kill criterion is added. |
| C-P2-2 | P2 | critic | "#3372" now reads "PR #3372 (issue #3349)". |
| C-P2-3, A-1.5 | P2 | both | This file now exists. |
| C-P2-4 | P2 | critic | The correction says the check enforced rule 5 for zero days. |
| A-1.6 | P2 | architect | Rule 2a's heading says "proposed, not yet binding". Status says the frontmatter `accepted` covers only prior text. |
| A-1.7 | P2 | architect | The first vendored hook under rule 2a records a fresh ADR-071 runtime contract. |
| A-1.8 | P2 | architect | REQ-048 AC-18 points at the restored test. The `tool-use-hook-bar.md` wording is deferred to TASK-006. |

### Deferral (P1, per references/issue-resolution.md)

**C-P1-4: no guard test detects the first vendored hook.**

- **Deferred to**: REQ-048 TASK-006.
- **Justification**: the owner scoped this work to "draft the amendment and run it through adr-review before any implementation". A guard test is implementation.
- **Risk during the gap**: the REQ-048 hook cannot land without TASK-006. TASK-006 is blocked on this amendment, and the amendment requires both rule 5 tests in that same PR. This does not cover other hooks; see residual risk.
- **Residual risk**: a different contributor could add an unrelated vendored hook before TASK-006, and only review would catch it. The ADR text records this.

### Major Changes Made

- Rule 2a went from five conditions to seven (a to g). Condition d narrowed from "session-boundary or per-turn" to `Stop` only.
- A Copilot exclusion clause and an ADR-071 duty clause were added.
- The Amendment Record was rewritten for evidence parity, the ADR-097 quote, and the corpus scope. It now lists the open items.
- REQ-048 gained AC-20 and AC-21 and retargeted AC-18. TASK-006 grew to match.


## Round 2 Summary

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | All eight round 1 findings were checked as resolved in the ADR text. Six new P2s. |
| critic | Accept | No round 1 finding is still open. The critic accepts the C-P1-4 deferral. Three new P2s. |

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| C2-1 | P2 | critic | The REQ-048 condition-to-AC map is corrected. |
| C2-2, A2-4 | P2 | both | The REQ-048 blocked range now includes AC-21. |
| C2-3, A2-2 | P2 | both | AC-17 now also checks that the advisory is absent from the next turn's model context (condition f). |
| C2-log | P2 | critic | The "risk during the gap" line is narrowed to the REQ-048 hook only. |
| A2-1 | P2 | architect | New AC-22: a planted file outside the four condition e inputs is never opened. |
| A2-3 | P2 | architect | The rule 5 test lived about 22 hours (`2c85d2547` to `f79e70c01`), not zero days. The correction says so, and it notes the original "Enforced since" date is one day late. |
| A2-5 | P2 | architect | REQ-048 now cites both Stop sections of `official-hook-contracts.md` (lines 237-252 and 442-454). |
| A2-6 | P2 | architect | Rule 2a states that `copilotExclude` is used for an output-contract gap, not a security judgment. |

Round 2 changes are P2 text repairs. No condition, MUST, or scope changed after the Accept votes, so no round 3 was run.

### Next Steps

- The owner (@rjmurillo) accepts or rejects rule 2a. Rule 2a binds only after acceptance.
- After acceptance, REQ-048 TASK-001 to TASK-004 may start dogfood-first. TASK-006 carries the deferred C-P1-4 guard and the rule 5 test restoration.
