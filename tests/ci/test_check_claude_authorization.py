"""Tests for the Claude authorization wrapper (#3536).

The step this replaces separates a script fault from an authorization denial.
Collapsing the two would turn a crashed checker into a silent "not
authorized", so both failure modes are driven here against real stub
checkers rather than asserted against shell text.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from scripts.ci import check_claude_authorization as wrapper

REPO_ROOT = Path(__file__).resolve().parents[2]


def _checker(tmp_path: Path, body: str) -> Path:
    """Write an executable stub checker that ignores its arguments."""
    path = tmp_path / "checker.py"
    path.write_text("import sys\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "gh-output"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def _run(checker: Path, extra: list[str] | None = None) -> int:
    return wrapper.main(["--checker", str(checker), *(extra or [])])


class TestAuthorizationDecision:
    """A clean run forwards the decision unchanged."""

    def test_true_is_forwarded(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: an authorized actor reaches the downstream step."""
        out = _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "print('true')\n")) == 0
        assert "authorized=true" in out.read_text(encoding="utf-8")

    def test_false_is_forwarded(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: a denial is a decision, not a failure."""
        out = _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "print('false')\n")) == 0
        assert "authorized=false" in out.read_text(encoding="utf-8")

    def test_surrounding_whitespace_is_stripped(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: the shell ran ``tr -d '[:space:]'`` for this reason."""
        out = _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "print('  true  ')\n")) == 0
        assert "authorized=true" in out.read_text(encoding="utf-8")

    def test_arguments_reach_the_checker(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the event context is what the checker decides on."""
        out = _outputs(tmp_path, monkeypatch)
        checker = _checker(
            tmp_path,
            "print('true' if '--actor' in sys.argv and 'octocat' in sys.argv else 'false')\n",
        )
        assert _run(checker, ["--actor", "octocat"]) == 0
        assert "authorized=true" in out.read_text(encoding="utf-8")

    def test_an_actor_with_spaces_stays_one_argument(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: argv passing must not word-split a hostile value."""
        out = _outputs(tmp_path, monkeypatch)
        checker = _checker(
            tmp_path, "print('true' if 'a b' in sys.argv else 'false')\n"
        )
        assert _run(checker, ["--actor", "a b"]) == 0
        assert "authorized=true" in out.read_text(encoding="utf-8")


class TestScriptFaultIsNotDenial:
    """A crashed checker must fail the job, never read as 'false'."""

    def test_a_non_zero_exit_fails(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: this is the fail-open the step exists to prevent."""
        _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "sys.exit(3)\n")) == 1

    def test_a_non_zero_exit_reports_the_code(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Edge: the operator needs the code to triage."""
        _outputs(tmp_path, monkeypatch)
        _run(_checker(tmp_path, "sys.exit(3)\n"))
        assert "exit code 3" in capsys.readouterr().out

    def test_a_non_zero_exit_says_it_is_not_a_denial(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Negative: the distinction is the whole point of the branch."""
        _outputs(tmp_path, monkeypatch)
        _run(_checker(tmp_path, "sys.exit(1)\n"))
        assert "not an authorization denial" in capsys.readouterr().out

    def test_a_non_zero_exit_writes_no_output(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: a fault must leave the downstream gate unset."""
        out = _outputs(tmp_path, monkeypatch)
        _run(_checker(tmp_path, "print('true')\nsys.exit(2)\n"))
        assert "authorized=" not in out.read_text(encoding="utf-8")

    def test_a_missing_checker_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Edge: a renamed or unshipped checker must not pass silently."""
        _outputs(tmp_path, monkeypatch)
        assert wrapper.main(["--checker", str(tmp_path / "absent.py")]) == 1
        assert "not found" in capsys.readouterr().out


class TestOutputValidation:
    """A zero exit with a strange answer is a silent failure."""

    def test_an_unexpected_value_fails(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: 'maybe' must not be coerced into a decision."""
        _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "print('maybe')\n")) == 1

    def test_empty_output_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Negative: an early return prints nothing and exits zero."""
        _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "pass\n")) == 1
        assert "without producing valid output" in capsys.readouterr().out

    def test_a_prefix_extension_is_rejected(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: 'trueish' starts with 'true' but is not a decision."""
        _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "print('trueish')\n")) == 1

    def test_internal_whitespace_is_rejected(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: the shell's ``tr -d`` turned 'tr ue' into an accepted 'true'.

        Only the ends are trimmed now, so a garbled answer stays garbled and
        fails rather than being coerced into an authorization decision.
        """
        _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "print('tr ue')\n")) == 1

    def test_the_rejected_value_is_reported(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Edge: the operator needs to see what came back."""
        _outputs(tmp_path, monkeypatch)
        _run(_checker(tmp_path, "print('maybe')\n"))
        assert "'maybe'" in capsys.readouterr().out

    def test_an_invalid_value_writes_no_output(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: the downstream gate must stay unset."""
        out = _outputs(tmp_path, monkeypatch)
        _run(_checker(tmp_path, "print('maybe')\n"))
        assert "authorized=" not in out.read_text(encoding="utf-8")

    def test_multiline_output_is_rejected(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: a checker that logs before answering must not pass."""
        _outputs(tmp_path, monkeypatch)
        assert _run(_checker(tmp_path, "print('debugging')\nprint('true')\n")) == 1


class TestOutputHandling:
    """Step outputs append; they never truncate."""

    def test_existing_output_content_is_preserved(self, tmp_path: Path, monkeypatch) -> None:
        """Edge: a prior step's outputs must survive."""
        out = _outputs(tmp_path, monkeypatch)
        out.write_text("earlier=kept\n", encoding="utf-8")
        _run(_checker(tmp_path, "print('true')\n"))
        assert "earlier=kept" in out.read_text(encoding="utf-8")

    def test_without_the_env_var_the_value_goes_to_stdout(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Edge: running outside Actions must still be inspectable."""
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        assert _run(_checker(tmp_path, "print('true')\n")) == 0
        assert "authorized=true" in capsys.readouterr().out


class TestWorkflowWiring:
    """The workflow must call the script this module tests."""

    def test_the_workflow_calls_the_wrapper(self) -> None:
        """Positive: extraction is only real once the YAML points here."""
        text = (REPO_ROOT / ".github" / "workflows" / "claude.yml").read_text(encoding="utf-8")
        assert "scripts/ci/check_claude_authorization.py" in text

    def test_the_inline_exit_code_handling_is_gone(self) -> None:
        """Negative: the replaced shell must be removed, not bypassed."""
        text = (REPO_ROOT / ".github" / "workflows" / "claude.yml").read_text(encoding="utf-8")
        assert "exit_code=$?" not in text

    def test_the_checker_path_is_supplied_by_the_workflow(self) -> None:
        """Edge: the script must stay free of repository layout knowledge."""
        text = (REPO_ROOT / ".github" / "workflows" / "claude.yml").read_text(encoding="utf-8")
        assert "--checker ./tests/workflows/test_claude_authorization.py" in text
        source = (REPO_ROOT / "scripts" / "ci" / "check_claude_authorization.py").read_text(
            encoding="utf-8"
        )
        assert "tests/workflows" not in source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
