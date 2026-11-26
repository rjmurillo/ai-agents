# ADR-115 Debate Log 10

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`, Decision 6, proposed job layout (not in force).
- **Scope**: the PR #7634 follow-up only. It corrects the rollout dependency and clarifies future validation and rollback. Pack membership does not change.
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-9.md` (closed by consensus; not edited).
- **Claims ledger**: `.project-toolkit/critique/ADR-115-claims-ledger.md`, section "PR #7634 follow-up".
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). The text sets acceptance criteria for future build checks and the smoke.

## Triggers

- PM review: the PR said pilot #7581 merges first. Native links show #7581 is blocked by #7587, so that order deadlocks.
- The pilot owner confirmed on 2026-11-25 that #7586 (ship driver wiring) can land while `push-pr` still ships. #7586 is blocked by #7582 to #7585, not by #7587. #7586 is not yet implemented.
- Devin review on PR #7634 raised four findings: spec tier prerequisites, a PR-opening check that a broken handoff could pass, a path check that would reject same-pack calls, and a rollback that names a retired skill.

## Round 1

Votes: architect Block, critic Block, independent-thinker Block, security Block (scope not enumerable), analyst Disagree-and-Commit, high-level-advisor Block. No P0.

| ID | Seat | Finding | Disposition |
|---|---|---|---|
| R1-P1-1 | architect, analyst, high-level-advisor | The analysis still let #7587 merge with the layout PR, against the stated order. | Resolved. #7587 merges only after the layout PR merges and proves the Hermes PR path, and never in that PR. |
| R1-P1-2 | critic | The code-built path check would forbid the `skillforge/scripts/_packs.py` sibling lookup that ADR-115 allows. | Resolved. Criterion 7 and Decision 6 keep that exception and list the four test cases. |
| R1-P1-3 | independent-thinker | `spec-generator` needs excluded `cva-analysis` for every Tier 3 to 5 spec and multi-use-case Tier 1 or 2 spec, so three packs do not suffice for Tier 3. | Resolved. The analysis states both limits and which specs finish on Hermes. |
| R1-P1-4 | independent-thinker | "Reversible" was not true after retirement unless proven. | Resolved. Before #7587, record either a proven four-pack fallback that keeps `ship` or the owner's acceptance of roll-forward-only recovery. |
| R1-P1-5 | security | The review scope was not enumerable from the working tree alone. | Resolved for round 2. The seat gets the full diff snapshot against `origin/main`. |

## Round 2

Votes: architect Accept, critic Accept, independent-thinker Accept, security Accept, analyst Accept, high-level-advisor Accept. No P0 or P1 open.

Outcome: consensus in round 2, six Accept.

Not checked by a seat: the analyst could not read the long `cva-analysis` line through search. The independent-thinker read it and confirmed it matches Step 5 of `spec-prior-art-schema.md`.

Status stays `proposed`. The owner decides the layout under Decision 6.
- `/review` round 4 (three PASS, one WARN, all low): ADR-115 Status now cites this log; the analysis PR-path line names #7586, not the pilot; the claims-ledger follow-up rows are C23 to C27, and C25 now states the `cva-analysis` limit at `spec-prior-art-schema.md:195`.
