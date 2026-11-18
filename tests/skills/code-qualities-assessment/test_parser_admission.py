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


@pytest.fixture
def parser_admission_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    (tmp_path / _PARSER_SCANNER).parent.mkdir(parents=True)
    _repo_with_change(tmp_path, monkeypatch, _FOCUSED, _PARSER_IMPORTS + _FOCUSED, _PARSER_SCANNER)
    return {
        "thresholds": {},
        "csharpParserDependencyAdmission": {
            "issue": 7406,
            "file": _PARSER_SCANNER,
            "imports": ["tree_sitter", "tree_sitter_c_sharp"],
            "baseScore": 10.0,
            "headScore": 8.0,
            "authorizedBy": "rjmurillo",
            "authorizedOn": "2026-11-16",
            "authorization": "Maintainer instruction: waiver, full send.",
        },
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
    assert (
        comparison["csharp_parser_dependency_admission"]
        == (parser_admission_repo["csharpParserDependencyAdmission"])
    )
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
    parser_admission_repo["csharpParserDependencyAdmission"][field] = value

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 1
    assert "ERROR:" in capsys.readouterr().err


@pytest.mark.parametrize("record", [None, [], "approved"])
def test_parser_admission_rejects_malformed_config(
    parser_admission_repo: dict[str, Any], tmp_path: Path, record: object
) -> None:
    parser_admission_repo["csharpParserDependencyAdmission"] = record

    assert _run_parser_admission(parser_admission_repo, tmp_path) == 1


@pytest.mark.parametrize("extra", ["", "import requests\n", _SPRAWLING])
def test_parser_admission_does_not_clear_unapproved_regressions(
    parser_admission_repo: dict[str, Any], tmp_path: Path, extra: str
) -> None:
    if extra:
        _commit(tmp_path, _PARSER_SCANNER, _PARSER_IMPORTS + extra + _FOCUSED, "regress")
    else:
        del parser_admission_repo["csharpParserDependencyAdmission"]

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
    admission = parser_admission_repo["csharpParserDependencyAdmission"]

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
