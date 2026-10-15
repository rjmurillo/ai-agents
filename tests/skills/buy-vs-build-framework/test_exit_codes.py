"""ADR-035 exit-code contract for the buy-vs-build scripts and the github skill docs.

ADR-035 reserves exit codes 5-99. Script-specific codes start at 100 and an
idempotent skip exits 0. These tests pin the codes the scripts emit and keep the
reference docs from naming a reserved code.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / "src" / "claude" / "skills" / "buy-vs-build-framework"
SCRIPTS = SKILL_DIR / "scripts"
GITHUB_REFS = REPO_ROOT / "src" / "claude" / "skills" / "github" / "references"

PASS_VENDOR = {
    "years_in_business": 8,
    "funding_status": "series_c_plus",
    "ma_risk": "low",
    "market_position": "challenger",
    "customer_count": 500,
    "public_roadmap": True,
    "pricing_transparency": "public",
    "pricing_model": "per_seat",
    "lock_in_cost": "low",
    "core_feature_coverage_percent": 85,
    "customization_options": "api",
}
YELLOW_VENDOR = {**PASS_VENDOR, "years_in_business": 1, "funding_status": "seed"}
RED_VENDOR: dict[str, Any] = {}

WEIGHTS = {"strategic": 50.0, "risk": 50.0}


def _option(score: int) -> dict[str, Any]:
    return {"strategic": {"a": score}, "risk": {"b": score}}


def _run(script: str, tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _write(tmp_path: Path, name: str, payload: object) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return name


def _literal_exit_codes(script: str) -> set[int]:
    tree = ast.parse((SCRIPTS / script).read_text(encoding="utf-8"))
    codes: set[int] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "exit" or not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
            codes.add(arg.value)
    return codes


class TestScoreVendorExitCodes:
    def test_pass_exits_0(self, tmp_path: Path) -> None:
        name = _write(tmp_path, "v.json", PASS_VENDOR)
        assert _run("score_vendor.py", tmp_path, "--vendor-data", name).returncode == 0

    def test_yellow_flag_exits_100(self, tmp_path: Path) -> None:
        name = _write(tmp_path, "v.json", YELLOW_VENDOR)
        assert _run("score_vendor.py", tmp_path, "--vendor-data", name).returncode == 100

    def test_red_flag_exits_101(self, tmp_path: Path) -> None:
        name = _write(tmp_path, "v.json", RED_VENDOR)
        assert _run("score_vendor.py", tmp_path, "--vendor-data", name).returncode == 101

    def test_missing_file_exits_2_not_a_flag_code(self, tmp_path: Path) -> None:
        result = _run("score_vendor.py", tmp_path, "--vendor-data", "absent.json")
        assert result.returncode == 2
        assert "not found" in result.stderr

    def test_invalid_json_exits_2(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        result = _run("score_vendor.py", tmp_path, "--vendor-data", "bad.json")
        assert result.returncode == 2
        assert "Invalid JSON" in result.stderr

    def test_path_traversal_exits_1(self, tmp_path: Path) -> None:
        result = _run("score_vendor.py", tmp_path, "--vendor-data", "../outside.json")
        assert result.returncode == 1

    def test_boundary_score_70_is_yellow_and_50_is_yellow(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            import score_vendor
        finally:
            sys.path.remove(str(SCRIPTS))
        assert score_vendor.exit_code_for_score(70.01) == 0
        assert score_vendor.exit_code_for_score(70.0) == 100
        assert score_vendor.exit_code_for_score(50.0) == 100
        assert score_vendor.exit_code_for_score(49.99) == 101


class TestScoreDecisionExitCodes:
    def test_clear_winner_exits_0(self, tmp_path: Path) -> None:
        payload = {"weights": WEIGHTS, "options": {"build": _option(9), "buy": _option(3)}}
        name = _write(tmp_path, "c.json", payload)
        assert _run("score_decision.py", tmp_path, "--criteria-file", name).returncode == 0

    def test_tie_exits_1(self, tmp_path: Path) -> None:
        payload = {"weights": WEIGHTS, "options": {"build": _option(9), "buy": _option(9)}}
        name = _write(tmp_path, "c.json", payload)
        assert _run("score_decision.py", tmp_path, "--criteria-file", name).returncode == 1

    def test_missing_file_exits_2(self, tmp_path: Path) -> None:
        result = _run("score_decision.py", tmp_path, "--criteria-file", "absent.json")
        assert result.returncode == 2

    def test_invalid_json_exits_2(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        result = _run("score_decision.py", tmp_path, "--criteria-file", "bad.json")
        assert result.returncode == 2

    def test_failed_validation_exits_2(self, tmp_path: Path) -> None:
        name = _write(tmp_path, "c.json", {"weights": {"strategic": 10.0}, "options": {}})
        result = _run("score_decision.py", tmp_path, "--criteria-file", name)
        assert result.returncode == 2
        assert "Validation failed" in result.stderr


@pytest.mark.parametrize(
    "script",
    [
        "calculate_tco.py",
        "check_reassessment_triggers.py",
        "score_decision.py",
        "score_vendor.py",
    ],
)
def test_no_literal_exit_in_reserved_band(script: str) -> None:
    reserved = {code for code in _literal_exit_codes(script) if 5 <= code <= 99}
    assert reserved == set(), f"{script} exits in the ADR-035 reserved band: {sorted(reserved)}"


_RESERVED_ROW = re.compile(r"^\|\s*(?:[5-9]|[1-9][0-9])\s*\|", re.MULTILINE)
_RESERVED_COMMENT = re.compile(r"^#\s+(?:[5-9]|[1-9][0-9]):", re.MULTILINE)


def test_github_api_reference_has_no_reserved_exit_code_row() -> None:
    text = (GITHUB_REFS / "api-reference.md").read_text(encoding="utf-8")
    assert _RESERVED_ROW.search(text) is None
    assert re.search(r"exit code 5", text, re.IGNORECASE) is None


def test_github_patterns_says_idempotent_skip_exits_zero() -> None:
    text = (GITHUB_REFS / "patterns.md").read_text(encoding="utf-8")
    assert "exits with code 5" not in text
    assert "exits with code 0" in text


@pytest.mark.parametrize(
    "doc",
    [
        SKILL_DIR / "SKILL.md",
        SKILL_DIR / "references" / "PHASE1_ANALYSIS.md",
        REPO_ROOT / "templates" / "skills" / "buy-vs-build-framework.SKILL.md.tmpl",
    ],
)
def test_buy_vs_build_docs_name_only_real_exit_codes(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    assert _RESERVED_COMMENT.search(text) is None
    assert not re.search(r"\b(?:10|11)=", text)
    assert re.search(r"100\s*[:=]\s*[Yy]ellow flag", text)
