"""Path-fragment tests for check_review_thread_resolution_shas.py (issue #7338)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    # Not registered in sys.modules: sibling tests patch that entry by name.
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_mod = _import_script("check_review_thread_resolution_shas")

_LEARNING = (
    "Learning: files under evals/_archive/ (e.g., "
    "evals/_archive/security-spike-20260503T165136Z-84f918a9/) are frozen."
)


def test_directory_suffix_in_learning_line_is_not_a_sha() -> None:
    assert _mod.extract_shas(_LEARNING) == []


def test_standalone_short_sha_is_checked() -> None:
    assert _mod.extract_shas("Fixed in 84f918a9 on the branch.") == ["84f918a9"]


def test_sha_in_backticks_is_checked() -> None:
    assert _mod.extract_shas("Fixed in `84f918a9`.") == ["84f918a9"]


def test_commit_url_is_checked() -> None:
    body = "See https://github.com/o/r/commit/84f918a9 for the fix."
    assert _mod.extract_shas(body) == ["84f918a9"]


def test_commit_url_with_trailing_path_is_checked() -> None:
    body = "See https://github.com/o/r/commit/84f918a9/files for the fix."
    assert _mod.extract_shas(body) == ["84f918a9"]


def test_pull_commits_url_is_checked() -> None:
    body = "See https://github.com/o/r/pull/7/commits/84f918a9 for the fix."
    assert _mod.extract_shas(body) == ["84f918a9"]


@pytest.mark.parametrize(
    "body",
    [
        "See https://github.com/o/r/blob/84f918a9/src/app.py#L4 for the fix.",
        "See https://github.com/o/r/tree/84f918a9/src for the fix.",
        "See https://github.com/o/r/tree/84f918a9 for the fix.",
        "See https://github.com/o/r/compare/84f918a9...main for the fix.",
        "See https://github.com/o/r/compare/84f918a9..main for the fix.",
    ],
)
def test_ref_url_sha_is_checked(body: str) -> None:
    assert _mod.extract_shas(body) == ["84f918a9"]


def test_compare_url_checks_both_sides() -> None:
    body = "See https://github.com/o/r/compare/84f918a9...abc1234 for the diff."
    assert _mod.extract_shas(body) == ["84f918a9", "abc1234"]


def test_markdown_link_to_commit_is_checked() -> None:
    body = "[fix](https://github.com/o/r/commit/84f918a9)"
    assert _mod.extract_shas(body) == ["84f918a9"]


@pytest.mark.parametrize(
    "body",
    [
        "see build-84f918a9 here",
        "see logs/84f918a9 here",
        "see 84f918a9/readme here",
        "see src/84f918a9/ here",
    ],
)
def test_hex_run_attached_to_path_characters_is_ignored(body: str) -> None:
    assert _mod.extract_shas(body) == []


@pytest.mark.parametrize(
    "body",
    [
        "(84f918a9)",
        "84f918a9.",
        "84f918a9, then",
        "commit:84f918a9",
        "84f918a9..abcdef0",
    ],
)
def test_hex_run_next_to_prose_punctuation_is_checked(body: str) -> None:
    assert "84f918a9" in _mod.extract_shas(body)


def test_hex_run_at_start_of_text_is_checked() -> None:
    assert _mod.extract_shas("84f918a9") == ["84f918a9"]


def test_path_fragment_does_not_hide_adjacent_sha() -> None:
    body = f"{_LEARNING} Real fix is abc1234."
    assert _mod.extract_shas(body) == ["abc1234"]


def test_raw_scan_fallback_ignores_path_fragment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_mod, "_MARKDOWN", None)

    shas, mode = _mod.scan_comment(_LEARNING)

    assert mode == _mod.TEXT_MODE_RAW_PARSER_MISSING
    assert shas == []
