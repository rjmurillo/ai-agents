"""Tests for scripts/ci/retrospective_gate.py (ADR-006 extraction, issue #3523).

Parity with the shell block this replaced is the bar. Where the port diverges,
a test names the divergence so a future reader sees it was chosen, not missed.
"""

from __future__ import annotations

import pytest

from scripts.ci import retrospective_gate as gate


class TestIsBot:
    @pytest.mark.parametrize(
        "author",
        [
            "dependabot[bot]",
            "renovate[bot]",
            "github-actions[bot]",
            "copilot[bot]",
            "coderabbitai[bot]",
        ],
    )
    def test_every_name_in_the_shell_case_arm_is_recognized(self, author: str) -> None:
        assert gate.is_bot(author)

    @pytest.mark.parametrize("author", ["rjmurillo", "", "dependabot", "somebody[bot]"])
    def test_humans_and_unlisted_bots_are_not_bots(self, author: str) -> None:
        assert not gate.is_bot(author)

    def test_matching_is_case_sensitive_like_the_shell_case_statement(self) -> None:
        # The original used a POSIX `case` arm, which is case-sensitive. Keep it.
        assert not gate.is_bot("Dependabot[bot]")


class TestIsFork:
    def test_same_repository_is_not_a_fork(self) -> None:
        assert not gate.is_fork("rjmurillo/ai-agents", "rjmurillo/ai-agents")

    def test_different_repository_is_a_fork(self) -> None:
        assert gate.is_fork("someone/ai-agents", "rjmurillo/ai-agents")

    def test_both_empty_is_not_a_fork(self) -> None:
        # Matches `[ "" != "" ]` in the original: falls through, does not skip.
        assert not gate.is_fork("", "")

    def test_empty_head_against_a_real_base_is_a_fork(self) -> None:
        assert gate.is_fork("", "rjmurillo/ai-agents")


class TestReviewCommentCount:
    @pytest.mark.parametrize(("raw", "expected"), [("12", 12), ("0", 0), ("9", 9), (" 7 ", 7)])
    def test_numeric_values_parse(self, raw: str, expected: int) -> None:
        assert gate.review_comment_count(raw) == expected

    @pytest.mark.parametrize("raw", ["", "abc", "5x", "1.5", None])
    def test_unparseable_values_are_zero_not_an_exception(self, raw: str | None) -> None:
        # Probed against bash: `[ "abc" -ge 10 ]` under `set -euo pipefail`
        # writes to stderr and evaluates false. It does not abort the step,
        # because `set -e` is suppressed inside an `if` condition.
        assert gate.review_comment_count(raw) == 0

    def test_negative_values_parse_and_do_not_escalate(self) -> None:
        assert gate.review_comment_count("-3") == -3


class TestShouldEscalate:
    def test_a_merged_quiet_plain_titled_pr_does_not_escalate(self) -> None:
        assert not gate.should_escalate(merged="true", title="feat: add thing", review_comments="0")

    def test_an_unmerged_close_escalates(self) -> None:
        assert gate.should_escalate(merged="false", title="feat: add thing", review_comments="0")

    def test_an_empty_merged_value_escalates(self) -> None:
        assert gate.should_escalate(merged="", title="feat: add thing", review_comments="0")

    @pytest.mark.parametrize(
        "title",
        [
            "rework: the parser",
            "REWORK the parser",
            "chore: retry the deploy",
            "fix-cycle 3",
            "to improve coverage",
            "to-improve coverage",
            "hotfix: null deref",
            "Hotfix: null deref",
        ],
    )
    def test_rework_markers_escalate(self, title: str) -> None:
        assert gate.should_escalate(merged="true", title=title, review_comments="0")

    @pytest.mark.parametrize(
        "title",
        ["reworking the parser", "hotfixes applied", "retrying later", "network"],
    )
    def test_word_boundaries_keep_substrings_from_escalating(self, title: str) -> None:
        assert not gate.should_escalate(merged="true", title=title, review_comments="0")

    def test_ten_review_comments_escalate(self) -> None:
        assert gate.should_escalate(merged="true", title="feat: x", review_comments="10")

    def test_nine_review_comments_do_not_escalate(self) -> None:
        assert not gate.should_escalate(merged="true", title="feat: x", review_comments="9")

    def test_an_unparseable_comment_count_does_not_escalate_on_its_own(self) -> None:
        assert not gate.should_escalate(merged="true", title="feat: x", review_comments="lots")


