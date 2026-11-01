# ADR Debate Log: ADR-084 rule 2a (advisory nudge) and rule 5 correction

## Summary

- **Rounds**: 5 of 10
- **Prior debate logs**: `.project-toolkit/critique/ADR-084-debate-log.md` (original consensus) and `.project-toolkit/critique/ADR-084-rule-6-tool-use-bar-debate-log.md`
- **Outcome**: pending round 5 vote on the narrowed text
- **Final Status**: proposed (consensus reached; owner acceptance pending)
- **Subject**: proposed 2026-10-31 amendment to ADR-084 adding rule 2a and correcting rule 5's enforcement record, for REQ-048.
- **Trigger**: repo-owner @rjmurillo decided on 2026-10-31 to vendor the REQ-048 friction nudge. The decision was relayed from the owner's master session and authorizes TASK-005.
- **Panel**: reduced (architect, critic), per AGENTS.md. The amendment edits policy prose in rules 2 and 5 and adds rule 2a. It touches no executable enforcement. `git grep ADR-084` over `scripts/`, `build/`, and `tests/` (2026-11-01, branch tip) finds one test that reads ADR-084 text: `tests/build_scripts/test_hook_contract_knowledge.py:1301-1312`. It reads only the security carve-out quote, which is unchanged, and it passes. The rule 5 tests and the Copilot generator test do not exist yet (deleted in `f79e70c01`, or owed by TASK-006).

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
| C-P2-4 | P2 | critic | The correction says the check enforced rule 5 for zero days (superseded by A2-3). |
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
| critic | Accept | No round 1 finding is still open. The critic accepts the C-P1-4 deferral. Four new P2s. |

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| C2-1 | P2 | critic | The REQ-048 condition-to-AC map is corrected. |
| C2-2, A2-4 | P2 | both | The REQ-048 blocked range now includes AC-21. |
| C2-3, A2-2 | P2 | both | AC-17 now also checks that the advisory is absent from the next turn's model context (condition f). |
| C2-log | P2 | critic | The "risk during the gap" line is narrowed to the REQ-048 hook only. |
| A2-1 | P2 | architect | New AC-22: a planted file outside the four condition e inputs is never opened. |
| A2-3 | P2 | architect | The rule 5 test lived about 22 hours (`2c85d2547` to `f79e70c01`), not zero days. The correction says so, and it notes the original "Enforced since" date is one day late in -0700 (round 3: correct in UTC). |
| A2-5 | P2 | architect | REQ-048 now cites both Stop sections of `official-hook-contracts.md` (lines 237-252 and 442-454). |
| A2-6 | P2 | architect | Rule 2a states that `copilotExclude` is used for an output-contract gap, not a security judgment. |

Round 2 changes are P2 text repairs. Two were not re-reviewed in round 2: AC-22 was added (A2-1) and the rule 5 duration was corrected (A2-3). Round 3 covers them.

## Round 3 Summary

**Trigger**: `/review` on 2026-10-31 returned WARN. The fixes changed rule 2a text after the round 2 votes. Owner decisions, 2026-10-31: the opt-out turns off the whole hook; the owner's vendoring decision replaces the consumer-value argument; the held-out set is a seeded 70/30 session split.

**Round 3 scope**: the rule 2 proposed marker; conditions e and g; the ADR-085 Decision 7 MUST in the Copilot clause; the timezone note on rule 5; the Consequences corrections; the Alternatives, kill-scope, and Rollback paragraphs; REQ-048 Q3, AC-12, AC-15, AC-19, the AC map, and Q-1 and Q-2; and the round 2 items AC-22 and A2-3.

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | No MUST weakened. AC-12, AC-20, and condition g agree. One P1 (A3-1) and four P2s. |
| critic | Disagree-and-Commit | Rule 5 duration verified at 22h14m. C3-1 and C3-2 must close before TASK-006. |

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| A3-1, C3-1 | P1 | both | Condition e now lists a closed set of state-root variables. A state root inside the repository is refused. New AC-24 tests the refusal. |
| C3-2 | P1 | critic | Rollback now removes the restored rule 5 tests when the vendored surface empties (superseded by A4-5, then reverted in the narrowing). |
| A3-2, C3-6 | P2 | both | The REQ-048 evidence row now names the seeded split. AC-19 records window dates, seed, split list, and the accepted leakage risk. |
| A3-3 | P2 | architect | AC-12: an off hook neither reads nor writes its state. |
| A3-4 | P2 | architect | Not changed. The authorizing issue is a TASK-006 duty under the Copilot clause, and rule 2a binds only after owner acceptance. |
| A3-5 | P2 | architect | Covered by the AC-19 change above. |
| C3-3 | P2 | critic | AC-12 off values ignore case and whitespace. New AC-23 is the positive control. |
| C3-4 | P2 | critic | AC-15 snapshots `.git/` after a priming `git status`. |
| C3-5 | P2 | critic | AC-22 names `sys.addaudithook` and a recording env mapping, with both branches active. |
| C3-7 | P2 | critic | The A2-3 row notes UTC. This section logs the full round 3 scope. Status again requires review closure. |

