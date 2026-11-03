"""Tests for the --alert path of check_ruleset_params_drift.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "validation"))
import check_ruleset_params_drift as mod

from scripts.ci import ruleset_context_drift as sibling

REPO_ROOT = Path(__file__).resolve().parents[2]
ALERT_TITLE = "Ruleset Parameter Drift Detected"
ALERT_LABELS = "bug,area-workflows,drift-detected,automated"


def _live(*, drift: bool) -> subprocess.CompletedProcess[str]:
    """A gh api result matching the committed baseline, optionally drifted."""
    baseline = mod.load_baseline()
    params = dict(baseline["parameters"])
    if drift:
        params["strict_required_status_checks_policy"] = True
    payload = {
        "rules": [{"type": "pull_request", "parameters": params}],
        "enforcement": baseline["ruleset"]["enforcement"],
    }
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")


def _recorder(calls: list[dict[str, Any]]) -> Callable[..., int]:
    """Stand-in publisher that records its keyword arguments and reports success."""

    def publish(**kwargs: Any) -> int:
        calls.append(kwargs)
        return 0

    return publish


class TestAlert:
    """--alert publishes through the shared helper; exit codes mirror run()."""

    def test_drift_with_alert_publishes_once_and_returns_drift(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(sibling, "publish_issue_alert", _recorder(calls))
        with patch("subprocess.run", return_value=_live(drift=True)):
            rc = mod.main(["--alert"])
        assert rc == mod.EXIT_DRIFT
        assert len(calls) == 1
        call = calls[0]
        assert call["title"] == ALERT_TITLE
        assert call["marker"] == "RULESET-PARAMS-DRIFT"
        assert call["labels"] == ALERT_LABELS
        assert "<!-- RULESET-PARAMS-DRIFT -->" in call["body"]
        assert "strict_required_status_checks_policy" in call["body"]
        assert "ruleset_params_baseline.json" in call["body"]
        assert "11104075" in call["body"]
        out = capsys.readouterr().out
        assert "ALERT: tracking issue created or updated." in out
        assert out.index("NOT OBSERVABLE") < out.index("DRIFT DETECTED")

    @pytest.mark.parametrize("publish_rc", [mod.EXIT_CONFIG, mod.EXIT_EXTERNAL])
    def test_publish_failure_rc_propagates(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        publish_rc: int,
    ) -> None:
        monkeypatch.setattr(sibling, "publish_issue_alert", lambda **kw: publish_rc)
        with patch("subprocess.run", return_value=_live(drift=True)):
            assert mod.main(["--alert"]) == publish_rc
        assert "ALERT:" not in capsys.readouterr().out

    def test_no_drift_does_not_publish(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(sibling, "publish_issue_alert", _recorder(calls))
        with patch("subprocess.run", return_value=_live(drift=False)):
            rc = mod.main(["--alert"])
        assert rc == mod.EXIT_OK
        assert calls == []

    def test_drift_without_alert_does_not_publish(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(sibling, "publish_issue_alert", _recorder(calls))
        with patch("subprocess.run", return_value=_live(drift=True)):
            rc = mod.main([])
        assert rc == mod.EXIT_DRIFT
        assert calls == []

    def test_alert_through_real_helper_requires_runner_temp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("RUNNER_TEMP", raising=False)
        with patch("subprocess.run", return_value=_live(drift=True)):
            assert mod.main(["--alert"]) == mod.EXIT_CONFIG

    def test_step0_answers_pass_the_issue_script_hedge_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.skills.claude_skills_import import import_skill_script

        new_issue: Any = import_skill_script(".claude/skills/github/scripts/issue/new_issue.py")
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(sibling, "publish_issue_alert", _recorder(calls))
        with patch("subprocess.run", return_value=_live(drift=True)):
            mod.main(["--alert"])
        for answer in (calls[0]["blocked_by"], calls[0]["signal"]):
            assert new_issue.provenance.answer_error("answer", answer, "--source=agent") is None

    def test_step0_answers_name_ruleset_and_count_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(sibling, "publish_issue_alert", _recorder(calls))
        with patch("subprocess.run", return_value=_live(drift=True)):
            mod.main(["--alert"])
        assert "11104075" in calls[0]["blocked_by"]
        assert "main" in calls[0]["blocked_by"]
        assert "1 drifted item(s)" in calls[0]["signal"]
        assert "strict_required_status_checks_policy" not in calls[0]["signal"]


class TestRealHelper:
    """Drive main(["--alert"]) through the real publish helper.

    publish_issue_alert resolves _run_issue_skill in ruleset_context_drift's
    globals, so the dispatcher is patched on that module.
    """

    def _dispatch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        issues: list[dict[str, Any]],
        failing: str = "",
    ) -> list[tuple[str, list[str]]]:
        calls: list[tuple[str, list[str]]] = []

        def run_skill(script_name: str, arguments: list[str]) -> tuple[int, dict[str, Any]]:
            calls.append((script_name, list(arguments)))
            if script_name == failing:
                return mod.EXIT_EXTERNAL, {}
            if script_name == "list_issues.py":
                return 0, {"issues": issues}
            if script_name in {"new_issue.py", "post_issue_comment.py"}:
                return 0, {}
            raise AssertionError(f"unexpected issue script: {script_name}")

        monkeypatch.setattr(sibling, "_run_issue_skill", run_skill)
        return calls

    @staticmethod
    def _arg(arguments: list[str], flag: str) -> str:
        return arguments[arguments.index(flag) + 1]

    def test_no_existing_issue_creates_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
        calls = self._dispatch(monkeypatch, issues=[])
        with patch("subprocess.run", return_value=_live(drift=True)):
            rc = mod.main(["--alert"])

        assert rc == mod.EXIT_DRIFT
        assert [name for name, _ in calls] == ["list_issues.py", "new_issue.py"]
        assert ALERT_TITLE in self._arg(calls[0][1], "--search")
        create_args = calls[1][1]
        assert self._arg(create_args, "--title") == ALERT_TITLE
        assert self._arg(create_args, "--labels") == ALERT_LABELS
        body = Path(self._arg(create_args, "--body-file")).read_text(encoding="utf-8")
        assert Path(self._arg(create_args, "--body-file")).parent == tmp_path
        assert "<!-- RULESET-PARAMS-DRIFT -->" in body

    def test_existing_issue_gets_marked_comment(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
        calls = self._dispatch(monkeypatch, issues=[{"number": 42}])
        with patch("subprocess.run", return_value=_live(drift=True)):
            rc = mod.main(["--alert"])

        assert rc == mod.EXIT_DRIFT
        assert [name for name, _ in calls] == ["list_issues.py", "post_issue_comment.py"]
        comment_args = calls[1][1]
        assert self._arg(comment_args, "--issue") == "42"
        assert self._arg(comment_args, "--marker") == "RULESET-PARAMS-DRIFT"

    @pytest.mark.parametrize("failing", ["list_issues.py", "new_issue.py"])
    def test_issue_script_failure_exits_external(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        failing: str,
    ) -> None:
        monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
        calls = self._dispatch(monkeypatch, issues=[], failing=failing)
        with patch("subprocess.run", return_value=_live(drift=True)):
            rc = mod.main(["--alert"])

        assert rc == mod.EXIT_EXTERNAL
        assert calls[-1][0] == failing
        assert "ALERT:" not in capsys.readouterr().out


def test_bare_python_entrypoint_bootstraps_its_own_path() -> None:
    """Run as the workflow does: bare interpreter, no PYTHONPATH, repo-root cwd."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "scripts/validation/check_ruleset_params_drift.py", "--offline"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    assert result.returncode == mod.EXIT_OK
    assert "SKIP" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="the gh stub is a POSIX shell script")