class TestDecide:
    def test_workflow_dispatch_runs_unconditionally_even_for_a_bot(self) -> None:
        out = gate.decide(
            {
                "EVENT_NAME": "workflow_dispatch",
                "PR_NUMBER": "42",
                "PR_AUTHOR": "dependabot[bot]",
                "DISPATCH_ESCALATE": "true",
            }
        )
        assert out == {
            "should_run": "true",
            "pr_number": "42",
            "merged": "unknown",
            "escalate_depth": "true",
        }

    def test_workflow_dispatch_defaults_escalation_to_false_when_unset(self) -> None:
        out = gate.decide({"EVENT_NAME": "workflow_dispatch", "PR_NUMBER": "7"})
        assert out["escalate_depth"] == "false"

    def test_workflow_dispatch_defaults_escalation_to_false_when_empty(self) -> None:
        # `${DISPATCH_ESCALATE:-false}` in the original treats empty as unset.
        out = gate.decide(
            {"EVENT_NAME": "workflow_dispatch", "PR_NUMBER": "7", "DISPATCH_ESCALATE": ""}
        )
        assert out["escalate_depth"] == "false"

    def test_a_bot_author_is_skipped(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = gate.decide({"EVENT_NAME": "pull_request", "PR_AUTHOR": "renovate[bot]"})
        assert out == {"should_run": "false"}
        assert "Skipping retrospective for bot author" in capsys.readouterr().out

    def test_a_fork_head_is_skipped(self, capsys: pytest.CaptureFixture[str]) -> None:
        out = gate.decide(
            {
                "EVENT_NAME": "pull_request",
                "PR_AUTHOR": "rjmurillo",
                "PR_HEAD_REPO": "fork/ai-agents",
                "PR_BASE_REPO": "rjmurillo/ai-agents",
            }
        )
        assert out == {"should_run": "false"}
        assert "Skipping retrospective for fork PR" in capsys.readouterr().out

    def test_the_bot_check_runs_before_the_fork_check(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Both apply; the original's ordering surfaces the bot reason.
        gate.decide(
            {
                "EVENT_NAME": "pull_request",
                "PR_AUTHOR": "copilot[bot]",
                "PR_HEAD_REPO": "fork/ai-agents",
                "PR_BASE_REPO": "rjmurillo/ai-agents",
            }
        )
        assert "bot author" in capsys.readouterr().out

    def test_a_merged_same_repo_human_pr_runs_without_escalation(self) -> None:
        out = gate.decide(
            {
                "EVENT_NAME": "pull_request",
                "PR_NUMBER": "100",
                "PR_AUTHOR": "rjmurillo",
                "PR_MERGED": "true",
                "PR_TITLE": "feat: add thing",
                "PR_HEAD_REPO": "rjmurillo/ai-agents",
                "PR_BASE_REPO": "rjmurillo/ai-agents",
                "REVIEW_COMMENTS": "2",
            }
        )
        assert out == {
            "should_run": "true",
            "pr_number": "100",
            "merged": "true",
            "escalate_depth": "false",
        }

    def test_an_unmerged_pr_runs_with_escalation(self) -> None:
        out = gate.decide(
            {
                "EVENT_NAME": "pull_request",
                "PR_NUMBER": "101",
                "PR_AUTHOR": "rjmurillo",
                "PR_MERGED": "false",
                "PR_TITLE": "feat: add thing",
                "PR_HEAD_REPO": "rjmurillo/ai-agents",
                "PR_BASE_REPO": "rjmurillo/ai-agents",
                "REVIEW_COMMENTS": "0",
            }
        )
        assert out["escalate_depth"] == "true"
        assert out["merged"] == "false"

    def test_an_entirely_empty_environment_still_produces_a_full_output_set(self) -> None:
        out = gate.decide({})
        assert set(out) == {"should_run", "pr_number", "merged", "escalate_depth"}
        assert out["escalate_depth"] == "true"


class TestWriteOutputs:
    def test_outputs_append_one_key_per_line(self, tmp_path) -> None:
        path = tmp_path / "out.txt"
        path.write_text("existing=1\n", encoding="utf-8")
        gate.write_outputs(path, {"a": "1", "b": "2"})
        assert path.read_text(encoding="utf-8") == "existing=1\na=1\nb=2\n"


class TestMain:
    def test_a_missing_github_output_is_a_config_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert gate.main([], env={}) == gate.EXIT_CONFIG
        assert "GITHUB_OUTPUT is required" in capsys.readouterr().err

    def test_an_empty_github_output_is_a_config_error(self) -> None:
        assert gate.main([], env={"GITHUB_OUTPUT": ""}) == gate.EXIT_CONFIG

    def test_main_writes_the_decision_and_returns_ok(self, tmp_path) -> None:
        out = tmp_path / "out.txt"
        rc = gate.main(
            [],
            env={
                "GITHUB_OUTPUT": str(out),
                "EVENT_NAME": "pull_request",
                "PR_NUMBER": "5",
                "PR_AUTHOR": "rjmurillo",
                "PR_MERGED": "true",
                "PR_TITLE": "docs: tidy",
                "PR_HEAD_REPO": "rjmurillo/ai-agents",
                "PR_BASE_REPO": "rjmurillo/ai-agents",
                "REVIEW_COMMENTS": "1",
            },
        )
        assert rc == gate.EXIT_OK
        body = out.read_text(encoding="utf-8")
        assert "should_run=true" in body
        assert "pr_number=5" in body
        assert "escalate_depth=false" in body

    def test_a_skip_writes_only_should_run(self, tmp_path) -> None:
        out = tmp_path / "out.txt"
        gate.main(
            [],
            env={
                "GITHUB_OUTPUT": str(out),
                "EVENT_NAME": "pull_request",
                "PR_AUTHOR": "copilot[bot]",
            },
        )
        assert out.read_text(encoding="utf-8") == "should_run=false\n"

    def test_main_reads_the_process_environment_when_none_is_supplied(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
        monkeypatch.setenv("PR_NUMBER", "9")
        assert gate.main([]) == gate.EXIT_OK
        assert "pr_number=9" in out.read_text(encoding="utf-8")
