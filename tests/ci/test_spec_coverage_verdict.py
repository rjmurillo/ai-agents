"""Tests for scripts/ci/spec_coverage_verdict.py (issue #6182)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci import spec_coverage_verdict as verdict_module
from scripts.ci.spec_coverage_verdict import (
    ACCEPTANCE_HEADING,
    EXIT_CONFIG,
    EXIT_FAIL,
    EXIT_OK,
    decide,
    main,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "spec_coverage_verdict.py"

ALL_CHECKED = "## Acceptance criteria\n\n- [x] one\n- [X] two\n"
ONE_UNCHECKED = "## Acceptance criteria\n\n- [x] one\n- [ ] two\n- [ ] three\n"
NUMBERED_ONLY = "## Acceptance criteria\n\n1. one\n2. two\n"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HAS_SPECS",
        "PR_BODY",
        "EVENT_NAME",
        "PR_NUMBER",
        "GITHUB_REPOSITORY",
        "GITHUB_STEP_SUMMARY",
    ):
        monkeypatch.delenv(name, raising=False)


class TestDecide:
    def test_no_spec_passes_with_any_body(self) -> None:
        assert decide(False, "").passed
        assert decide(False, ONE_UNCHECKED).passed

    def test_spec_without_section_fails_and_names_heading(self) -> None:
        result = decide(True, "Just prose, no list.")
        assert not result.passed
        assert ACCEPTANCE_HEADING in result.reason

    def test_spec_with_empty_body_fails(self) -> None:
        assert not decide(True, "").passed

    def test_numbered_list_is_not_a_checkbox_section(self) -> None:
        result = decide(True, NUMBERED_ONLY)
        assert not result.passed
        assert ACCEPTANCE_HEADING in result.reason

    def test_missing_section_states_the_item_syntax(self) -> None:
        result = decide(True, "Just prose, no list.")
        assert "`- [ ] text` or `- [x] text`" in result.reason
        assert "does not accept" not in result.reason
        assert "heading is present" not in result.reason

    def test_suffixed_heading_is_named_as_the_near_miss(self) -> None:
        body = "## Acceptance criteria (draft)\n\n- [x] one\n"
        result = decide(True, body)
        assert not result.passed
        assert "`## Acceptance criteria (draft)`" in result.reason
        assert "does not accept" in result.reason

    def test_prefixed_heading_is_named_as_the_near_miss(self) -> None:
        result = decide(True, "## 3. Acceptance criteria\n\n- [x] one\n")
        assert "`## 3. Acceptance criteria`" in result.reason

    def test_numbered_list_reason_says_numbered_lists_do_not_count(self) -> None:
        result = decide(True, NUMBERED_ONLY)
        assert "heading is present" in result.reason
        assert "Numbered lists" in result.reason
        assert "does not accept" not in result.reason

    def test_heading_hidden_in_a_comment_is_not_a_near_miss(self) -> None:
        body = "<!--\n## Acceptance criteria (old)\n-->\nprose\n"
        result = decide(True, body)
        assert "does not accept" not in result.reason

    def test_unchecked_reason_says_how_to_clear_it(self) -> None:
        result = decide(True, ONE_UNCHECKED)
        assert "Check each box" in result.reason
        assert "## Deferred" in result.reason

    def test_unchecked_items_are_listed(self) -> None:
        result = decide(True, ONE_UNCHECKED)
        assert not result.passed
        assert result.unchecked == ["two", "three"]
        assert "2 of 3" in result.reason

    def test_all_checked_passes(self) -> None:
        result = decide(True, ALL_CHECKED)
        assert result.passed
        assert result.unchecked == []

    def test_repeat_calls_return_equal_verdicts(self) -> None:
        assert decide(True, ONE_UNCHECKED) == decide(True, ONE_UNCHECKED)


class TestRun:
    def test_no_spec_exits_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", "false")
        assert run() == EXIT_OK

    def test_has_specs_is_case_and_space_tolerant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", " TRUE ")
        monkeypatch.setenv("PR_BODY", ALL_CHECKED)
        assert run() == EXIT_OK

    @pytest.mark.parametrize("raw", ["", "yes", "1", "null"])
    def test_bad_has_specs_is_config_error(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("HAS_SPECS", raw)
        assert run() == EXIT_CONFIG

    def test_unset_has_specs_is_config_error(self) -> None:
        assert run() == EXIT_CONFIG

    def test_missing_section_exits_fail_with_error_annotation(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", "no list")
        assert run() == EXIT_FAIL
        out = capsys.readouterr().out
        assert "::error::" in out
        assert ACCEPTANCE_HEADING in out

    def test_unchecked_exits_fail_and_lists_each(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert run() == EXIT_FAIL
        out = capsys.readouterr().out
        assert "::error::Unchecked acceptance criterion: two" in out
        assert "::error::Unchecked acceptance criterion: three" in out

    def test_all_checked_exits_ok_without_error_annotation(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ALL_CHECKED)
        assert run() == EXIT_OK
        assert "::error::" not in capsys.readouterr().out

    def test_repeat_runs_return_same_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert run() == run() == EXIT_FAIL

    def test_summary_written_on_fail(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert run() == EXIT_FAIL
        text = summary.read_text(encoding="utf-8")
        assert "Validate Spec Coverage: FAIL" in text
        assert "- [ ] two" in text
        assert "- [ ] three" in text

    def test_summary_written_on_pass(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("HAS_SPECS", "false")
        assert run() == EXIT_OK
        assert "Validate Spec Coverage: PASS" in summary.read_text(encoding="utf-8")

    def test_pull_request_event_with_empty_body_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "pull_request")
        assert run() == EXIT_FAIL


class TestAnnotationsAndSummary:
    def test_item_annotations_are_capped_with_a_remainder_line(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = "## Acceptance criteria\n" + "".join(f"- [ ] item {n}\n" for n in range(12))
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", body)
        assert run() == EXIT_FAIL
        out = capsys.readouterr().out
        assert out.count("::error::Unchecked acceptance criterion:") == 8
        assert "item 7" in out
        assert "::error::Unchecked acceptance criterion: item 8" not in out
        assert "::error::4 more unchecked criteria are listed in the step summary." in out
        assert out.count("  unchecked: ") == 12

    def test_exactly_the_cap_has_no_remainder_line(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = "## Acceptance criteria\n" + "".join(f"- [ ] item {n}\n" for n in range(8))
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", body)
        run()
        assert "more unchecked" not in capsys.readouterr().out

    def test_annotation_text_escapes_percent_and_line_breaks(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", "## Acceptance criteria\n- [ ] 100% done\r\n")
        run()
        out = capsys.readouterr().out
        assert "::error::Unchecked acceptance criterion: 100%25 done" in out
        assert "\r" not in out

    def test_escape_covers_all_three_characters(self) -> None:
        assert verdict_module._escape_annotation("a%b\rc\nd") == "a%25b%0Dc%0Ad"

    def test_summary_write_failure_warns_and_keeps_the_exit_code(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "missing" / "s.md"))
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert run() == EXIT_FAIL
        assert "::warning::could not write the step summary" in capsys.readouterr().err

    def test_summary_write_failure_does_not_fail_a_passing_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path))
        monkeypatch.setenv("HAS_SPECS", "false")
        assert run() == EXIT_OK

    def test_config_error_writes_a_one_line_summary(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("HAS_SPECS", "maybe")
        assert run() == EXIT_CONFIG
        text = summary.read_text(encoding="utf-8")
        assert "Validate Spec Coverage: ERROR" in text
        assert "HAS_SPECS" in text


class TestDispatchBody:
    def test_dispatch_without_body_file_is_a_config_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
        assert run() == EXIT_CONFIG
        assert "PR_BODY_FILE missing" in capsys.readouterr().err

    def test_dispatch_error_writes_a_one_line_summary(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
        assert run() == EXIT_CONFIG
        assert "PR_BODY_FILE missing" in summary.read_text(encoding="utf-8")

    def test_dispatch_reads_the_saved_body_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        body_file = tmp_path / "body.md"
        body_file.write_text(ALL_CHECKED + "\n", encoding="utf-8")
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
        monkeypatch.setenv("PR_BODY_FILE", str(body_file))
        assert run() == EXIT_OK

    def test_script_never_touches_the_network(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "urllib" not in text
        assert "subprocess" not in text


class TestCli:
    def test_main_returns_fail_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert main() == EXIT_FAIL

    def test_main_returns_config_code(self) -> None:
        assert main() == EXIT_CONFIG

    @pytest.mark.parametrize(
        ("has_specs", "body", "code"),
        [("false", "", 0), ("true", ONE_UNCHECKED, 1), ("true", ALL_CHECKED, 0), ("x", "", 2)],
    )
    def test_script_runs_under_isolated_python_from_other_cwd(
        self, tmp_path: Path, has_specs: str, body: str, code: int
    ) -> None:
        """Bare-interpreter check: the script imports only the standard library."""
        env = {"HAS_SPECS": has_specs, "PR_BODY": body, "PATH": "/usr/bin:/bin"}
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == code, proc.stderr
        assert "ModuleNotFoundError" not in proc.stderr


@pytest.mark.parametrize(
    ("body", "word"),
    [
        ("## Acceptance criteria\n- [x] a\n<!-- stray\n- [ ] b\n", "comment"),
        ("## Acceptance criteria\n- [x] a\n```\n- [ ] b\n", "fence"),
    ],
)
def test_unclosed_construct_fails_closed_and_names_it(body: str, word: str) -> None:
    result = decide(True, body)
    assert not result.passed
    assert word in result.reason


def test_unclosed_construct_does_not_matter_without_a_spec() -> None:
    assert decide(False, "<!-- stray\n").passed


def test_hidden_unchecked_box_fails_closed_and_lists_it() -> None:
    body = "## Acceptance criteria\n- [x] a\n<!--\n- [ ] later\n-->\n"
    result = decide(True, body)
    assert not result.passed
    assert "hidden" in result.reason
    assert result.unchecked == ["later"]


def test_two_acceptance_headings_fail_closed() -> None:
    body = "    <!-- x\n## Acceptance\n- [ ] x\n    -->\n## Acceptance\n- [x] y\n"
    result = decide(True, body)
    assert not result.passed
    assert "more than one" in result.reason
