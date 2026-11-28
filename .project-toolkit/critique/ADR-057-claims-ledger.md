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

## Amendment 2026-11-25: the /spec CI leg is deleted

Claims in the 2026-11-25 amendment or edited sentences of ADR-057. The owner-statement row is `NOT RUN`: it names a source this ledger did not re-query, so the amendment attributes it to the owner and does not assert it as a measurement.

Commands ran in the working tree of branch `ci/delete-agent-env-jobs` at head `7cfb378901` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` on base `e74b842786`.

| Claim | Kind | Command | Result |
|---|---|---|---|
| slash-command-quality.yml no longer exists | absence | `test ! -e .github/workflows/slash-command-quality.yml && echo absent` | VERIFIED: absent |
| advisory_agent_workflows no longer lists slash-command-quality | absence | `grep -c 'slash-command-quality' src/claude/skills/pr-review/pr-review-config.yaml` | VERIFIED: 0 |
| No workflow invokes eval-prompt-change.py | absence | `grep -rln 'eval-prompt-change' .github \| wc -l` | VERIFIED: 0 |
| The acceptance gate returns FAIL on a regression when run | behavior | `uv run pytest tests/eval/test_eval_prompt_change.py -q -k test_regression_fails_gate` (asserts `gate["passed"] is False` at test line 1004) | VERIFIED: 1 passed, 149 deselected in 0.16s |
| tests/evals/spec-scenarios.json still exists (scenario set cited in the edited sentence) | path | `test -f tests/evals/spec-scenarios.json && echo present` | VERIFIED: present |
| Owner statement: latest 100 deployments of agent-claude and agent-copilot show none approved or run | quote | `echo 'owner statement in the task brief, 2026-11-25; not re-queried'` | NOT RUN: owner statement in the task brief, 2026-11-25; not re-queried |

## Second pass, 2026-11-25

Rows for the reworded first sentences of the 2026-11-25 amendment (the owner's stated reason and its scope). Commands ran on 2026-11-25 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| Commit 637b60d749 is a bot stats commit dated 2026-11-13 | behavior | `git log -1 --format='%h %cs %an %s' 637b60d749` | VERIFIED: 637b60d749 2026-11-13 github-actions[bot] chore(stats): update reviewer signal statistics (#7327) |
| That commit title is what the reviewer-stats workflow writes | behavior | `git show 637b60d749:.github/workflows/update-reviewer-stats.yml \| grep -n 'update reviewer signal statistics' \| head -n 2 \| tr '\n' ' '` | VERIFIED: 165: --message "chore(stats): update reviewer signal statistics" \ |
| update-stats declared agent-claude from commit d73c0cf0fe (2026-11-05) | behavior | `git log -1 --format='%h %cs' d73c0cf0fe; git show d73c0cf0fe:.github/workflows/update-reviewer-stats.yml \| grep -n 'environment: agent-claude' \| tr '\n' ' '` | VERIFIED: d73c0cf0fe 2026-11-05 39: environment: agent-claude |
| The parent of d73c0cf0fe did not declare it | absence | `git show d73c0cf0fe^:.github/workflows/update-reviewer-stats.yml \| grep -c 'environment: agent-claude'` | VERIFIED: 0 |
| At 637b60d749 the job still declared it | behavior | `git show 637b60d749:.github/workflows/update-reviewer-stats.yml \| grep -n 'environment: agent-claude' \| tr '\n' ' '` | VERIFIED: 57: environment: agent-claude |
| Owner statement: the latest 100 deployments of agent-claude and agent-copilot show none approved or run | quote | none: the source is the owner's statement, not a query this ledger ran | NOT RUN: attributed to the owner in the ADR text, with the window stated |

## Third pass, 2026-11-26

Rows for the text the reduced panel added on 2026-11-26: the decision-maker line and the rewritten clause about commit `637b60d749` (2026-11-13). Commands ran on 2026-11-26 in the working tree of branch `ci/delete-agent-env-jobs` at head `879dff55b3` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| Commit 637b60d749 changes a metrics report and a memory file | behavior | `git show --format= --name-only 637b60d749 \| tr '\n' ' '` | VERIFIED: .project-toolkit/metrics/agent-pr-intervention.md .serena/memories/pr-review/pr-comment-responder-skills.md |
| That report says it was generated 2026-11-12 | quote | `git show 637b60d749:.project-toolkit/metrics/agent-pr-intervention.md \| grep -o -m1 'Generated 2026-11-12 from GitHub PR events'` | VERIFIED: Generated 2026-11-12 from GitHub PR events |
| At 637b60d749 the report is built and uploaded inside `update-stats` (lines 53 to 114) | behavior | `git show 637b60d749:.github/workflows/update-reviewer-stats.yml \| sed -n '53,114p' \| grep -c -E 'agent-intervention\|upload-artifact'` | VERIFIED: 3 |
| At 637b60d749 `publish-stats` starts at line 115, needs `update-stats`, and declares no environment | behavior | `git show 637b60d749:.github/workflows/update-reviewer-stats.yml \| sed -n '115,200p' \| grep -n -E '^    needs:\|^    environment:\|download-artifact@\|open_bot_pr.py' \| cut -c1-60 \| tr '\n' ' '` | VERIFIED: 6:    needs: update-stats 30:        uses: actions/download-artifact@9000827ccba6bdab6 43:          python3 -I scripts/ci/open_bot_pr.py \ |
| The two-job layout landed in 4273c7d5e2 (2026-11-11) | behavior | `git log -1 --format='%h %ad %s' --date=short 4273c7d5e2` | VERIFIED: 4273c7d5e2 2026-11-11 fix(ci): publish reviewer stats through a bot pull request (#7317) |
| Commit 3f145f26fd deleted the slash-command-quality workflow | behavior | `git show --format= --name-status 3f145f26fd -- .github/workflows \| grep -i 'slash-command' \| tr '\t' ' '` | VERIFIED: D .github/workflows/slash-command-quality.yml |
| The first debate log named in the pointer line exists | path | `ls .project-toolkit/critique/agent-env-adr-amendments-2026-11-25-debate-log.md` | VERIFIED: .project-toolkit/critique/agent-env-adr-amendments-2026-11-25-debate-log.md |
| The merged pull request body calls the commit scheduled workflow output | quote | `git log -1 --format=%b 637b60d749 \| grep -o -m1 'Scheduled workflow output committed on a bot branch'` | VERIFIED: Scheduled workflow output committed on a bot branch |

## Fourth pass, 2026-11-26

Rows for the two sentences reworded when `main` content was merged into branch `ci/delete-agent-env-jobs` (head `17db22a931`, 2026-11-26). The conflicts were resolved against `6c0a0fc5db` (2026-11-26), a local merge of `main` (`4d104e9a8f`, 2026-11-26) into the pull request #7630 head `f4557cc4f2` (2026-11-25). That merge commit was never pushed. Squash commit `dff887317c` (2026-11-26) on `main` holds the same tree. That tree carries the ADR-127 amendment from pull request #7629 (`4d459a2206`, 2026-11-26), whose check calls the runner's `acceptance_gate` in CI. The sentences "no CI job invokes them" and "No CI job runs `eval-prompt-change.py` now" were narrowed to match. Commands ran on 2026-11-26 in the merged working tree before the merge commit.

| Claim | Kind | Command | Result |
|---|---|---|---|
| `Validate PR` runs the ADR-127 evidence check | path | `grep -n 'Check ADR-127 skill rewrite evidence' .github/workflows/pr-validation.yml \| cut -d: -f1` | VERIFIED: 328 |
| The check loads the runner as a module | behavior | `grep -n 'spec_from_file_location' scripts/validation/skill_rewrite_evidence.py \| cut -d: -f1` | VERIFIED: 53 |
| The check calls the runner's `acceptance_gate` | behavior | `grep -n 'runner.acceptance_gate(' scripts/validation/skill_rewrite_evidence.py \| cut -d: -f1` | VERIFIED: 265 |
| No workflow file names `eval-prompt-change` | absence | `grep -rln 'eval-prompt-change' .github \| wc -l` | VERIFIED: 0 |
| The merged ADR cites no deleted workflow path | absence | `grep -c 'slash-command-quality.yml' .project-toolkit/architecture/ADR-057-prompt-behavioral-evaluation.md` | VERIFIED: 0 |
| Line 277 still holds "Do not add a new blocking gate." | quote | `sed -n '277p' .project-toolkit/architecture/ADR-057-prompt-behavioral-evaluation.md \| grep -c 'Do not add a new blocking gate.'` | VERIFIED: 1 |
| `6c0a0fc5db` and `dff887317c` hold the same tree | behavior | `git diff --quiet 6c0a0fc5db dff887317c; echo $?` | VERIFIED: 0 |
| Merging `main` into the pull request #7630 head gives the tree of `dff887317c`, from pushed commits only | behavior | `git merge-tree --write-tree f4557cc4f2 4d104e9a8f \| cut -c1-12; git rev-parse dff887317c^{tree} \| cut -c1-12` | VERIFIED: 984f58ed058c both times, run 2026-11-27 |
| The check calls no model | quote | none: the ADR-127 amendment states it ("It is deterministic and calls no model") and the first ledger section above verifies it | NOT RUN: cited from the amendment and the row "The check calls no model." above |

Correction, 2026-11-27: an earlier draft of this pass called `6c0a0fc5db` the last tip of the pull request #7630 branch. `git ls-remote origin refs/pull/7630/head` prints `f4557cc4f2`. The intro above now says what `6c0a0fc5db` is, and the last row gives a check that needs no local-only commit.


## Amendment 2026-11-28 (plugin eval migration)

Claims in ADR-057 Amendment 2026-11-28, read from the working tree on 2026-11-28. No paid `claude plugin eval` pass ran.

| # | Claim | Kind | Command | Result |
| --- | --- | --- | --- | --- |
| 1 | `claude plugin eval --help` lists `--tag`, `--judge-model`, `--max-cost-usd`, `--no-publish`, `--runs`, `--ablation`, `--json`. | behavior | `claude plugin eval --help \| grep -nE '^\s+--(tag\|judge-model\|max-cost-usd\|no-publish\|runs\|ablation\|json)'` | All seven printed (lines 15, 44, 47, 49, 66, 77, 81). VERIFIED |
| 2 | The host publishes the HTML report to claude.ai by default when the account supports it. | quote | same help, `--publish-report` text | "already the default when your account supports it". VERIFIED |
| 3 | ADR-127 decision 7 item 3 reads "The grade is a label match, not a quality judgment." | quote | `grep -n "label match, not a quality judgment" ADR-127-workflow-skills-are-script-drivers.md` | Line 175. VERIFIED |
| 4 | ADR-058 makes the LLM judge advisory and the gated signal deterministic. | behavior | `grep -n -i "advisory\|deterministic" ADR-058-agent-eval-discipline.md` | Lines 53, 156, 158, 309, 370. VERIFIED |
| 5 | `tests/evals/skill-scenarios/` and `tests/evals/<skill>-scenarios.json` exist today. | path | `ls -d tests/evals/skill-scenarios; ls tests/evals/*-scenarios.json` | Directory and files present. VERIFIED |
| 6 | `check_skill_rewrite_evidence.py` calls `load_runner()` and holds `_JUDGE_PATHS` and `_SKILL_PATH_PATTERNS`. | path | `grep -n "load_runner\|^_JUDGE_PATHS\|^_SKILL_PATH_PATTERNS" scripts/validation/check_skill_rewrite_evidence.py` | Lines 102, 115, 358, 438. VERIFIED |
| 7 | `evals/skill-rewrites/skill-doctor/` holds legacy results files, and `evals/_archive/` exists. | path | `ls evals/skill-rewrites/*/ evals/_archive` | `results.json` and `results-2.json` present, archive directory present. VERIFIED. The refuting seat found no `schema` key in `results.json`, so the ADR no longer says "schema 1" |
| 8 | The host default judge model is `haiku`, so "the host default is not a pin" is accurate. | quote | help, `--judge-model` | "Override LLM-grader model (default: haiku)". VERIFIED |
| 9 | The spec's buy-versus-build record says the host runner records real tool traces. | quote | `grep -n "real tool traces" SPEC-plugin-eval-migration.md` | Present in "Buy-vs-build decision". VERIFIED |
| 10 | The adapter exits 3 on a `claudeVersion` or `schemaVersion` mismatch. | behavior | plan task B2 acceptance criteria | Plan text only, code not written yet. NOT RUN, stated as a decision with PR B named |
| 11 | The served model is readable from the trace. | behavior | none | UNCONFIRMED by the spec. The ADR states the fallback and does not assert it. NOT RUN |
| 12 | Per-run cost rates. | count | none | INFERRED in the spec. The ADR states stage caps and the ceiling only. NOT RUN |
| 13 | The $50 monthly line and the 2 hour line are in Cost Expectations. | quote | `grep -n "exceeds \$50" ADR-057-prompt-behavioral-evaluation.md` | Present. VERIFIED |
