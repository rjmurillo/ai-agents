"""Tests for bootstrap_adr draft: which heading of the newest ADR receives each part (P16)."""

from __future__ import annotations

from pathlib import Path

import bootstrap_adr
from adr_helpers import commit, new_repo, write
from draft_helpers import _cand, _scan_file, _text


def test_only_the_first_heading_of_a_kind_is_filled(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-a.md", "# 1. A\n\n## Context\n\nc\n\n## Background\n\nb\n")
    commit(repo, "Initial work")
    scan = _scan_file(tmp_path, repo, _cand())
    text = _text(bootstrap_adr.draft(scan, "c-1234567", str(repo / "docs" / "adr"), "Proposed"))
    assert text.count("The reason given at the time:") == 1
    assert "## Background\n\nNot recorded in the source." in text


def test_section_matching_uses_whole_words(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(
        repo,
        "docs/adr/0001-a.md",
        "# 1. A\n\n## Context and Constraints\n\nc\n\n## Updates\n\nu\n\n## Candidates\n\nk\n"
        "\n## Decision\n\nd\n",
    )
    commit(repo, "Initial work")
    scan = _scan_file(tmp_path, repo, _cand())
    text = _text(bootstrap_adr.draft(scan, "c-1234567", str(repo / "docs" / "adr"), "Proposed"))
    assert "## Context and Constraints\n\nThe reason given at the time:" in text
    assert "## Updates\n\nNot recorded in the source." in text
    assert "## Candidates\n\nNot recorded in the source." in text
    assert "## Decision\n\nReplace eo-inference" in text
    assert "Date: 2026-11-02" in text and "2026-11-02" not in text.split("## Updates")[1]
