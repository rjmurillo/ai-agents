"""TypeScript parser dependency admission for issue #7435 (ADR-122 item 8)."""

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

__all__ = ["parser_admission_repo"]

_TYPESCRIPT_RECORD = {
    "issue": 7435,
    "file": _PARSER_SCANNER,
    "imports": ["tree_sitter", "tree_sitter_c_sharp", "tree_sitter_typescript"],
    "baseScore": 8.0,
    "headScore": 7.0,
    "authorizedBy": "rjmurillo",
    "authorizedOn": "2026-11-18",
    "authorization": (
        "Maintainer instruction: LGTM. Ship. agent- environment is optional. Package add approved"
    ),
}

_TYPESCRIPT_IMPORTS = _PARSER_IMPORTS + "import tree_sitter_typescript\n"


@pytest.fixture
def typescript_admission_repo(
    parser_admission_repo: dict[str, Any], tmp_path: Path
) -> dict[str, Any]:
    """Base already holds the C# parser imports (8.0); head adds the TypeScript one (7.0)."""
    _run_git(tmp_path, "checkout", "-q", "main")
    _commit(tmp_path, _PARSER_SCANNER, _PARSER_IMPORTS + _FOCUSED, "c# parser on main")
    _run_git(tmp_path, "checkout", "-q", "feature")
    _run_git(tmp_path, "reset", "-q", "--hard", "main")
    _commit(tmp_path, _PARSER_SCANNER, _TYPESCRIPT_IMPORTS + _FOCUSED, "typescript parser")
    parser_admission_repo["typescriptParserDependencyAdmission"] = dict(_TYPESCRIPT_RECORD)
    return parser_admission_repo


def test_typescript_admission_matches_the_repository_config() -> None:
    root = Path(__file__).resolve().parents[3]
    config = json.loads((root / ".qualityrc.json").read_text(encoding="utf-8"))

    assert config["typescriptParserDependencyAdmission"] == _TYPESCRIPT_RECORD


def test_typescript_admission_keeps_raw_regression_and_authorization(
    typescript_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = _run_parser_admission(typescript_admission_repo, tmp_path)

    captured = capsys.readouterr()
    comparison = json.loads(captured.out)["comparisons"][0]
    coupling = next(d for d in comparison["deltas"] if d["quality"] == "coupling")
    assert rc == 0
    assert (coupling["base"], coupling["head"], coupling["delta"]) == (8.0, 7.0, -1.0)
    assert comparison["regressions"] == ["coupling"]
    assert comparison["typescript_parser_dependency_admission"] == _TYPESCRIPT_RECORD
    assert comparison["csharp_parser_dependency_admission"] is None
    assert "coupling regressed 8.0 -> 7.0 (delta -1.0)" in captured.err
    assert "ADMITTED: issue #7435" in captured.err
    assert "NOT ADMITTED" not in captured.err
    assert adapt_local_axis_verdict("code-qualities-assessment", captured.out, rc) == "WARN"


def test_csharp_record_alone_does_not_admit_the_typescript_transition(
    typescript_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del typescript_admission_repo["typescriptParserDependencyAdmission"]

    assert _run_parser_admission(typescript_admission_repo, tmp_path) == 10
    err = capsys.readouterr().err
    assert "NOT ADMITTED" in err
    assert "issue #7406: coupling transition" in err


def test_typescript_record_alone_does_not_admit_the_csharp_transition(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del parser_admission_repo["csharpParserDependencyAdmission"]
    parser_admission_repo["typescriptParserDependencyAdmission"] = dict(_TYPESCRIPT_RECORD)

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 10
    assert "issue #7435: coupling transition" in capsys.readouterr().err


def test_no_record_admits_both_parsers_at_once(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """10.0 -> 7.0 matches neither record, so both mismatch reasons print."""
    _commit(tmp_path, _PARSER_SCANNER, _TYPESCRIPT_IMPORTS + _FOCUSED, "both parsers")
    parser_admission_repo["typescriptParserDependencyAdmission"] = dict(_TYPESCRIPT_RECORD)

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 10
    err = capsys.readouterr().err
    assert "issue #7406: coupling transition" in err
    assert "issue #7435: coupling transition" in err
    assert "ADMITTED: issue" not in err


def test_typescript_admission_requires_the_actual_three_imports(
    typescript_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _commit(tmp_path, _PARSER_SCANNER, _PARSER_IMPORTS + "import requests\n" + _FOCUSED, "other")

    assert _run_parser_admission(typescript_admission_repo, tmp_path) == 10
    assert "issue #7435: external imports" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issue", 7434),
        ("imports", ["tree_sitter", "tree_sitter_typescript"]),
        ("baseScore", 10.0),
        ("headScore", 6.0),
        ("authorizedOn", "2026-11-16"),
        ("authorization", "Maintainer instruction: waiver, full send."),
    ],
)
def test_typescript_admission_rejects_broader_or_unauthorized_config(
    typescript_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    typescript_admission_repo["typescriptParserDependencyAdmission"][field] = value

    assert _run_parser_admission(typescript_admission_repo, tmp_path) == 1
    assert "Invalid typescriptParserDependencyAdmission" in capsys.readouterr().err
