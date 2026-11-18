"""Parser dependency admission boundaries and local-review integration."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.ai_review_common import adapt_local_axis_verdict

from .test_assess import (
    _FOCUSED,
    _SPRAWLING,
    _commit,
    _mod,
    _regression_argv,
    _repo_with_change,
    _run_git,
    _write,
    main,
)

_PARSER_SCANNER = "src/claude/skills/code-qualities-assessment/scripts/assess.py"

_PARSER_IMPORTS = "import tree_sitter\nimport tree_sitter_c_sharp\n"

_PYTHON_PARSER_IMPORTS = _PARSER_IMPORTS + "import tree_sitter_python\n"

_CSHARP_ADMISSION = {
    "issue": 7406,
    "file": _PARSER_SCANNER,
    "imports": ["tree_sitter", "tree_sitter_c_sharp"],
    "baseScore": 10.0,
    "headScore": 8.0,
    "authorizedBy": "rjmurillo",
    "authorizedOn": "2026-11-16",
    "authorization": "Maintainer instruction: waiver, full send.",
}

_PYTHON_ADMISSION = {
    "issue": 7436,
    "file": _PARSER_SCANNER,
    "imports": ["tree_sitter", "tree_sitter_c_sharp", "tree_sitter_python"],
    "baseScore": 8.0,
    "headScore": 7.0,
    "authorizedBy": "rjmurillo",
    "authorizedOn": "2026-11-18",
    "authorization": "Maintainer instruction: LGTM. Ship. Package add approved.",
}


@pytest.fixture
def parser_admission_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    (tmp_path / _PARSER_SCANNER).parent.mkdir(parents=True)
    _repo_with_change(tmp_path, monkeypatch, _FOCUSED, _PARSER_IMPORTS + _FOCUSED, _PARSER_SCANNER)
    return {
        "thresholds": {},
        "parserDependencyAdmissions": [dict(_CSHARP_ADMISSION), dict(_PYTHON_ADMISSION)],
    }


def _run_parser_admission(config: dict[str, Any], tmp_path: Path) -> int:
    config_path = _write(tmp_path, ".qualityrc.json", json.dumps(config))
    result = main([*_regression_argv(), "--config", str(config_path)])
    assert isinstance(result, int)
    return result


def test_parser_admission_keeps_raw_regression_and_authorization(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = _run_parser_admission(parser_admission_repo, tmp_path)

    captured = capsys.readouterr()
    comparison = json.loads(captured.out)["comparisons"][0]
    coupling = next(d for d in comparison["deltas"] if d["quality"] == "coupling")
    assert rc == 0
    assert (coupling["base"], coupling["head"], coupling["delta"]) == (10.0, 8.0, -2.0)
    assert comparison["regressions"] == ["coupling"]
    assert comparison["parser_dependency_admission"] == _CSHARP_ADMISSION
    assert "coupling regressed 10.0 -> 8.0 (delta -2.0)" in captured.err
    assert "ADMITTED" in captured.err
    assert adapt_local_axis_verdict("code-qualities-assessment", captured.out, rc) == "WARN"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issue", 7407),
        ("file", "other.py"),
        ("imports", ["tree_sitter"]),
        ("baseScore", 9.0),
        ("headScore", 7.0),
        ("authorizedBy", ""),
        ("authorizedOn", ""),
        ("authorization", ""),
    ],
)
def test_parser_admission_rejects_broader_or_unauthorized_config(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    parser_admission_repo["parserDependencyAdmissions"][0][field] = value

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 1
    assert "ERROR:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "records",
    [
        None,
        [],
        "approved",
        _CSHARP_ADMISSION,
        [_CSHARP_ADMISSION, _CSHARP_ADMISSION],
        [_CSHARP_ADMISSION, "approved"],
    ],
)
def test_parser_admission_rejects_malformed_config(
    parser_admission_repo: dict[str, Any], tmp_path: Path, records: object
) -> None:
    parser_admission_repo["parserDependencyAdmissions"] = records

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 1


def test_parser_admission_rejects_the_retired_single_record_key(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser_admission_repo["csharpParserDependencyAdmission"] = dict(_CSHARP_ADMISSION)

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 1
    assert "parserDependencyAdmissions" in capsys.readouterr().err


def test_parser_admission_admits_the_python_grammar_transition(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _run_git(tmp_path, "branch", "-f", "main")
    _commit(tmp_path, _PARSER_SCANNER, _PYTHON_PARSER_IMPORTS + _FOCUSED, "python grammar")

    rc = _run_parser_admission(parser_admission_repo, tmp_path)

    captured = capsys.readouterr()
    comparison = json.loads(captured.out)["comparisons"][0]
    coupling = next(d for d in comparison["deltas"] if d["quality"] == "coupling")
    assert rc == 0
    assert (coupling["base"], coupling["head"], coupling["delta"]) == (8.0, 7.0, -1.0)
    assert comparison["parser_dependency_admission"] == _PYTHON_ADMISSION
    assert "ADMITTED: issue #7436" in captured.err
    assert adapt_local_axis_verdict("code-qualities-assessment", captured.out, rc) == "WARN"


def test_parser_admission_needs_the_matching_record_configured(
    parser_admission_repo: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_git(tmp_path, "branch", "-f", "main")
    _commit(tmp_path, _PARSER_SCANNER, _PYTHON_PARSER_IMPORTS + _FOCUSED, "python grammar")
    parser_admission_repo["parserDependencyAdmissions"] = [dict(_CSHARP_ADMISSION)]

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 10
    assert "NOT ADMITTED" in capsys.readouterr().err


@pytest.mark.parametrize("extra", ["", "import requests\n", _SPRAWLING])
def test_parser_admission_does_not_clear_unapproved_regressions(
    parser_admission_repo: dict[str, Any], tmp_path: Path, extra: str
) -> None:
    if extra:
        _commit(tmp_path, _PARSER_SCANNER, _PARSER_IMPORTS + extra + _FOCUSED, "regress")
    else:
        del parser_admission_repo["parserDependencyAdmissions"]

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 10


@pytest.mark.parametrize(
    ("head_imports", "reason"),
    [
        (_PARSER_IMPORTS + "import requests\n", "coupling transition"),
        ("import requests\nimport flask\n", "external imports"),
        ("from . import x\nimport tree_sitter\n", "external imports"),
    ],
)
def test_parser_admission_reports_why_a_mismatch_is_not_admitted(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    head_imports: str,
    reason: str,
) -> None:
    _commit(tmp_path, _PARSER_SCANNER, head_imports + _FOCUSED, "mismatch")

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 10
    err = capsys.readouterr().err
    assert f"NOT ADMITTED: {_PARSER_SCANNER}: " in err
    assert reason in err
    assert "ADMITTED: issue" not in err


def _comparison(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "file_path": _PARSER_SCANNER,
        "is_new_file": False,
        "deltas": [_mod.QualityDelta("coupling", 10.0, 8.0, -2.0, "compared")],
        "regressions": ["coupling"],
        "evidence_loss": [],
    }
    fields.update(overrides)
    return _mod.FileComparison(**fields)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"change_status": "R"}, "change status is R"),
        ({"absolute_gate_reason": "below floor"}, "absolute gate applies: below floor"),
        ({"deltas": []}, "no coupling delta recorded"),
    ],
)
def test_admission_mismatch_reason_names_each_non_matching_shape(
    parser_admission_repo: dict[str, Any], overrides: dict[str, Any], reason: str
) -> None:
    admission = parser_admission_repo["parserDependencyAdmissions"][0]

    assert reason in _mod._admission_mismatch_reason(_comparison(**overrides), admission)


def test_parser_admission_requires_the_actual_two_imports(
    parser_admission_repo: dict[str, Any], tmp_path: Path
) -> None:
    _commit(tmp_path, _PARSER_SCANNER, "import requests\nimport flask\n" + _FOCUSED, "other")

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 10


@pytest.mark.parametrize("failure", ["unreadable", "undecodable", "syntax"])
def test_parser_admission_rejects_unverifiable_source_without_a_report(
    parser_admission_repo: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    verify_imports: Callable[[Path], set[str]] = _mod._python_external_imports

    def verify_broken_source(path: Path) -> set[str]:
        if failure == "unreadable":
            with patch.object(Path, "read_text", side_effect=PermissionError("read denied")):
                return verify_imports(path)
        path.write_bytes(b"\xff" if failure == "undecodable" else b"import (\n")
        return verify_imports(path)

    monkeypatch.setattr(_mod, "_python_external_imports", verify_broken_source)

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 1
    captured = capsys.readouterr()
    assert "Cannot verify parser dependency admission" in captured.err
    assert _PARSER_SCANNER in captured.err
    assert not captured.out


def test_parser_admission_does_not_clear_new_file_threshold_failure(
    parser_admission_repo: dict[str, Any], tmp_path: Path
) -> None:
    _commit(tmp_path, "new.py", _SPRAWLING, "new module")
    parser_admission_repo["minConfidence"] = 0.0
    parser_admission_repo["thresholds"] = {
        "cohesion": {"min": 10},
        "coupling": {},
        "encapsulation": {},
        "testability": {},
        "nonRedundancy": {},
    }

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 11


def test_parser_admission_does_not_clear_lost_evidence(
    parser_admission_repo: dict[str, Any], tmp_path: Path
) -> None:
    (tmp_path / _PARSER_SCANNER).write_bytes(b"\xff")
    _run_git(tmp_path, "add", _PARSER_SCANNER)
    _run_git(tmp_path, "commit", "-m", "unreadable source")

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 10
