"""Tests for the headers, docstrings, and reference text of the ADR backfill modules."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from adr_helpers import SKILL_SCRIPTS

MODULES = (
    "adr_shape",
    "adr_reason",
    "adr_commits",
    "adr_docs",
    "adr_locate",
    "adr_scan",
    "bootstrap_adr",
)
_SIBLINGS = re.compile(r"^# Sibling ports:(.*?)^# MIT", re.MULTILINE | re.DOTALL)
_REPO = SKILL_SCRIPTS.parents[4]


def _source(name: str) -> str:
    return (SKILL_SCRIPTS / f"{name}.py").read_text(encoding="utf-8")


def _sibling_list(name: str) -> list[str]:
    match = _SIBLINGS.search(_source(name))
    assert match, name
    return re.findall(r"[a-z_]+\.py", match.group(1))


@pytest.mark.parametrize("name", MODULES)
def test_every_header_lists_all_seven_modules_in_the_same_order(name: str) -> None:
    assert _sibling_list(name) == [f"{module}.py" for module in MODULES]


@pytest.mark.parametrize("name", MODULES)
def test_every_module_header_names_the_upstream_commit_and_the_license(name: str) -> None:
    head = _source(name)[:1500]
    assert "aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a" in head
    assert "MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align" in head


@pytest.mark.parametrize("name", MODULES)
def test_every_module_has_one_docstring_and_no_repeated_paragraph(name: str) -> None:
    tree = ast.parse(_source(name))
    strings = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert len(strings) == 1
    paragraphs = [p.strip() for p in (ast.get_docstring(tree) or "").split("\n\n") if p.strip()]
    assert len(paragraphs) == len(set(paragraphs))
    assert "the JavaScript source" not in (ast.get_docstring(tree) or "")


def test_the_regex_notes_live_in_adr_shape_and_the_others_point_to_it() -> None:
    assert "Regex notes. Every module-level pattern" in _source("adr_shape")
    for name in MODULES:
        if name in ("adr_shape", "adr_scan", "adr_locate", "bootstrap_adr"):
            continue
        assert "Regex notes: see the module docstring of ``adr_shape.py``" in _source(name)


def _reference() -> str:
    return (SKILL_SCRIPTS.parent / "references" / "scripts.md").read_text(encoding="utf-8")


def test_the_reference_does_not_call_every_exit_three_git_or_io() -> None:
    text = _reference()
    assert "`git` or `io` for exit 3" not in text
    assert "`git` for exit 3" in text
    assert "report `io` with exit 2" in text


def test_the_reference_documents_the_new_payload_fields_and_the_internal_exit() -> None:
    text = _reference()
    for needle in ("walk_truncated", "shallow", "pr_other_repo", "log_files_skipped", "internal"):
        assert needle in text, needle


def test_the_contract_test_marks_the_adr_helper_entry_as_temporary() -> None:
    source = (Path(__file__).parent / "test_skill_md_contract_tools.py").read_text(encoding="utf-8")
    assert "until the skill step documents its locator (issue #7499)" in source


def test_the_adr_index_generator_cites_the_notices_check_by_name() -> None:
    text = (_REPO / "build" / "scripts" / "generate_adr_index.py").read_text(encoding="utf-8")
    assert "generate_third_party_notices.py:489-495" not in text
    assert "main() of scripts/generate_third_party_notices.py" in text
