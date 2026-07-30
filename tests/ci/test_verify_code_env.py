"""Tests for ``scripts/ci/verify_code_env.py`` (issue #3532)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import verify_code_env as vce

REPO_ROOT = Path(__file__).resolve().parents[2]

ACTION = REPO_ROOT / ".github" / "actions" / "setup-code-env" / "action.yml"


def _completed(returncode: int, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


@pytest.fixture
def no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing is installed unless a test says otherwise."""
    monkeypatch.setattr(vce.shutil, "which", lambda _name: None)
    monkeypatch.setattr(vce, "_run", lambda _argv: _completed(0))


class TestLefthookGate:
    """The only check that can fail the job."""

    def test_a_clean_check_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(0, "ok\n"))
        assert vce.verify_lefthook() == 0

    def test_a_failure_propagates_the_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(7))
        assert vce.verify_lefthook() == 7

    def test_the_failure_is_reported(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(3))
        vce.verify_lefthook()
        assert "[FAIL] Lefthook installation verification failed (exit code 3)" in (
            capsys.readouterr().out
        )

    def test_the_check_output_is_forwarded(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(0, "hook detail\n"))
        vce.verify_lefthook()
        assert "hook detail" in capsys.readouterr().out

    def test_it_invokes_lefthook_through_uv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[list[str]] = []

        def _record(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return _completed(0)

        monkeypatch.setattr(vce, "_run", _record)
        vce.verify_lefthook()
        assert seen == [["uv", "run", "--frozen", "--extra", "dev", "lefthook", "check-install"]]


class TestGateActivation:
    def test_both_flags_are_required(self, monkeypatch: pytest.MonkeyPatch, no_tools: None) -> None:
        calls: list[int] = []

        def _verify() -> int:
            calls.append(1)
            return 0

        monkeypatch.setattr(vce, "verify_lefthook", _verify)
        for hooks, python, expected in [
            ("true", "true", 1),
            ("true", "false", 0),
            ("false", "true", 0),
            ("false", "false", 0),
        ]:
            calls.clear()
            monkeypatch.setenv("ENABLE_GIT_HOOKS", hooks)
            monkeypatch.setenv("ENABLE_PYTHON", python)
            monkeypatch.setenv("ENABLE_PESTER", "false")
            vce.main([])
            assert len(calls) == expected, (hooks, python)

    def test_a_lefthook_failure_stops_before_the_report(
        self, monkeypatch: pytest.MonkeyPatch, no_tools: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("ENABLE_GIT_HOOKS", "true")
        monkeypatch.setenv("ENABLE_PYTHON", "true")
        monkeypatch.setattr(vce, "verify_lefthook", lambda: 9)
        assert vce.main([]) == 9
        assert "SKIP_AUTOFIX" not in capsys.readouterr().out

    def test_a_non_true_value_does_not_enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PYTHON", "True")
        assert vce._enabled("ENABLE_PYTHON") is False
        monkeypatch.setenv("ENABLE_PYTHON", "1")
        assert vce._enabled("ENABLE_PYTHON") is False
        monkeypatch.delenv("ENABLE_PYTHON")
        assert vce._enabled("ENABLE_PYTHON") is False


class TestSkipAutofixLine:
    def test_an_unset_value_defaults_to_zero(
        self, monkeypatch: pytest.MonkeyPatch, no_tools: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("SKIP_AUTOFIX", raising=False)
        for name in ("ENABLE_GIT_HOOKS", "ENABLE_PYTHON", "ENABLE_PESTER"):
            monkeypatch.setenv(name, "false")
        vce.main([])
        assert "SKIP_AUTOFIX: 0 (0=enabled, 1=disabled)" in capsys.readouterr().out

    def test_a_set_value_is_echoed(
        self, monkeypatch: pytest.MonkeyPatch, no_tools: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("SKIP_AUTOFIX", "1")
        for name in ("ENABLE_GIT_HOOKS", "ENABLE_PYTHON", "ENABLE_PESTER"):
            monkeypatch.setenv(name, "false")
        vce.main([])
        assert "SKIP_AUTOFIX: 1 (0=enabled, 1=disabled)" in capsys.readouterr().out


class TestToolReport:
    def test_missing_tools_report_nothing(
        self, no_tools: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        vce.report_tools(python=True, pester=True)
        assert capsys.readouterr().out == ""

    def test_npx_warms_the_markdownlint_cache(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda name: "/x" if name == "npx" else None)
        seen: list[list[str]] = []

        def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return _completed(1)

        monkeypatch.setattr(vce, "_run", _run)
        vce.report_tools(python=False, pester=False)
        out = capsys.readouterr().out
        assert "[PASS] npx is available" in out
        assert "[PASS] markdownlint-cli2 is installed" in out
        assert seen == [["npx", "markdownlint-cli2@0.23.1", "--help"]]

    def test_python_tools_are_skipped_when_python_is_off(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda name: "/x" if name == "ruff" else None)
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(0))
        vce.report_tools(python=False, pester=False)
        assert "ruff" not in capsys.readouterr().out

    def test_python_version_is_reported(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda name: "/x" if name == "python3" else None)
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(0, "Python 3.14.6\n"))
        vce.report_tools(python=True, pester=False)
        assert "[PASS] Python 3.14.6 is installed" in capsys.readouterr().out

    def test_gh_is_reported_independently_of_python(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda name: "/x" if name == "gh" else None)
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(0))
        vce.report_tools(python=False, pester=False)
        assert "[PASS] GitHub CLI is available for workflow monitoring" in capsys.readouterr().out

    def test_pester_is_skipped_when_off(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda _name: None)
        monkeypatch.setattr(vce, "_module_version", lambda name: "5.7.1")
        vce.report_tools(python=False, pester=False)
        out = capsys.readouterr().out
        assert "Pester" not in out
        assert "[PASS] powershell-yaml 5.7.1 is installed" in out

    def test_pester_version_is_reported_when_on(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda _name: None)
        monkeypatch.setattr(
            vce, "_module_version", lambda name: "5.7.1" if name == "Pester" else None
        )
        vce.report_tools(python=False, pester=True)
        assert "[PASS] Pester 5.7.1 is installed" in capsys.readouterr().out


class TestModuleVersion:
    def test_without_pwsh_no_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda _name: None)
        assert vce._module_version("Pester") is None

    def test_a_failing_probe_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda _name: "/x")
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(1, "err"))
        assert vce._module_version("Pester") is None

    def test_empty_output_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda _name: "/x")
        monkeypatch.setattr(vce, "_run", lambda _argv: _completed(0, "\n"))
        assert vce._module_version("Pester") is None

    @pytest.mark.parametrize(
        "hostile", ["Pester; rm -rf /", "Pester\n", "$(whoami)", "", "-Pester", "a`b"]
    )
    def test_a_hostile_module_name_is_rejected(self, hostile: str) -> None:
        with pytest.raises(ValueError):
            vce._module_version(hostile)

    def test_the_probe_uses_an_argument_vector(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(vce.shutil, "which", lambda _name: "/x")
        seen: list[list[str]] = []

        def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            seen.append(argv)
            return _completed(0, "5.7.1")

        monkeypatch.setattr(vce, "_run", _run)
        assert vce._module_version("Pester") == "5.7.1"
        assert seen[0][:3] == ["pwsh", "-NoProfile", "-Command"]
        assert len(seen[0]) == 4


class TestCli:
    def test_a_clean_run_exits_zero_and_prints_the_banner(
        self, monkeypatch: pytest.MonkeyPatch, no_tools: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for name in ("ENABLE_GIT_HOOKS", "ENABLE_PYTHON", "ENABLE_PESTER"):
            monkeypatch.setenv(name, "false")
        assert vce.main([]) == 0
        out = capsys.readouterr().out
        assert "=== Setup Verification ===" in out
        assert "[PASS] Setup complete." in out


class TestWorkflowWiring:
    def test_the_action_invokes_the_script(self) -> None:
        assert "scripts/ci/verify_code_env.py" in ACTION.read_text(encoding="utf-8")

    def test_the_replaced_powershell_is_gone(self) -> None:
        text = ACTION.read_text(encoding="utf-8")
        assert "$LASTEXITCODE" not in text
        assert "Get-Module -ListAvailable" not in text
        assert "markdownlint-cli2@0.23.1 --help" not in text

    def test_the_inputs_are_still_passed_as_env(self) -> None:
        text = ACTION.read_text(encoding="utf-8")
        for name in ("ENABLE_GIT_HOOKS", "ENABLE_PESTER", "ENABLE_PYTHON"):
            assert name in text
