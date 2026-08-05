"""Tests for the ai-review context builder split."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts/ci/build_ai_review_context.py"
_OUTPUTS_MODULE_PATH = _REPO_ROOT / "scripts/ai_review_outputs.py"


def test_ci_entrypoint_no_longer_needs_file_size_ignore():
    """Issue #4597: the entrypoint must not carry a file-size escape hatch."""

    source = _SCRIPT_PATH.read_text(encoding="utf-8")

    assert "taste-lint: ignore file-size" not in source


def test_ci_entrypoint_stays_below_taste_file_size_cap():
    """Issue #4597: editing this script should not require a split first."""

    source = _SCRIPT_PATH.read_text(encoding="utf-8")

    assert len(source.splitlines()) <= 500


def test_output_helpers_are_extracted_from_ci_entrypoint():
    """Issue #4597: output writing is a cohesive seam outside scripts/ci."""

    entrypoint_source = _SCRIPT_PATH.read_text(encoding="utf-8")
    outputs_source = _OUTPUTS_MODULE_PATH.read_text(encoding="utf-8")

    assert 'import_module("ai_review_outputs")' in entrypoint_source
    assert "def write_outputs(" not in entrypoint_source
    assert "def append_multiline_output(" in outputs_source
