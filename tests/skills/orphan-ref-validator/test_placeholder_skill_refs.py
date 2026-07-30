"""CI-collected tests for orphan-ref-validator placeholder skill refs.

The skill-local suite covers the full scanner. This file keeps issue #3833 in
the default pytest run so generated retrospectives and session logs do not
reintroduce placeholder false positives unnoticed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "orphan-ref-validator" / "scripts"
)
sys.path.insert(0, str(_SCRIPT_DIR))
_spec = importlib.util.spec_from_file_location(
    "_orphan_ref_validator_scan_placeholder_ci", _SCRIPT_DIR / "scan.py"
)
assert _spec is not None and _spec.loader is not None
_scan = importlib.util.module_from_spec(_spec)
sys.modules["_orphan_ref_validator_scan_placeholder_ci"] = _scan
_spec.loader.exec_module(_scan)

scan = _scan.scan


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    skills = repo / ".claude" / "skills"
    skills.mkdir(parents=True)
    (repo / ".git").mkdir()
    return repo


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("token", ["x", "y", "foo", "bar", "baz", "name"])
def test_metasyntactic_placeholder_skill_route_docs_not_flagged(
    fake_repo: Path, token: str
) -> None:
    target = fake_repo / "docs" / "syntax.md"
    write(target, f"The scanner reads Skill: `{token}` as a route name.\n")

    result = scan([target], fake_repo)

    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert result.refs_checked == 0
    assert result.verdict == "PASS"
