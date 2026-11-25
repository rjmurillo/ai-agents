# ADR Debate Log 4: ADR-127 Workflow Skills Are Script Drivers, and Evals Gate Skill Rewrites

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-127-debate-log-3.md`
- **Outcome**: Consensus (3 Accept, 3 Disagree-and-Commit)
- **Final Status**: accepted
- **Panel**: full six seats. The change edits the result-line protocol and the gate's floors.
- **Claims ledger**: `.project-toolkit/critique/ADR-127-claims-ledger.md` (53 rows at the vote, 55 after the review round that followed)
- **Date**: 2026-11-25

## Why a fourth debate

PR #7575 review raised four threads on commit `ee9b08b787` (2026-11-25).
One came from the owner's account. Three came from Devin Review. All four were valid.

| Thread | Finding |
|---|---|
| Stdout contracts | ADR-103 is accepted. It requires a JSON envelope when stdout is captured. ADR-127's result lines contradicted it. |
| Baseline pin, two threads | Decision 7 said the first run records the base commit. The runner records only the ref name. |
| Mixed-base scenarios | A scenario that passes 2 of 3 base runs met neither floor. The runner excludes it, so it could drop to zero. |

The first finding is a gate escape. Six seats, three debates, and a 50-row ledger all missed an accepted record.
No seat searched the accepted records for an existing script output contract.

Carried forward from the third log: three standing dissents and no unresolved P0.

## Round 1 Summary

### Major Changes Made

- Decision 4 item 12: a driver script keeps ADR-103. The result lines are its `human` format.
  `json` emits the ADR-103 envelope. A driver passes `--output-format human` on every call.
- Decision 7 item 4: the author puts the base commit in the PR body until the decision 9 check lands.
- Decision 7 item 7: the after-side floor also binds a scenario with a mixed base result.
- Decision 7 item 8: the author runs the scenarios on base first and fixes or removes a mixed one.
- The tagging exemption reads "changes nothing else in the skill".

### Agent Positions

| Agent | Position | Notes |
|---|---|---|
| architect | Disagree-and-Commit | Item 12 is a coherent reading of ADR-103, except item 5's color. Say so. |
| critic | Disagree-and-Commit | The pre-freeze base run was unrecorded. The color deviation was silent. |
| independent-thinker | Disagree-and-Commit | Every driver call passes `human`, so `json` runs only in tests. Measure both. |
| security | Disagree-and-Commit | Say the cap and secret rules bind both formats. |
| analyst | Disagree-and-Commit | "Mixed" missed two unstable shapes the runner knows. |
| high-level-advisor | Disagree-and-Commit | Keep both modes. Amending ADR-103 inside the pilot is the larger scope. |

## Round 2 Summary

### Major Changes Made

- Item 12 states that items 8, 9, and 10 bind both formats and that an envelope reaching the model is a STOP.
- Item 12 states its departure from ADR-103 item 5. The ADR-103 row reads "Kept, except item 5's color".
  The pilot's change amends ADR-103 item 5 through `adr-review`.
- Decision 7 item 4: carried scenarios pass all three scored base runs.
- Decision 7 item 7 names the runner's own `base_unstable_scenarios` list.
- Decision 7 item 8: the pre-freeze base run's output is committed.
- Decision 12 adds a fifth pilot measure: one driver run in each format, with misread control values and tokens per call.

### Agent Positions

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Round 1 dissent resolved. |
| critic | Disagree-and-Commit | Carries standing dissent 1. Note: item 7 lists two unstable shapes; the runner has a third. |
| independent-thinker | Accept | Withdrew the dissent. The fifth measure tests it. |
| security | Accept | Round 1 dissent closed. Two open recommendations carried from the second log. |
| analyst | Disagree-and-Commit | Carries standing dissent 2. |
| high-level-advisor | Disagree-and-Commit | Carries standing dissent 3. |

## Dissent standing after all four debates

1. **critic.** The pilot merges on author-written scenarios and a reviewer-read floor.
2. **analyst.** A carried scenario that falls from 3 of 3 to 2 of 3 on the after side still passes.
3. **high-level-advisor.** Fix threads can start before the pilot reports its numbers.

## Measured by a seat, not in the ledger

- The high-level-advisor counted 4 of 228 skill script files that contain `output-format` at `75db399af8` (2026-11-25).
- The independent-thinker counted 59 of 313 with a wider pattern at `792f6febd3` (2026-11-25).

The two counts used different patterns and file sets. Neither is verified here.
Both say the same thing: most skill scripts do not follow ADR-103 today.

## Next Steps

Unchanged from the second log, plus one: the pilot's change amends ADR-103 item 5.
