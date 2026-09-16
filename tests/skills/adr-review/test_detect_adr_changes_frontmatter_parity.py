#!/usr/bin/env python3
"""Parity between the plugin-side fence mirror and the library it copies.

Split from `test_detect_adr_changes.py` to keep each file under the 500-line
taste-lint limit, matching how this directory already splits by concern
(`_duplicate_keys`, `_encoding`, `_status_scalar`).

`detect_adr_changes.py` ships inside a plugin root, so it may import only the
standard library and yaml (`.claude/rules/plugin-self-containment.md`). It can
import neither `python-frontmatter` nor the repo-side
`scripts/validation/frontmatter_contract.py`, so it keeps a verbatim copy of the
library's boundary. These tests are what hold that copy honest; they run in the
repo, where the import is available.

Issue #4918 is what a missing pin costs: a gate keying on the literal `"---"`
silently passed memory files the real parser rejected, because the actual
boundary accepts three OR MORE dashes. A gate with false negatives is decorative.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/adr-review/scripts/detect_adr_changes.py")

_split_frontmatter = mod._split_frontmatter


class TestFrontmatterBoundaryParity:
    """The mirrored fence pattern must not drift from the library it copies.

    `detect_adr_changes.py` ships inside a plugin root, so it may import only the
    standard library and yaml (`.claude/rules/plugin-self-containment.md`). It
    cannot import `python-frontmatter`, and it cannot import the repo-side
    `scripts/validation/frontmatter_contract.py` either. It therefore keeps a
    verbatim copy of the library's boundary, and this test is what holds the copy
    honest. It runs in the repo, where the import is available.

    Issue #4918 is what a missing pin costs: a gate keying on the literal `"---"`
    silently passed memory files the real parser rejected, because the actual
    boundary accepts three OR MORE dashes. A gate with false negatives is
    decorative.
    """

    def test_mirrored_pattern_equals_the_library(self) -> None:
        from frontmatter.default_handlers import YAMLHandler

        assert mod.FRONTMATTER_BOUNDARY.pattern == YAMLHandler.FM_BOUNDARY.pattern

    @pytest.mark.parametrize(
        ("label", "fence", "is_close"),
        [
            ("exactly three dashes", "---", True),
            ("four dashes", "----", True),
            ("many dashes", "----------", True),
            ("padded with a space", "--- ", True),
            ("padded with a tab", "---\t", True),
            ("two dashes", "--", False),
            ("trailing text", "--- nope", False),
            ("leading space", " ---", False),
            ("dashes then a word", "---x", False),
        ],
    )
    def test_boundary_agrees_with_the_library_per_shape(
        self, label: str, fence: str, is_close: bool
    ) -> None:
        """Shape-by-shape parity, so a drift names the shape it broke."""
        from frontmatter.default_handlers import YAMLHandler

        mirrored = mod.FRONTMATTER_BOUNDARY.match(fence) is not None
        canonical = YAMLHandler.FM_BOUNDARY.match(fence) is not None
        assert mirrored == canonical, label
        assert mirrored is is_close, label

    def test_four_dash_close_is_now_accepted(self) -> None:
        """The regression issue #5275 reported from this side.

        `line.strip() == "---"` rejected a four-dash close that the lifecycle
        gate and the index generator both accepted.
        """
        raw, body = _split_frontmatter("---\nid: ADR-1\nstatus: accepted\n----\nBody.\n")
        assert raw == "id: ADR-1\nstatus: accepted\n"
        assert body == "Body.\n"

    def test_padded_close_is_accepted(self) -> None:
        """The exact input from issue #5275: one trailing space."""
        raw, body = _split_frontmatter("---\nid: ADR-1\n--- \nBody.\n")
        assert raw == "id: ADR-1\n"
        assert body == "Body.\n"

    def test_trailing_text_is_not_a_close(self) -> None:
        raw, body = _split_frontmatter("---\nid: ADR-1\n--- nope\nBody.\n")
        assert raw == ""
        assert body == "---\nid: ADR-1\n--- nope\nBody.\n"

    def test_crlf_close_is_accepted(self) -> None:
        raw, _body = _split_frontmatter("---\r\nid: ADR-1\r\n---\r\nBody.\r\n")
        assert "id: ADR-1" in raw
