"""Doc-accuracy routing stays in its own module so the scanner file stays under 500 lines."""

from __future__ import annotations

import sys
from pathlib import Path

REVIEW_TESTS = str(Path(__file__).resolve().parent)
TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
for entry in (REVIEW_TESTS, TESTS_SKILLS_DIR):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from claude_skills_import import import_skill_script
from test_select_axes_scanner_capability import mod, select


def test_docstring_effect_selects_doc_accuracy_for_a_python_only_diff():
    result = select(["src/main.py"], effects=["comments-or-docstrings"])
    assert "doc-accuracy" in result["local_selected"]


def test_docstring_effect_is_dropped_when_no_path_is_readable():
    result = select(["src/main.rs"], effects=["comments-or-docstrings"])
    assert "doc-accuracy" not in result["local_selected"]
    assert result["skipped"]["doc-accuracy"] == mod._UNREADABLE_REASON


def test_prose_and_code_combination_routes_doc_accuracy():
    result = select(["templates/skills/x.SKILL.md.tmpl", "scripts/x.py"])
    assert "doc-accuracy" in result["local_selected"]
    assert "prose-and-code" in result["selection_reasons"]["doc-accuracy"]


def test_code_alone_does_not_route_doc_accuracy():
    result = select(["scripts/x.py"])
    assert "doc-accuracy" not in result["local_selected"]


def test_prose_alone_without_a_code_path_is_not_a_combination():
    assert mod._routes_doc_accuracy_by_combination(["config/x.yaml"]) == []


def test_same_pr_suffixes_match_the_scanner():
    same_pr = import_skill_script(
        ".claude/skills/doc-accuracy/scripts/same_pr.py",
        module_name="route_same_pr",
    )
    expected = same_pr.PROSE_SUFFIXES | same_pr.DATA_SUFFIXES | {".py"}
    assert mod._DOC_ACCURACY_SAME_PR_SUFFIXES == expected