def test_bare_python_alert_path_imports_the_shared_helper(tmp_path: Path) -> None:
    """Run --alert as the workflow does, with a stub gh that reports drift.

    The shared helper is imported lazily, so only this path proves the
    in-function sys.path bootstrap works under a bare interpreter. The stub gh
    answers every call with the drifted ruleset, so the issue scripts fail on
    its output: reaching that ::error:: proves publish_issue_alert ran.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    payload = tmp_path / "ruleset.json"
    payload.write_text(_live(drift=True).stdout, encoding="utf-8")
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\ncat '{payload}'\n", encoding="utf-8")
    gh.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "GH_TOKEN"}}
    env.update(PATH=f"{bin_dir}{os.pathsep}{env['PATH']}", RUNNER_TEMP=str(tmp_path))

    # -S skips site-packages, so an editable install of this repo cannot make
    # scripts.ci importable; CI's bare python3 has no such install either.
    result = subprocess.run(
        [sys.executable, "-S", "scripts/validation/check_ruleset_params_drift.py", "--alert"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        timeout=120,
    )

    assert "ModuleNotFoundError" not in result.stderr
    assert "DRIFT DETECTED" in result.stdout
    assert "::error::" in result.stderr
    assert result.returncode not in {mod.EXIT_OK, mod.EXIT_DRIFT}


def test_alert_files_against_the_checked_repository() -> None:
    assert sibling.REPOSITORY == mod.REPO
