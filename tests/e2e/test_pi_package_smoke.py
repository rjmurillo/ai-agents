"""Real-runtime smoke for the Pi package (ADR-115 Decisions 5, 9, 10)."""

from __future__ import annotations

from tests.e2e.pi_package_contract_cases import (
    test_get_commands_line_fails_clearly_when_no_response_is_present,
    test_get_commands_line_skips_a_banner_before_the_response,
    test_package_skill_paths_ignores_skills_not_from_this_package,
    test_package_skill_paths_keeps_package_skills_under_the_repo,
    test_package_skill_paths_rejects_an_unexpected_response,
    test_package_skill_paths_rejects_non_json,
    test_pi_binary_finds_pi_on_path_when_pi_bin_is_unset,
    test_pi_binary_prefers_pi_bin_and_returns_none_when_it_is_missing,
    test_pi_binary_returns_none_when_pi_bin_is_unset_and_path_has_no_pi,
    test_pi_env_isolates_config_home_and_drops_credentials,
    test_skill_script_env_drops_plugin_root_variables,
)
from tests.e2e.pi_package_runtime_cases import (
    test_a_script_copy_with_lib_at_the_resolver_location_passes,
    test_a_script_copy_without_lib_at_the_resolver_location_fails,
    test_pi_package_loads_every_skill_and_a_skill_script_finds_lib,
    test_shipped_skill_names_lists_the_skill_directories,
)

__all__ = [
    "test_a_script_copy_with_lib_at_the_resolver_location_passes",
    "test_a_script_copy_without_lib_at_the_resolver_location_fails",
    "test_get_commands_line_fails_clearly_when_no_response_is_present",
    "test_get_commands_line_skips_a_banner_before_the_response",
    "test_package_skill_paths_ignores_skills_not_from_this_package",
    "test_package_skill_paths_keeps_package_skills_under_the_repo",
    "test_package_skill_paths_rejects_an_unexpected_response",
    "test_package_skill_paths_rejects_non_json",
    "test_pi_binary_finds_pi_on_path_when_pi_bin_is_unset",
    "test_pi_binary_prefers_pi_bin_and_returns_none_when_it_is_missing",
    "test_pi_binary_returns_none_when_pi_bin_is_unset_and_path_has_no_pi",
    "test_pi_env_isolates_config_home_and_drops_credentials",
    "test_pi_package_loads_every_skill_and_a_skill_script_finds_lib",
    "test_shipped_skill_names_lists_the_skill_directories",
    "test_skill_script_env_drops_plugin_root_variables",
]