Round 3 fixes apply the fixes the reviewers proposed. The condition e refusal clause is new requirement text, taken from the C3-1 fix. No other condition or MUST changed after the votes.

**Post-round-3 repairs (from `/review` round 2, 2026-10-31).** The review found three gaps in that unvoted condition e text, and they are now repaired. First, the refusal needed an input outside condition e's list, so it now checks only the repository that holds the payload `cwd`, found with `stat` calls. Second, AC-24 now says nothing is emitted on refusal. Third, the variable list now names `HOMEDRIVE` and `HOMEPATH`, which `Path.home()` reads on Windows. AC-19 gained a minimum of 20 labeled nudges. The condition e repairs narrow the refusal, and the `HOMEDRIVE` and `HOMEPATH` names widen the allowed reads to match what `Path.home()` already does. The AC-19 minimum is a new gate condition in REQ-048, not in the ADR. The owner may re-poll the panel before accepting.

**Second repair pass (from `/review` round 3, 2026-10-31).** The first pass checked only the repository holding `cwd`, so it covered fewer cases than condition b requires. A dotfile-managed `$HOME` repo above a nested project was missed. The refusal now walks from the resolved state root to the filesystem root. It runs before any `mkdir`, and it emits one stderr line but no `systemMessage`. AC-19 now has a 90-day owner decision point and daily transcript snapshots. Round 4 votes on all post-round-3 text.

## Round 4 Summary

**Trigger**: no panel had voted on the post-round-3 text. The owner chose a re-poll on 2026-10-31.

**Round 4 scope**: everything changed since the round 2 Accept votes, with a focus on condition e, the Copilot clause, Rollback, and REQ-048 AC-12, AC-19, AC-20, and AC-22 to AC-24.

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Disagree-and-Commit | No MUST is unsound. A4-1 must close before TASK-001 reports. |
| critic | Disagree-and-Commit | The refusal holds for symlinked roots, missing roots, and linked worktrees. C4-1 must close before held-out labeling. |

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| A4-1, C4-1 | P1 | both | AC-19 freezes weights before held-out labeling. Post-freeze snapshots join the held-out split only. It states that the 90-day decision point is a likely path. |
| A4-2 | P2 | architect | New Security row for the transcript snapshot store. |
| A4-3 | P2 | architect | AC-24 runs after the AC-12 off check. |
| A4-4, C4-2, C4-4 | P2 | both | Condition e claims only a tree holding a `.git` entry and names the bare-repo gap. An unset `HOME` on POSIX is refused. "No other variable" is scoped to hook code. |
| A4-5 | P2 | architect | Rollback keeps the presence test and skips the companion test on an empty surface. It names the leftover marker directory. |
| A4-6 | P2 | architect | TASK-004 names the `_safe_marker_dir` reorder. |
| C4-3 | P2 | critic | The failure-mode row covers `/` holding a `.git` entry. |
| C4-5 | P2 | critic | AC-24 names its five fixtures. |
| C4-6 | P2 | critic | AC-12 defines off values as literal tokens only. |
| C4-7 | P2 | critic | This section exists, the header is current, and the "narrow" wording is corrected. |

Round 4 fixes apply the reviewers' proposed fixes. The unset-`HOME` refusal is new text from C4-4.

## Narrowing (2026-11-01, before round 5)

**Trigger**: the fresh `/review` on 2026-10-31 returned WARN on four axes. Mechanics inside the ADR kept drawing findings. The owner chose to narrow the ADR and move mechanics to REQ-048 (D6). The owner also chose a conversion-rate kill rule (D7).

**Changes, all made before the round 5 vote:**

- Rule 2a covers the REQ-048 hook only and lapses under a sunset clause.
- Condition e names inputs; REQ-048 AC-22 holds the closed variable list, including the launcher's `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PROJECT_DIR`.
- The refusal walk, the unset-`HOME` refusal, and the bare-repo gap move to REQ-048 AC-24.
- Rollback deletes both rule 5 tests on an empty surface, as `f79e70c01` did. This reverts the A4-5 skip.
- The rule 5 correction's new duties are marked proposed with rule 2a.
- "Failed retries" becomes "repeated identical calls", matching Q5.
- REQ-048: AC-19 adds a Wilson lower bound of at least 50 percent. A new SLI 5 measures conversion. "Release" is defined. The kill rule is a 20 percent same-session conversion floor or precision under 50 percent. New AC-25 tests Stop-only registration. TASK-006 maps all nine ADR-085 Decision 7 items.

### Next Steps

- The owner (@rjmurillo) accepts or rejects rule 2a. Rule 2a binds only after acceptance.
- After acceptance, REQ-048 TASK-001 to TASK-004 may start dogfood-first. TASK-006 carries the deferred C-P1-4 guard and the rule 5 test restoration.
