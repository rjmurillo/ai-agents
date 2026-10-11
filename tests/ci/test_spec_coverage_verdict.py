"""Tests for scripts/ci/spec_coverage_verdict.py (issue #6182)."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch

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

    def test_pull_request_event_never_fetches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "pull_request")
        with patch(_URLOPEN) as mock_open:
            assert run() == EXIT_FAIL
        mock_open.assert_not_called()


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

    def test_fetch_failure_writes_a_one_line_summary(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
        with patch(_URLOPEN, side_effect=OSError("x")):
            assert run() == EXIT_CONFIG
        assert "Could not read the pull request body" in summary.read_text(encoding="utf-8")


class _FakeResponse:
    """Minimal context-manager response for urlopen."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self, *_args: object) -> bytes:
        return self._payload


def _json_response(body: object) -> _FakeResponse:
    return _FakeResponse(json.dumps({"body": body}).encode("utf-8"))


_URLOPEN = "scripts.ci.spec_coverage_verdict._OPENER.open"


class TestDispatchFetch:
    def _env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
        monkeypatch.setenv("PR_NUMBER", "42")
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r.x-y_z")
        monkeypatch.setenv("GH_TOKEN", "tok")

    def test_fetches_body_with_bearer_token_when_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._env(monkeypatch)
        with patch(_URLOPEN, return_value=_json_response(ALL_CHECKED)) as mock_open:
            assert run() == EXIT_OK
        request = mock_open.call_args.args[0]
        assert request.full_url == "https://api.github.com/repos/o/r.x-y_z/pulls/42"
        assert request.get_header("Authorization") == "Bearer tok"
        assert request.get_header("Accept") == "application/vnd.github+json"
        assert request.get_method() == "GET"
        assert mock_open.call_args.kwargs["timeout"] == 60

    def test_falls_back_to_github_token_and_custom_api_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._env(monkeypatch)
        monkeypatch.delenv("GH_TOKEN")
        monkeypatch.setenv("GITHUB_TOKEN", "alt")
        monkeypatch.setenv("GITHUB_API_URL", "https://ghe.example/api/v3/")
        with patch(_URLOPEN, return_value=_json_response(ALL_CHECKED)) as mock_open:
            assert run() == EXIT_OK
        request = mock_open.call_args.args[0]
        assert request.full_url == "https://ghe.example/api/v3/repos/o/r.x-y_z/pulls/42"
        assert request.get_header("Authorization") == "Bearer alt"

    def test_no_token_omits_the_authorization_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._env(monkeypatch)
        monkeypatch.delenv("GH_TOKEN")
        with patch(_URLOPEN, return_value=_json_response(ALL_CHECKED)) as mock_open:
            assert run() == EXIT_OK
        assert mock_open.call_args.args[0].get_header("Authorization") is None

    def test_null_body_is_treated_as_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._env(monkeypatch)
        with patch(_URLOPEN, return_value=_json_response(None)):
            assert run() == EXIT_FAIL

    def test_skips_fetch_when_body_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._env(monkeypatch)
        monkeypatch.setenv("PR_BODY", ALL_CHECKED)
        with patch(_URLOPEN) as mock_open:
            assert run() == EXIT_OK
        mock_open.assert_not_called()

    @pytest.mark.parametrize(
        "failure",
        [
            urllib.error.HTTPError("u", 404, "nf", Message(), None),
            urllib.error.URLError("down"),
            TimeoutError("slow"),
            OSError("reset"),
        ],
    )
    def test_transport_failures_are_config_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        failure: Exception,
    ) -> None:
        self._env(monkeypatch)
        with patch(_URLOPEN, side_effect=failure):
            assert run() == EXIT_CONFIG
        assert "::error::" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "payload",
        [b"not json", b"\xff\xfe", b"[1]", b'{"body": 5}', b'{"other": 1}'],
    )
    def test_bad_payloads_are_config_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        payload: bytes,
    ) -> None:
        self._env(monkeypatch)
        with patch(_URLOPEN, return_value=_FakeResponse(payload)):
            assert run() == EXIT_CONFIG
        assert "::error::" in capsys.readouterr().err

    @pytest.mark.parametrize("missing", ["PR_NUMBER", "GITHUB_REPOSITORY"])
    def test_missing_fetch_inputs_is_config_error(
        self, monkeypatch: pytest.MonkeyPatch, missing: str
    ) -> None:
        self._env(monkeypatch)
        monkeypatch.delenv(missing)
        with patch(_URLOPEN) as mock_open:
            assert run() == EXIT_CONFIG
        mock_open.assert_not_called()

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("PR_NUMBER", "0"),
            ("PR_NUMBER", "012"),
            ("PR_NUMBER", "4 2"),
            ("PR_NUMBER", "42/../x"),
            ("PR_NUMBER", "-1"),
            ("GITHUB_REPOSITORY", "justone"),
            ("GITHUB_REPOSITORY", "a/b/c"),
            ("GITHUB_REPOSITORY", "a/b c"),
            ("GITHUB_REPOSITORY", "a/b?x=1"),
            ("GITHUB_REPOSITORY", "../b"),
            ("GITHUB_REPOSITORY", "a/.."),
            ("GITHUB_API_URL", "http://api.github.com"),
            ("GITHUB_API_URL", "file:///etc/passwd"),
            ("GITHUB_API_URL", "ftp://x"),
        ],
    )
    def test_invalid_inputs_never_reach_the_network(
        self, monkeypatch: pytest.MonkeyPatch, name: str, value: str
    ) -> None:
        self._env(monkeypatch)
        monkeypatch.setenv(name, value)
        with patch(_URLOPEN) as mock_open:
            assert run() == EXIT_CONFIG
        mock_open.assert_not_called()

    def test_redirects_are_refused_so_the_token_stays_put(self) -> None:
        handler = verdict_module._RefuseRedirect()
        request = urllib.request.Request("https://api.github.com/repos/o/r/pulls/1")
        assert handler.redirect_request(request, None, 302, "Found", Message(), "https://x") is None
        assert any(
            isinstance(h, verdict_module._RefuseRedirect)
            for h in vars(verdict_module._OPENER)["handlers"]
        )

    def test_a_refused_redirect_is_a_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._env(monkeypatch)
        error = urllib.error.HTTPError("https://x", 302, "Found", Message(), None)
        with patch(_URLOPEN, side_effect=error):
            assert run() == EXIT_CONFIG

    def test_script_does_not_import_subprocess(self) -> None:
        assert "subprocess" not in SCRIPT.read_text(encoding="utf-8")


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
