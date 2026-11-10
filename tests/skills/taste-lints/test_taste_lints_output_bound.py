"""Text output of taste_lints.py is bounded; JSON output is not."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/taste-lints/scripts/taste_lints.py")
format_text = mod.format_text
LintResult = mod.LintResult
Violation = mod.Violation


def _violation(index: int, severity: str = "error"):
    return Violation(
        rule="file-size",
        severity=severity,
        file=f"f{index}.py",
        line=index,
        message=f"message {index}",
        remediation="AGENT_REMEDIATION: split",
    )


class TestFormatTextBound:
    def test_default_limit_lists_100_and_names_the_rest(self) -> None:
        result = LintResult(files_scanned=150, violations=[_violation(i) for i in range(150)])

        output = format_text(result)

        assert output.count("[ERROR]") == 100
        assert "... 50 more violation(s) not shown" in output
        assert "150 error(s)" in output

    def test_errors_are_listed_before_warnings_when_the_list_is_cut(self) -> None:
        violations = [_violation(i, "warning") for i in range(5)] + [_violation(9, "error")]
        result = LintResult(files_scanned=6, violations=violations)

        output = format_text(result, max_violations=2)

        assert "f9.py:9" in output
        assert output.count("[WARNING]") == 1
        assert "... 4 more violation(s) not shown" in output

    def test_zero_lists_every_violation(self) -> None:
        result = LintResult(files_scanned=150, violations=[_violation(i) for i in range(150)])

        output = format_text(result, max_violations=0)

        assert output.count("[ERROR]") == 150
        assert "not shown" not in output

    def test_exactly_the_limit_prints_no_notice(self) -> None:
        result = LintResult(files_scanned=3, violations=[_violation(i) for i in range(3)])

        assert "not shown" not in format_text(result, max_violations=3)


class TestMainBound:
    def _lint(self, tmp_path: Path, extra: list[str], capsys) -> tuple[int, str]:
        for index in range(3):
            (tmp_path / f"big{index}.py").write_text("x = 1\n" * 501)
        argv = ["taste_lints.py", *extra, *(str(p) for p in sorted(tmp_path.glob("big*.py")))]
        with patch("sys.argv", argv):
            rc = mod.main()
        return rc, capsys.readouterr().out

    def test_text_limit_applies_and_exit_code_stays_10(self, tmp_path: Path, capsys) -> None:
        rc, out = self._lint(tmp_path, ["--max-violations", "1"], capsys)

        assert rc == mod.EXIT_VIOLATIONS
        assert out.count("[ERROR]") == 1
        assert "2 more violation(s) not shown" in out

    def test_json_is_never_bounded(self, tmp_path: Path, capsys) -> None:
        rc, out = self._lint(tmp_path, ["--format", "json", "--max-violations", "1"], capsys)

        assert rc == mod.EXIT_VIOLATIONS
        assert len(json.loads(out)["violations"]) == 3

    def test_negative_limit_is_a_usage_error(self, tmp_path: Path, capsys) -> None:
        with patch("sys.argv", ["taste_lints.py", "--max-violations", "-1", str(tmp_path)]):
            with pytest.raises(SystemExit) as exc:
                mod.main()

        assert exc.value.code == 2
        assert "--max-violations must be 0 or greater, got -1" in capsys.readouterr().err
