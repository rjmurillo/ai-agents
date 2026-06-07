"""Tests for scripts/quality_gate/determine_should_run.py.

Pins the decision logic of the extracted ``Determine if review should run``
workflow step across every branch of the original bash block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality_gate.determine_should_run import (
    decide,
    main,
    write_should_run_review,
)


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    @pytest.mark.parametrize("bot", ["dependabot[bot]", "github-actions[bot]"])
    def test_bot_actor_skips_even_when_relevant(self, bot: str) -> None:
        should_run, message = decide(bot, "pull_request", "true")
        assert should_run is False
        assert f"bot actor: {bot}" in message

    def test_workflow_dispatch_runs(self) -> None:
        should_run, message = decide("alice", "workflow_dispatch", "false")
        assert should_run is True
        assert "manual trigger" in message

    def test_relevant_changes_run(self) -> None:
        should_run, message = decide("alice", "pull_request", "true")
        assert should_run is True
        assert "relevant files changed" in message

    def test_no_relevant_changes_skip(self) -> None:
        should_run, message = decide("alice", "pull_request", "false")
        assert should_run is False
        assert "no relevant files changed" in message

    def test_bot_precedence_over_workflow_dispatch(self) -> None:
        # Bot check comes first in the original block.
        should_run, _ = decide("dependabot[bot]", "workflow_dispatch", "true")
        assert should_run is False

    def test_empty_relevant_is_treated_as_skip(self) -> None:
        should_run, message = decide("alice", "pull_request", "")
        assert should_run is False
        assert "no relevant files changed" in message


# ---------------------------------------------------------------------------
# write_should_run_review
# ---------------------------------------------------------------------------


class TestWriteShouldRunReview:
    def test_writes_true(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_should_run_review(output, True)
        assert output.read_text(encoding="utf-8") == "should-run-review=true\n"

    def test_writes_false(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_should_run_review(output, False)
        assert output.read_text(encoding="utf-8") == "should-run-review=false\n"

    def test_appends(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.write_text("existing=1\n", encoding="utf-8")
        write_should_run_review(output, True)
        assert (
            output.read_text(encoding="utf-8")
            == "existing=1\nshould-run-review=true\n"
        )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_relevant_writes_true_and_returns_zero(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main(
            ["--gh-actor", "alice", "--gh-event-name", "pull_request", "--relevant", "true"]
        )
        assert rc == 0
        assert "should-run-review=true" in output.read_text(encoding="utf-8")

    def test_bot_writes_false(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main(
            [
                "--gh-actor",
                "dependabot[bot]",
                "--gh-event-name",
                "pull_request",
                "--relevant",
                "true",
            ]
        )
        assert rc == 0
        assert "should-run-review=false" in output.read_text(encoding="utf-8")

    def test_reads_from_env(self, tmp_path, monkeypatch) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("GH_ACTOR", "alice")
        monkeypatch.setenv("GH_EVENT_NAME", "workflow_dispatch")
        monkeypatch.setenv("RELEVANT", "false")
        rc = main([])
        assert rc == 0
        assert "should-run-review=true" in output.read_text(encoding="utf-8")

    def test_missing_github_output_returns_two(self, monkeypatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        rc = main(
            ["--gh-actor", "alice", "--gh-event-name", "pull_request", "--relevant", "true"]
        )
        assert rc == 2

    def test_prints_relevant_line_only_in_else_branch(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        main(
            ["--gh-actor", "alice", "--gh-event-name", "pull_request", "--relevant", "true"]
        )
        captured = capsys.readouterr()
        assert "Relevant files changed: true" in captured.out

    def test_bot_does_not_print_relevant_line(self, tmp_path, monkeypatch, capsys) -> None:
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        main(
            [
                "--gh-actor",
                "dependabot[bot]",
                "--gh-event-name",
                "pull_request",
                "--relevant",
                "true",
            ]
        )
        captured = capsys.readouterr()
        assert "Relevant files changed" not in captured.out
