# ADR Debate Log 2: ADR-127 Workflow Skills Are Script Drivers, and Evals Gate Every Skill Rewrite

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-127-debate-log.md`
- **Outcome**: Consensus (3 Accept, 3 Disagree-and-Commit)
- **Final Status**: accepted
- **Panel**: full six seats. The change edits the gate's trigger, which is an enforcement rule.
- **Claims ledger**: `.project-toolkit/critique/ADR-127-claims-ledger.md`
- **Date**: 2026-11-25

## Why a second debate

The first debate closed by consensus. A `/review` run on the branch then raised findings.
Fixing them changed ADR text, and a closed log takes no more rounds.

Carried forward from the first log: four dissents and no unresolved P0.

## Input: `/review` round 1 on commit `75db399af8` (2026-11-25)

| Axis | Verdict | Finding that changed ADR text |
|---|---|---|
| spec-compliance | WARN | The title says every skill rewrite is gated. The triggers gated less. |
| analyst | PASS | "Gap audit" was used before it was defined. The 8 and 6 floor was not marked provisional. |
| decision-rigor | WARN | Thirteen decisions were accepted before one driver exists. |
| roadmap | WARN | The rollout was unsized. The decision 9 check had no place in the order of work. |
| correctness | WARN | "Sets or changes `metadata.shape`" gated all 121 templates on tagging. Count lines lacked a same-line anchor. |
| doc-accuracy | PASS | None. |

## Round 1 Summary

### Major Changes Made

- Decision 7 has four triggers. Tagging a skill `reference` with no prompt change is not gated.
- Decision 1 defines the gap audit at first use. It gives each finding a stable id and counts the driver skills.
- Decision 7 item 4 labels the 8 and 6 floor an analogy and provisional.
- Decision 12 names the pilot's path to change decision 4 or 7: through `adr-review`.
- Trade-offs state that no gate measures real tool calls after the pilot.
- Implementation Notes size the rollout in the audit and place the decision 9 check first after the pilot.
- Each count line carries its commit and date on the same line.
- Outside the ADR: spec R8 points to decision 7. Debate log 1 states 27, 32, and 50 ledger rows. Audit rules G4 and H1 gained line citations.

### Agent Positions

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Condition: this log lands in the same change. |
| critic | Disagree-and-Commit | Trigger (b) bound only tagged drivers, so an untagged driver-shaped skill escaped. |
| independent-thinker | Disagree-and-Commit | "The four triggers together cover every skill rewrite" was false as written. |
| security | Disagree-and-Commit | A mutating skill mis-tagged `reference` in an ungated PR escapes decision 3. |
| analyst | Disagree-and-Commit | Same overclaim as the independent-thinker. |
| high-level-advisor | Disagree-and-Commit | Carried dissent, reduced by the sizing step. |

## Round 2 Summary

### Key Issues Addressed

- A prose-only rewrite of a `reference` skill hits no trigger. The coverage sentence claimed otherwise.
- Trigger (b) missed a skill that must be a driver but is not yet tagged.

### Major Changes Made

- Trigger (b): "a skill that is a `driver`, or that decision 1 says must be one".
- The coverage sentence names the one case outside the gate and points to ADR-057's existing MUST.
- The Neutral line matches: tagging is not gated, restructuring or an audit-row change is.

### Agent Positions

| Agent | Position | Notes |
|---|---|---|
| architect | Accept | Note: "decision 1 says must be one" is a judgment call until the audit assigns shapes. |
| critic | Disagree-and-Commit | Carried dissent 1 from the first log. Round 1 dissent cleared. |
| independent-thinker | Accept | Round 1 dissent closed. Note: ADR-057's MUST is weakly enforced for the excluded case. |
| security | Accept | Round 1 dissent dropped. Two open recommendations below. |
| analyst | Disagree-and-Commit | Carried dissent 3 from the first log. |
| high-level-advisor | Disagree-and-Commit | Carried dissent 4 from the first log. |

## Dissent standing after both debates

1. **critic.** The pilot is the hardest case and gets the weakest check.
2. **analyst.** A carried scenario that falls from 3 of 3 to 2 of 3 still passes.
3. **high-level-advisor.** Fix threads can start before the pilot reports its numbers.

The independent-thinker's dissent on the floor of 8 closed when the ADR labeled it an analogy.

## Open recommendations, not adopted

| Recommendation | Seat | Disposition |
|---|---|---|
| The decision 9 check should fail a `reference` skill whose `allowed-tools` grants a push, a PR-writing script, or `Bash(*)` | security | Left for the check's own change, which goes through `adr-review`. |
| Name `PYTHONPATH` in decision 3 item 6 | security | Left open. ADR-121 owns the locator text. |
| Hold the record at `proposed` until the pilot reports | decision-rigor review axis | Not adopted. Decision 12 names how the pilot changes the record. Put to the owner. |
| Take pilot scenarios from another author, or have the owner approve the scenario commit | decision-rigor review axis | Not adopted here. It is a rule for the pilot thread. Put to the owner. |

## Next Steps

1. Write the gap audit. It sizes the rollout.
2. Put the three open `ship` decisions and the standing dissents to the owner.
3. Run the `ship` and `push-pr` pilot.
