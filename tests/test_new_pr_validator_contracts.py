"""Validator failure and subprocess codec contract tests."""

from __future__ import annotations

import ast
import codecs
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.new_pr_test_support import _completed, run_validations


class TestACrashedValidatorIsNotSuccess:
    """A validator that never ran must not read as a clean scan."""

    @staticmethod
    def _run(
        tmp_path,
        *,
        coverage_rc: int,
        skill_rc: int = 0,
        title: str = "feat: x",
    ):
        for name in ("detect_test_coverage_gaps.py", "detect_skill_violation.py"):
            script = tmp_path / "scripts" / name
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text("# mock", encoding="utf-8")

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout="src/main.py\n", rc=0)
            if len(cmd) > 1 and cmd[1].endswith("detect_test_coverage_gaps.py"):
                return _completed(stderr="ModuleNotFoundError\n", rc=coverage_rc)
            if len(cmd) > 1 and cmd[1].endswith("detect_skill_violation.py"):
                return _completed(rc=skill_rc)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch", title=title)

    def test_a_crashed_coverage_detector_blocks_creation(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, coverage_rc=1)
        assert exc.value.code == 1
        assert "All pre-creation validations passed" not in capsys.readouterr().out

    def test_the_message_names_the_validator_that_did_not_run(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            self._run(tmp_path, coverage_rc=1)
        stderr = capsys.readouterr().err
        assert "detect_test_coverage_gaps.py" in stderr
        assert "did not run" in stderr

    def test_a_crashed_skill_detector_blocks_too(self, tmp_path, capsys):
        """The same swallow existed on validation 2."""
        with pytest.raises(SystemExit):
            self._run(tmp_path, coverage_rc=0, skill_rc=2)
        assert "detect_skill_violation.py" in capsys.readouterr().err

    def test_the_detector_output_still_reaches_the_operator(self, tmp_path, capsys):
        """Capturing the subprocess must not hide what it printed."""
        with pytest.raises(SystemExit):
            self._run(tmp_path, coverage_rc=1)
        assert "ModuleNotFoundError" in capsys.readouterr().err

    def test_clean_detectors_still_report_success(self, tmp_path, capsys):
        """Negative control: the block must be keyed on the failure."""
        self._run(tmp_path, coverage_rc=0)
        assert "All pre-creation validations passed" in capsys.readouterr().out


class TestCapturedOutputPinsItsCodec:
    """Every capturing subprocess.run must pin UTF-8 on both mirrors."""

    _ROOT = Path(__file__).resolve().parents[1]
    _IMPLEMENTATIONS = (
        (
            _ROOT / ".claude/skills/github/scripts/pr/new_pr.py",
            _ROOT / ".claude/skills/github/scripts/pr/new_pr_validations.py",
        ),
        (
            _ROOT / "src/copilot-cli/skills/github/scripts/pr/new_pr.py",
            _ROOT
            / "src/copilot-cli/skills/github/scripts/pr/new_pr_validations.py",
        ),
    )

    @staticmethod
    def _set_true(kwargs: dict[str, ast.expr], name: str) -> bool:
        """True when the keyword is present and spelled as a truthy literal."""
        value = kwargs.get(name)
        return isinstance(value, ast.Constant) and bool(value.value)

    @staticmethod
    def _pins_utf8(encoding: ast.expr | None) -> bool:
        """True when encoding= resolves to the canonical UTF-8 codec."""
        if not isinstance(encoding, ast.Constant) or not isinstance(
            encoding.value,
            str,
        ):
            return False
        try:
            return codecs.lookup(encoding.value).name == "utf-8"
        except LookupError:
            return False

    @staticmethod
    def _capturing_runs(source: str):
        """Return capturing, decoding subprocess calls and their keyword sets."""
        found = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "run"):
                continue
            if not (
                isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            ):
                continue
            kwargs = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
            set_true = TestCapturedOutputPinsItsCodec._set_true
            captures = (
                set_true(kwargs, "capture_output")
                or "stdout" in kwargs
                or "stderr" in kwargs
            )
            decodes = (
                set_true(kwargs, "text")
                or set_true(kwargs, "universal_newlines")
                or "encoding" in kwargs
                or "errors" in kwargs
            )
            if captures and decodes:
                present = set(kwargs)
                if not TestCapturedOutputPinsItsCodec._pins_utf8(
                    kwargs.get("encoding")
                ):
                    present.discard("encoding")
                found.append((node.lineno, present))
        return found

    @staticmethod
    def _implementation_runs(implementation: tuple[Path, ...]):
        return [
            (path, line, kwargs)
            for path in implementation
            for line, kwargs in TestCapturedOutputPinsItsCodec._capturing_runs(
                path.read_text(encoding="utf-8")
            )
        ]

    @pytest.mark.parametrize(
        "implementation",
        _IMPLEMENTATIONS,
        ids=("claude", "copilot-cli"),
    )
    def test_every_capturing_run_pins_utf8(self, implementation):
        offenders = [
            f"{path.name}:{line}"
            for path, line, kwargs in self._implementation_runs(implementation)
            if "encoding" not in kwargs
        ]
        assert not offenders, (
            f"subprocess.run at {offenders} captures and decodes output without "
            "encoding='utf-8'; this crashes the reader thread on Windows cp1252"
        )

    @pytest.mark.parametrize(
        "implementation",
        _IMPLEMENTATIONS,
        ids=("claude", "copilot-cli"),
    )
    def test_every_capturing_run_survives_undecodable_bytes(self, implementation):
        """errors= must be set too: a pinned codec still raises without it."""
        offenders = [
            f"{path.name}:{line}"
            for path, line, kwargs in self._implementation_runs(implementation)
            if "errors" not in kwargs
        ]
        assert not offenders, (
            f"subprocess.run at {offenders} pins a codec but no errors= policy"
        )

    def test_the_check_finds_something_to_check(self):
        """Vacuity control: an AST walk that matches nothing proves nothing."""
        runs = self._implementation_runs(self._IMPLEMENTATIONS[0])
        assert len(runs) >= 5

    def test_a_bare_text_run_is_reported(self):
        """Negative control on the walker itself."""
        offenders = self._capturing_runs(
            "import subprocess\nsubprocess.run(['x'], capture_output=True, text=True)\n"
        )
        assert offenders == [(2, {"capture_output", "text"})]

    def test_errors_alone_run_is_reported(self):
        """errors= alone enables text mode through the locale codec."""
        offenders = self._capturing_runs(
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, errors='ignore')\n"
        )
        assert offenders == [(2, {"capture_output", "errors"})]

    def test_errors_with_encoding_is_not_an_encoding_offender(self):
        """errors= with encoding= pins the codec and stays quiet."""
        runs = self._capturing_runs(
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, "
            "encoding='utf-8', errors='ignore')\n"
        )
        offenders = [line for line, kwargs in runs if "encoding" not in kwargs]
        assert offenders == []

    def test_utf8_codec_aliases_are_not_encoding_offenders(self):
        """Python codec aliases that resolve to UTF-8 still pin the codec."""
        source = "\n".join(
            [
                "import subprocess",
                *(
                    "subprocess.run(['x'], capture_output=True, "
                    f"encoding={alias!r}, errors='replace')"
                    for alias in ("UTF-8", "utf8", "UTF8", "utf_8", "U8")
                ),
            ]
        )
        runs = self._capturing_runs(source)
        offenders = [line for line, kwargs in runs if "encoding" not in kwargs]
        assert len(runs) == 5
        assert offenders == []

    @pytest.mark.parametrize("codec", ("latin-1", "utf-8-sig", "not-a-codec"))
    def test_non_utf8_codecs_are_encoding_offenders(self, codec):
        """Non-UTF-8 codecs still fail the pinned-codec guard."""
        runs = self._capturing_runs(
            "import subprocess\n"
            f"subprocess.run(['x'], capture_output=True, "
            f"encoding={codec!r}, errors='replace')\n"
        )
        offenders = [line for line, kwargs in runs if "encoding" not in kwargs]
        assert offenders == [2]

    def test_a_non_capturing_run_is_out_of_scope(self):
        """text= without capture never decodes, so it is out of scope."""
        assert self._capturing_runs(
            "import subprocess\nsubprocess.run(['x'], text=True, check=False)\n"
        ) == []
