# ADR-087 claims ledger

Verified 2026-11-25 for issue #7642, covering the "Amendment 2026-11-25" text and
`.project-toolkit/analysis/7678-adr-087-trusted-controller-and-null-control.md`.

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| Sub-issues #7678 to #7689 are children of #7642, in that order. | Behavior | `gh api repos/rjmurillo/ai-agents/issues/7642/sub_issues --jq '.[].number'` | `7678 ... 7689`, twelve rows. VERIFIED |
| #7678 blocks #7686 and #7687. | Behavior | `set_issue_relationship.py --issue 7678 --relation blocking --target 7686 7687` | Both `linked`, `failed: []`. VERIFIED |
| #7679 and #7682 are closed as completed. | Behavior | `close_issue.py` output | `state: closed`, `reason: completed` for both. VERIFIED |
| #3436 is closed. | Behavior | `gh issue view 3436 --json state` | `CLOSED`. VERIFIED |
| `optimize-artifact.py report` exists and reads the test group. | Path | `optimize-artifact.py` lines 3252-3269 | `sub.add_parser("report", help="read the test group once, at the end")`. VERIFIED |
| The controller runs scorer, `extract`, `split`, and `gate` itself. | Behavior | `scripts/eval/eval_controller.py`, `Controller.score` and `Controller.run` | Each is a subprocess the controller starts. VERIFIED |
| The proposer workspace holds `feedback.json` (step, artifact path, opt results, opt score, consultations left, last decision) and opt task files. | Behavior | `test_proposer_never_sees_a_held_out_id`, `test_accept_keeps_the_candidate_and_reports_one_bit`, `test_opt_task_files_are_copied_and_nothing_else` | 87 of 87 tests pass after the PR #7699 review fixes. VERIFIED |
| Every step exit restores the incumbent before the gate. | Behavior | `test_reject_restores_the_incumbent`, `test_proposer_that_edits_then_fails_leaves_the_incumbent`, `test_artifact_changed_during_scoring_is_refused` | Pass. VERIFIED |
| A planted workspace symlink does not redirect a controller write. | Behavior | `test_planted_feedback_symlink_is_not_followed` | Pass. VERIFIED |
| `deny_paths` is required, and `policy` lists state, config, and `deny_paths`. | Behavior | `test_bad_config_is_refused[deny_paths-value9]`, `test_policy_lists_state_and_task_paths` | Pass. VERIFIED |
| Both reports set `flaky_halt_threshold_crossed: true` and `recommendation: halt-due-to-flakiness`. | Count | Read both `report.json` files | As stated. VERIFIED |
| An edited task-definition path refuses scoring. | Behavior | `test_edited_task_definition_refuses_before_scoring` | Exit 2, no candidate run directory. VERIFIED |
| The gate cap and ledger root come from the launcher config. | Behavior | `Controller.run` passes `config.max_consultations` and sets `EVAL_LEDGER_DIR` to `state_dir/ledger`; `test_state_dir_is_private_and_holds_the_ledger` | Pass. VERIFIED |
| Python cannot stop a same-user process from reading a file. | Behavior | POSIX permission model: mode `0700` restricts other users, not the owner | Stated as a limit, not a property. VERIFIED |
| The hub does not serve `claude-sonnet-4-6`. | Behavior | `claude -p "reply OK" --model claude-sonnet-4-6` | `API Error: 400 unknown provider for model claude-sonnet-4-6`. VERIFIED |
| Both new reports agree on `fixture_set_sha` and `agent_prompt_sha`. | Count | Read both `report.json` files | `f6310eb016cb...` and `dfcb7790a0e8...` in both. VERIFIED |
| Both runs used `claude-sonnet-5-5`, three runs, zero errors. | Count | `model_id`, `per_fixture_pass_rates` lengths, `error_count` | As stated. VERIFIED |
| Agent recall 0.583 and 0.625; baseline 0.729 and 0.708. | Count | `agent_recall`, `baseline_recall` | 0.583333, 0.625, 0.729167, 0.708333. VERIFIED |
| Flaky fixtures 5 of 8 and 4 of 8. | Count | `flaky_fixtures_detected` | 5 and 4 ids. VERIFIED |
| At threshold 1.0, both runs pass 2 of 8, and the gate ties at 0/3. | Behavior | `extract`, `split --seed 7642`, `gate` | REJECT, gain 0, loss 0, p 1.0, `corpus_verified` and `corpus_pinned` true. VERIFIED |
| A001, A004, A007 agent means moved as stated. | Count | Per-fixture agent scores | 0.33 to 0.50, 0.83 to 0.67, 0.50 to 0.83. VERIFIED |
| At threshold 0.5, only A001 flips, and it is in `opt`. | Behavior | `extract --pass-threshold 0.5`; `split.json` `sel` is A006, A008, A004 | One flip; gate REJECT tie at 1.0. VERIFIED |
| `optimize-artifact.py` remains a supported direct path. | Behavior | `scripts/eval/README.md` still documents the direct loop | VERIFIED |
| An artifact swapped for a symlink is refused, and the restore does not follow it. | Behavior | `test_artifact_swapped_for_symlink_cannot_redirect_the_restore` | Exit 2, denied file unchanged. VERIFIED |
| A denied file edited on a NO_CHANGE step stops the loop. | Behavior | `test_denied_file_edited_on_a_no_change_step_stops_the_loop` | Exit 2 after one step. VERIFIED |
| A `setsid` grandchild cannot stretch the timeout. | Behavior | `test_escaped_grandchild_cannot_stretch_the_timeout` | Exit 3 under 10 s with a 1 s timeout and a 20 s grandchild. VERIFIED |
| A proposer that exceeds the timeout is stopped and the incumbent stays. | Behavior | `test_proposer_timeout_is_external` | Exit 3, artifact unchanged. VERIFIED |
| On Windows only the direct child is killed. | Behavior | `_kill_group` calls `proc.kill()` when `os.name != "posix"` | Code read; not run on Windows. VERIFIED (code), NOT RUN (Windows) |
| Restores keep the artifact's mode. | Behavior | `test_artifact_mode_survives_restore_and_accept`; fails with the `os.chmod` line removed | 0o755 kept. VERIFIED |
| A hard-linked artifact is refused. | Behavior | `test_artifact_hard_linked_to_a_denied_file_is_refused` | Exit 2. VERIFIED |
| The summary digest is read from disk. | Behavior | `test_summary_digest_is_the_file_on_disk` | Pass. VERIFIED |
| A gate exit 1 without a comparison stops the run and spends nothing. | Behavior | `test_gate_refusal_stops_the_run_and_spends_nothing` | Exit 3, `abort` logged. VERIFIED |
| `max_p` reaches the gate. | Behavior | `test_max_p_reaches_the_gate` | `--max-p 0.5` in the gate argv. VERIFIED |
| Scoring that edits controller state is refused before the gate. | Behavior | `test_scorer_that_edits_controller_state_is_refused` | Exit 2, no gate event. VERIFIED |
| The workspace is emptied each step. | Behavior | `test_workspace_is_emptied_between_steps` | Step 2 lists only `feedback.json` and `tasks`. VERIFIED |
| A `trusted_paths` edit stops the loop. | Behavior | `test_trusted_path_edit_stops_the_loop` | Exit 2. VERIFIED |
| The proposer env drops `EVAL_LEDGER_DIR` and honors an allowlist. | Behavior | `test_proposer_env_drops_the_ledger_variable_and_honors_an_allowlist` | Pass. VERIFIED |
| An artifact replaced by a directory is refused and restored. | Behavior | `test_artifact_replaced_by_a_directory_is_refused_and_restored` | Exit 2, file restored. VERIFIED |
| Child stderr goes to the log, not the launcher's stderr. | Behavior | `test_failure_detail_goes_to_the_log_not_stderr` | Pass. VERIFIED |
| SIGTERM raises so the restore runs. | Behavior | `test_sigterm_handler_raises_a_controller_error` (handler only; no signal delivered) | Pass. VERIFIED (handler), NOT RUN (live signal) |
| Held-out tasks in the null control were A004, A006, A008. | Count | `split.json` `sel` from `split --seed 7642` | VERIFIED |
| An artifact inside the workspace, or a non-empty workspace, is refused at start. | Behavior | `test_artifact_inside_the_workspace_is_refused`, `test_non_empty_workspace_is_refused_and_left_alone` | Exit 2, files untouched. VERIFIED |
| A new directory in a trusted path stops the loop. | Behavior | `test_new_file_in_a_trusted_directory_stops_the_loop` | Exit 2. VERIFIED |
| Optimizer calls carry `PYTHONPYCACHEPREFIX` under state. | Behavior | `test_gate_runs_with_bytecode_cache_under_state` | Every call. VERIFIED |
| Scorer runs carry `PYTHONPYCACHEPREFIX` inside their run directory. | Behavior | `test_scorer_runs_with_its_bytecode_cache_in_its_run_dir` | Pass. VERIFIED |
| A task id that could leave its directory is refused. | Behavior | `test_task_file_refuses_ids_that_leave_the_directory` (4 cases) | Pass. VERIFIED |
| `scorer_exit_codes` lets a run with failing tests reach the gate; the default refuses exit 1. | Behavior | `test_scorer_exit_codes_accept_a_run_with_failing_tests`, `test_scorer_exit_one_is_refused_by_default` | Pass. VERIFIED |
| A failed scorer's collected output is moved into state. | Behavior | `test_failed_scorer_output_is_moved_out_of_the_checkout` | Pass. VERIFIED |
| A baseline scorer that edits the artifact or a task file is refused before the split. | Behavior | `test_baseline_scorer_that_edits_the_artifact_is_refused`, `test_baseline_scorer_that_edits_a_task_file_is_refused` | Pass. VERIFIED |
| Linked or same-named task files are refused. | Behavior | `test_task_file_that_is_a_link_is_refused`, `test_task_files_sharing_a_name_are_refused` | Pass. VERIFIED |
| A launcher artifact symlink resolves to its target. | Behavior | `test_launcher_artifact_symlink_resolves_to_its_target` | Pass. VERIFIED |
| SIGTERM during a restore waits for the write. | Behavior | `test_sigterm_during_a_restore_waits_for_the_write` (handler invoked mid-write; no live signal) | Pass. VERIFIED |
| `proposer_env` is required. | Behavior | `test_bad_config_is_refused[proposer_env-None]` | Pass. VERIFIED |
| An artifact inside `state_dir` is refused; a tamper refusal still collects the scorer report. | Behavior | `test_artifact_inside_state_is_refused`, `test_tamper_refusal_still_collects_the_scorer_report` | Pass. VERIFIED |
| A failed baseline scoring run restores the incumbent. | Behavior | `test_baseline_scorer_that_edits_the_artifact_is_refused` | Artifact unchanged after exit 2. VERIFIED |
| A symlinked deny directory resolves and is digested by content. | Behavior | `test_symlinked_deny_directory_is_digested_by_content` | Exit 2 on an edit inside it. VERIFIED |
| An artifact inside `scripts/eval/` is refused at load. | Behavior | `test_artifact_inside_the_eval_directory_is_refused` | Pass. VERIFIED |
| An optimizer call that hangs is stopped within its timeout, with its group killed. | Behavior | `test_optimizer_timeout_is_bounded_and_external` | Exit 3 under 10 s with a 1 s timeout. VERIFIED |
| The artifact may not be the config; a planted `results.json` is not written through. | Behavior | `test_artifact_that_is_the_config_is_refused`, `test_planted_results_file_is_not_written_through` | Pass. VERIFIED |
| Every `collect` output is moved even when one is missing. | Behavior | `test_every_collect_output_is_moved_even_when_one_is_missing` | Pass. VERIFIED |
| A baseline `OSError` still restores the incumbent. | Behavior | `test_baseline_os_error_still_restores` | Pass. VERIFIED |
| An unreadable protected directory is refused. | Behavior | `test_unreadable_protected_directory_is_refused` | Pass (non-root POSIX). VERIFIED |
| On Windows the proposer keeps startup variables, matched case-insensitively. | Behavior | `test_windows_proposer_env_keeps_startup_variables` (`os.name` patched; not run on Windows) | Pass. VERIFIED (logic), NOT RUN (Windows) |
| An oversized optimizer reply is refused; `policy` names `collect` paths. | Behavior | `test_oversized_optimizer_reply_is_refused`, `test_policy_names_collect_paths` | Pass. VERIFIED |
