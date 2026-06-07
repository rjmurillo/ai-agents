"""Tests for scripts/workflows/determine_should_run_from_filters.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.workflows.determine_should_run_from_filters import (
    main,
    parse_filter_keys,
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


class TestParseFilterKeys:
    def test_splits_comma_separated_keys(self) -> None:
        assert parse_filter_keys("skills, context,validator") == [
            "skills",
            "context",
            "validator",
        ]


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
