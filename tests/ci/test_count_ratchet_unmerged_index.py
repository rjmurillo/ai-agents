"""A conflicted path must be counted once, not once per merge stage (#4746)."""

from __future__ import annotations

from tests.ci.count_ratchet_unmerged_index_cases import (
    test_a_clean_enumeration_is_returned_unchanged,
    test_a_clean_tree_lists_every_path_once_and_says_nothing,
    test_a_large_conflict_is_summarised_rather_than_listed,
    test_a_resolved_merge_lists_every_path_once_and_says_nothing,
    test_a_three_stage_conflict_collapses_to_one_path,
    test_a_two_stage_conflict_collapses_too,
    test_an_empty_enumeration_reports_nothing,
    test_each_conflicted_path_is_reported_once_however_many_stages_it_has,
    test_first_occurrence_wins_and_the_rest_of_the_order_survives,
    test_git_repeats_an_unmerged_path_once_per_stage,
    test_the_note_names_the_conflicted_path_and_the_working_tree_caveat,
    test_tracked_files_lists_a_conflicted_path_once,
    test_tracked_files_lists_a_two_stage_conflict_once,
)
from tests.ci.count_ratchet_unmerged_integration_cases import (
    test_a_conflicted_file_counts_the_same_as_the_tree_it_resolves_to,
    test_one_run_prints_the_mid_merge_note_once,
    test_two_counting_scopes_still_print_one_note,
)

__all__ = [
    "test_a_clean_enumeration_is_returned_unchanged",
    "test_a_clean_tree_lists_every_path_once_and_says_nothing",
    "test_a_conflicted_file_counts_the_same_as_the_tree_it_resolves_to",
    "test_a_large_conflict_is_summarised_rather_than_listed",
    "test_a_resolved_merge_lists_every_path_once_and_says_nothing",
    "test_a_three_stage_conflict_collapses_to_one_path",
    "test_a_two_stage_conflict_collapses_too",
    "test_an_empty_enumeration_reports_nothing",
    "test_each_conflicted_path_is_reported_once_however_many_stages_it_has",
    "test_first_occurrence_wins_and_the_rest_of_the_order_survives",
    "test_git_repeats_an_unmerged_path_once_per_stage",
    "test_one_run_prints_the_mid_merge_note_once",
    "test_the_note_names_the_conflicted_path_and_the_working_tree_caveat",
    "test_tracked_files_lists_a_conflicted_path_once",
    "test_tracked_files_lists_a_two_stage_conflict_once",
    "test_two_counting_scopes_still_print_one_note",
]
