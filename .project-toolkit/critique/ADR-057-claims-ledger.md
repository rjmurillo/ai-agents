# ADR-057 claims ledger

Verified 2026-11-25 for Amendment 2026-11-25 (ADR-127 decision 9). Base `c0b72f8539`.

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| The 2026-07-22 amendment says "Do not add a new blocking gate." | Quote | `grep -n` on ADR-057 | VERIFIED. Line 277 holds the sentence. |
| The 2026-07-22 amendment names `pre_pr.py` plus a CI leg for a later gate. | Quote | Read ADR-057 lines 271-284 | VERIFIED. "it belongs in `scripts/validation/pre_pr.py` plus a CI leg". |
| The check runs as the `Skill Rewrite Evidence (ADR-127)` gate. | Path | `grep -n` on `scripts/validation/pre_pr_sequence.py` | VERIFIED. Line 566. |
| The check runs as the `Check ADR-127 skill rewrite evidence` step of `Validate PR`. | Path | `grep -n` on `.github/workflows/pr-validation.yml` | VERIFIED. Line 328, job `validate-pr`. |
| The check calls no model. | Behavior | Read `check_skill_rewrite_evidence.py` and `skill_rewrite_evidence.py` | VERIFIED. Only `git` subprocesses. The runner module loads, and only its pure functions are called. |
| The runner `--output` gains an `identity` block with seven fields. | Behavior | Read `run_identity` at `scripts/eval/eval-prompt-change.py:1087`; run `tests/eval/test_eval_prompt_change_identity.py` | VERIFIED. 7 tests pass. |
| The text sent to the model does not change. | Behavior | `--dry-run` on the ship skill before and after the edit | VERIFIED. Both report `before_chars` 33320, `after_chars` 33320, 48 calls. |
| An unresolved value is written as `null`. | Behavior | `test_unresolvable_ref_records_none`, `test_missing_scenarios_file_records_none` | VERIFIED. |
| The check never reads `gate.verdict` as truth and calls the runner's `acceptance_gate`. | Behavior | Read `verify_results` in `skill_rewrite_evidence.py`; negative control test | VERIFIED. `test_hand_edited_pass_blocks` fails a PASS file whose runs regress. |
| Floors: 8 scenarios, 6 carried, base failures pass every after run. | Behavior | `MIN_SCENARIOS`, `MIN_CARRIED` constants; `TestFloors` | VERIFIED. 5 floor tests pass. |
| The move rule needs 3 lines of 32 or more characters. | Behavior | `MOVE_MIN_LINES`, `MOVE_MIN_CHARS` in `skill_rewrite_skills.py` | VERIFIED. Lines 36 and 37. |
| The earlier draft fired on 51 skill changes in 400 commits. | Count | Corpus script over `git rev-list --first-parent -n 400` at `c0b72f8539` (2026-11-25) | VERIFIED. Output "commits 400 gated hits 51". |
| The verbatim rule fired on 5 skill changes in 4 commits. | Count | Same corpus at `c0b72f8539` (2026-11-25) | VERIFIED. Hits in f1203fed72, 99d82cdcbf (two skills), 94da4a9db9, a15edf93d4. |
| In each hit, `SKILL.md` shrank and a reference file gained the removed lines. | Behavior | `git show --stat` on the 4 commits | VERIFIED for shrink and growth. That the text moved rather than was rewritten is INFERRED from the verbatim overlap count. |
| No template sets `metadata.shape`. | Absence | `git grep -n "^  shape:" -- templates src/claude .claude` | VERIFIED. No match. |
| ADR-114 keeps agent verdicts advisory. | Behavior | Read ADR-114 decision 8 | VERIFIED. Line 53: "An agent verdict is advisory". The new check is not an agent workflow. |
| CODEOWNERS covers `scripts/validation/` but not `scripts/eval/`. | Absence | `grep -n "validation\|eval" .github/CODEOWNERS` | VERIFIED. Line 77 is `/scripts/validation/`. No `scripts/eval` line. |
| A merge's own edits count toward the freeze and append-only rules. | Behavior | `git diff-tree -r -z --cc --name-status` on a scratch repo; `test_merge_resolution_edit_blocks` | VERIFIED. Plain commit `M a`; clean merge empty; resolution `MM a`. A resolution equal to one parent hides the edit, so a second add of a path also fails. |
| CI passes the PR head commit as `--head-ref`. | Behavior | Read the step in `pr-validation.yml`; `test_head_ref_reads_the_named_commit` | VERIFIED. |
| List-form `allowed-tools` is read. | Behavior | `test_list_form_grants_are_read`, `test_non_string_grants_fail_closed` | VERIFIED. |
| The recompute agrees with the runner's own `run_comparison` and `acceptance_gate`. | Behavior | `TestEndToEndConformance`, 7 tables | VERIFIED. |

Rows added after `adr-review` round 1 (`ADR-057-debate-log-2.md`).
