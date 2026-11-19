"""Python parser dependency admission for issue #7436 (ADR-122 item 9)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.ai_review_common import adapt_local_axis_verdict

from .test_assess import _FOCUSED, _commit, _run_git
from .test_parser_admission import (
    _PARSER_IMPORTS,
    _PARSER_SCANNER,
    _run_parser_admission,
    parser_admission_repo,
)
from .test_typescript_admission import _TYPESCRIPT_IMPORTS, _TYPESCRIPT_RECORD

__all__ = ["parser_admission_repo"]

_PYTHON_RECORD = {
    "issue": 7436,
    "file": _PARSER_SCANNER,
    "imports": [
        "tree_sitter",
        "tree_sitter_c_sharp",
        "tree_sitter_python",
        "tree_sitter_typescript",
    ],
    "baseScore": 7.0,
    "headScore": 6.0,
    "authorizedBy": "rjmurillo",
    "authorizedOn": "2026-11-18",
    "authorization": (
        "Maintainer instruction: LGTM. Ship. agent- environment is optional. Package add approved"
    ),
}

_PYTHON_IMPORTS = _TYPESCRIPT_IMPORTS + "import tree_sitter_python\n"


@pytest.fixture
def python_admission_repo(parser_admission_repo: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """Base holds the C# and TypeScript parser imports (7.0); head adds Python (6.0)."""
    _run_git(tmp_path, "checkout", "-q", "main")
    _commit(tmp_path, _PARSER_SCANNER, _TYPESCRIPT_IMPORTS + _FOCUSED, "c# and ts parsers")
    _run_git(tmp_path, "checkout", "-q", "feature")
    _run_git(tmp_path, "reset", "-q", "--hard", "main")
    _commit(tmp_path, _PARSER_SCANNER, _PYTHON_IMPORTS + _FOCUSED, "python parser")
    parser_admission_repo["typescriptParserDependencyAdmission"] = dict(_TYPESCRIPT_RECORD)
    parser_admission_repo["pythonParserDependencyAdmission"] = dict(_PYTHON_RECORD)
    return parser_admission_repo


def test_python_admission_matches_the_repository_config() -> None:
    root = Path(__file__).resolve().parents[3]
    config = json.loads((root / ".qualityrc.json").read_text(encoding="utf-8"))

    assert config["pythonParserDependencyAdmission"] == _PYTHON_RECORD


def test_python_admission_keeps_raw_regression_and_authorization(
    python_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = _run_parser_admission(python_admission_repo, tmp_path)

    captured = capsys.readouterr()
    comparison = json.loads(captured.out)["comparisons"][0]
    coupling = next(d for d in comparison["deltas"] if d["quality"] == "coupling")
    assert rc == 0
    assert (coupling["base"], coupling["head"], coupling["delta"]) == (7.0, 6.0, -1.0)
    assert comparison["regressions"] == ["coupling"]
    assert comparison["python_parser_dependency_admission"] == _PYTHON_RECORD
    assert comparison["typescript_parser_dependency_admission"] is None
    assert comparison["csharp_parser_dependency_admission"] is None
    assert "ADMITTED: issue #7436" in captured.err
    assert "NOT ADMITTED" not in captured.err
    assert adapt_local_axis_verdict("code-qualities-assessment", captured.out, rc) == "WARN"


def test_other_records_do_not_admit_the_python_transition(
    python_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del python_admission_repo["pythonParserDependencyAdmission"]

    assert _run_parser_admission(python_admission_repo, tmp_path) == 10
    err = capsys.readouterr().err
    assert "issue #7406: coupling transition" in err
    assert "issue #7435: coupling transition" in err


def test_python_record_alone_does_not_admit_the_csharp_transition(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del parser_admission_repo["csharpParserDependencyAdmission"]
    parser_admission_repo["pythonParserDependencyAdmission"] = dict(_PYTHON_RECORD)

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 10
    assert "issue #7436: coupling transition" in capsys.readouterr().err


def test_python_admission_requires_the_actual_four_imports(
    python_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    other = _TYPESCRIPT_IMPORTS + "import requests\n"
    _commit(tmp_path, _PARSER_SCANNER, other + _FOCUSED, "other dependency")

    assert _run_parser_admission(python_admission_repo, tmp_path) == 10
    assert "issue #7436: external imports" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issue", 7435),
        ("imports", _PARSER_IMPORTS.split()),
        ("baseScore", 8.0),
        ("headScore", 7.0),
        ("authorizedOn", "2026-11-16"),
        ("authorization", "Maintainer instruction: waiver, full send."),
    ],
)
def test_python_admission_rejects_broader_or_unauthorized_config(
    python_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    python_admission_repo["pythonParserDependencyAdmission"][field] = value

    assert _run_parser_admission(python_admission_repo, tmp_path) == 1
    assert "Invalid pythonParserDependencyAdmission" in capsys.readouterr().err
