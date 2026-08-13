"""Tests for scripts/workflows/determine_should_run_from_filters.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.workflows.determine_should_run_from_filters import (
    main,
    parse_filter_keys,
    parse_filter_outputs,
    parse_force_run_events,
    should_run,
    write_output,
)


class TestShouldRun:
    def test_workflow_dispatch_always_runs(self) -> None:
        assert should_run("workflow_dispatch", {"context": "false"}, ["context"])

    def test_any_true_filter_runs(self) -> None:
        assert should_run(
            "pull_request",
            {"context": "false", "validator": "true"},
            ["context", "validator"],
        )

    def test_all_false_filters_skip(self) -> None:
        assert not should_run(
            "pull_request",
            {"context": "false", "validator": "false"},
            ["context", "validator"],
        )

    def test_missing_filters_skip(self) -> None:
        assert not should_run("pull_request", {}, ["context"])


class TestShouldRunForceRunEvents:
    """A whole-tree check must measure the mainline even when the diff misses it."""

    def test_forced_event_runs_despite_false_filters(self) -> None:
        assert should_run("push", {"rules": "false"}, ["rules"], {"push"})

    def test_forced_event_runs_when_filters_absent(self) -> None:
        assert should_run("push", {}, ["rules"], {"push"})

    def test_unlisted_event_still_skips(self) -> None:
        assert not should_run("pull_request", {"rules": "false"}, ["rules"], {"push"})

    def test_listed_event_does_not_force_a_different_event(self) -> None:
        assert not should_run("schedule", {"rules": "false"}, ["rules"], {"push"})

    def test_default_empty_preserves_prior_behavior(self) -> None:
        assert not should_run("push", {"rules": "false"}, ["rules"])

    def test_true_filter_still_runs_for_an_unlisted_event(self) -> None:
        assert should_run("pull_request", {"rules": "true"}, ["rules"], {"push"})

    def test_workflow_dispatch_runs_with_force_list_present(self) -> None:
        assert should_run("workflow_dispatch", {"rules": "false"}, ["rules"], {"push"})


class TestParseForceRunEvents:
    def test_splits_and_strips(self) -> None:
        assert parse_force_run_events("push, schedule") == frozenset(
            {"push", "schedule"}
        )

    def test_empty_string_yields_empty_set(self) -> None:
        assert parse_force_run_events("") == frozenset()

    def test_drops_blank_entries(self) -> None:
        assert parse_force_run_events("push,, ,schedule") == frozenset(
            {"push", "schedule"}
        )


class TestParseFilterKeys:
    def test_splits_comma_separated_keys(self) -> None:
        assert parse_filter_keys("skills, context,validator") == [
            "skills",
            "context",
            "validator",
        ]


class TestParseFilterOutputs:
    def test_null_from_a_skipped_paths_step_is_empty(self) -> None:
        assert parse_filter_outputs("null") == {}

    def test_non_object_json_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_filter_outputs("[]")


class TestWriteOutput:
    def test_writes_named_output(self, tmp_path: Path) -> None:
        output = tmp_path / "github_output"

        write_output(output, "should-run-budget", True)

        assert output.read_text(encoding="utf-8") == "should-run-budget=true\n"

    @pytest.mark.parametrize("name", ["bad name", "bad\nname", "1bad"])
    def test_rejects_invalid_output_name(self, tmp_path: Path, name: str) -> None:
        output = tmp_path / "github_output"

        with pytest.raises(ValueError):
            write_output(output, name, True)


class TestMain:
    def test_writes_output_from_environment(self, tmp_path: Path, monkeypatch) -> None:
        output = tmp_path / "github_output"
        monkeypatch.setenv("OUTPUT_NAME", "should-run-compliance")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GH_EVENT_NAME", "pull_request")
        monkeypatch.setenv("FILTER_KEYS", "skills,context,validator")
        monkeypatch.setenv(
            "FILTER_OUTPUTS",
            '{"skills":"false","context":"true","validator":"false"}',
        )

        rc = main()

        assert rc == 0
        assert output.read_text(encoding="utf-8") == "should-run-compliance=true\n"

    def test_returns_two_when_required_env_missing(self, monkeypatch) -> None:
        monkeypatch.delenv("OUTPUT_NAME", raising=False)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

        assert main() == 2

    def test_returns_two_for_invalid_filter_json(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        output = tmp_path / "github_output"
        monkeypatch.setenv("OUTPUT_NAME", "should-run-compliance")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GH_EVENT_NAME", "pull_request")
        monkeypatch.setenv("FILTER_KEYS", "skills")
        monkeypatch.setenv("FILTER_OUTPUTS", "{")

        assert main() == 2

    def test_force_run_events_env_overrides_false_filters(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        output = tmp_path / "github_output"
        monkeypatch.setenv("OUTPUT_NAME", "should-run-budget")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GH_EVENT_NAME", "push")
        monkeypatch.setenv("FILTER_KEYS", "rules,validator")
        monkeypatch.setenv("FILTER_OUTPUTS", '{"rules":"false","validator":"false"}')
        monkeypatch.setenv("FORCE_RUN_EVENTS", "push")

        rc = main()

        assert rc == 0
        assert output.read_text(encoding="utf-8") == "should-run-budget=true\n"

    def test_absent_force_run_events_env_leaves_push_gated(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        output = tmp_path / "github_output"
        monkeypatch.setenv("OUTPUT_NAME", "should-run-budget")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GH_EVENT_NAME", "push")
        monkeypatch.setenv("FILTER_KEYS", "rules,validator")
        monkeypatch.setenv("FILTER_OUTPUTS", '{"rules":"false","validator":"false"}')
        monkeypatch.delenv("FORCE_RUN_EVENTS", raising=False)

        rc = main()

        assert rc == 0
        assert output.read_text(encoding="utf-8") == "should-run-budget=false\n"
