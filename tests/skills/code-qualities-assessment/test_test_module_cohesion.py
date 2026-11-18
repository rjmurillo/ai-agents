"""Cohesion is not scored for test modules (issue #7410).

The size+definition proxy counts each test function as a definition, so a
focused suite of related cases scored 1.0 and failed the absolute gate.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "code-qualities-assessment"
    / "scripts"
    / "assess.py"
)
_spec = importlib.util.spec_from_file_location("assess_7410", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_CASES = 30


def _cohesive_suite() -> str:
    """Return a 30-case suite near the issue's 273 LOC, with distinct bodies."""
    lines = ['"""Cases for one parser."""', "", "from parser_under_test import parse", ""]
    for i in range(_CASES):
        lines += [
            f"def test_parse_case_{i}() -> None:",
            f'    text_{i} = "{i}" * {i + 1}',
            f"    value_{i} = parse(text_{i})",
            f"    assert value_{i} == int(text_{i})",
            f"    assert len(str(value_{i})) == {i + 1}",
            f"    assert value_{i} % {i + 2} >= 0",
            f"    assert value_{i} >= {i}",
            f"    assert isinstance(value_{i}, int)",
            f"    assert str(value_{i}).startswith(str({i})[0])",
            "",
        ]
    return "\n".join(lines) + "\n"


def _place(tmp_path: Path, rel: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_cohesive_suite(), encoding="utf-8")
    return path


def _run_default_gate(tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    # main() refuses a --target outside the working directory.
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "absent.qualityrc.json"
    assert not missing.exists()
    rc: int = _mod.main(["--target", str(target), "--config", str(missing), "--format", "json"])
    return rc


@pytest.mark.parametrize("rel", ["tests/test_parser.py", "pkg/test_parser.py"])
def test_cohesive_test_module_passes_default_gate(
    tmp_path: Path, rel: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _place(tmp_path, rel)

    rc = _run_default_gate(tmp_path, target, monkeypatch)

    assert rc == 0


def test_same_content_at_authored_path_still_fails_cohesion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _place(tmp_path, "src/parser_suite.py")

    rc = _run_default_gate(tmp_path, target, monkeypatch)

    assert rc == 11
    assert "Cohesion 1.0 < 7" in capsys.readouterr().err


def test_test_module_cohesion_is_unscored_with_reason(tmp_path: Path) -> None:
    target = _place(tmp_path, "tests/test_parser.py")

    assessment = _mod.assess_content(target, target.read_text(encoding="utf-8"))

    assert assessment.category == "test"
    assert assessment.cohesion.confidence == 0.0
    assert "issue #7410" in assessment.cohesion.reasons[0]
    # The other qualities stay scored, so the file is still gated.
    assert assessment.coupling.confidence > 0.0
    assert assessment.non_redundancy.confidence > 0.0


def test_authored_file_moved_under_tests_loses_no_evidence(tmp_path: Path) -> None:
    base_path = _place(tmp_path, "src/parser_suite.py")
    head_path = _place(tmp_path, "tests/test_parser.py")
    base = _mod.assess_content(base_path, base_path.read_text(encoding="utf-8"))
    head = _mod.assess_content(head_path, head_path.read_text(encoding="utf-8"))
    assert base.cohesion.confidence > 0.0

    comparison = _mod.compare_assessments(base, head, 0.5, base_path.as_posix(), "R100")

    assert comparison.evidence_loss == []
    cohesion = next(d for d in comparison.deltas if d.quality == "cohesion")
    assert cohesion.status == "evidence_lost"


def test_authored_file_losing_cohesion_still_reports_evidence_loss(tmp_path: Path) -> None:
    path = _place(tmp_path, "src/parser_suite.py")
    base = _mod.assess_content(path, path.read_text(encoding="utf-8"))
    head = _mod.assess_content(path, path.read_text(encoding="utf-8"))
    head.cohesion = _mod.QualityScore(value=10.0, confidence=0.0, reasons=["unscored"])

    comparison = _mod.compare_assessments(base, head, 0.5)

    assert comparison.evidence_loss == ["cohesion"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def test_regression_gate_passes_authored_file_renamed_under_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "checkout", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _place(tmp_path, "src/parser_suite.py")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "checkout", "-b", "feature")
    (tmp_path / "tests").mkdir()
    _git(tmp_path, "mv", "src/parser_suite.py", "tests/test_parser.py")
    _git(tmp_path, "commit", "-m", "move under tests")
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "absent.qualityrc.json"
    assert not missing.exists()

    rc = _mod.main(
        [
            "--target",
            ".",
            "--changed-only",
            "--base",
            "main",
            "--config",
            str(missing),
            "--format",
            "json",
        ]
    )

    assert rc == 0, capsys.readouterr().err
