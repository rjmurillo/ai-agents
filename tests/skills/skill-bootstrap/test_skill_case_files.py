"""Every evals/skill-cases/<skill>/cases.json validates as bootstrap_eval cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _ROOT / ".claude" / "skills" / "skill-bootstrap" / "scripts"
sys.path.insert(0, str(_SCRIPTS))
try:
    import bootstrap_eval
finally:
    sys.path.remove(str(_SCRIPTS))

CASE_FILES = sorted((_ROOT / "evals" / "skill-cases").glob("*/cases.json"))
MIN_CASES, MAX_CASES = 2, 3


def test_case_files_exist():
    assert {p.parent.name for p in CASE_FILES} >= {"skillopt", "skillify", "skillforge"}


@pytest.mark.parametrize("path", CASE_FILES, ids=lambda p: p.parent.name)
def test_file_validates_as_draft_cases(path):
    cases = bootstrap_eval.validate_cases(json.loads(path.read_text("utf-8")), allow_draft=True)

    assert MIN_CASES <= len(cases) <= MAX_CASES
    assert {c["skill"] for c in cases} == {path.parent.name}
    assert all(c["id"].startswith(path.parent.name + "-") for c in cases)


@pytest.mark.parametrize("path", CASE_FILES, ids=lambda p: p.parent.name)
def test_skill_directory_exists_for_each_case_file(path):
    assert (_ROOT / "src" / "claude" / "skills" / path.parent.name / "SKILL.md").is_file()


def test_ids_are_unique_across_files():
    ids = [c["id"] for p in CASE_FILES for c in json.loads(p.read_text("utf-8"))["cases"]]
    assert len(ids) == len(set(ids))


def test_a_grader_less_case_is_refused_by_freeze_validation():
    raw = json.loads(CASE_FILES[0].read_text("utf-8"))
    with pytest.raises(bootstrap_eval.ConfigError, match="draft with no grader"):
        bootstrap_eval.validate_cases(raw)
