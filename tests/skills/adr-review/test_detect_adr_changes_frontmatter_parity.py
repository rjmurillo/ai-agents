#!/usr/bin/env python3
"""detect_adr_changes uses the one shared frontmatter parser.

Split from `test_detect_adr_changes.py` to keep each file under the 500-line
taste-lint limit, matching how this directory already splits by concern
(`_duplicate_keys`, `_encoding`, `_status_scalar`).

`detect_adr_changes.py` ships inside a plugin root. It imports
`hook_utilities.frontmatter_block` through the ADR-047 inline lib bootstrap
instead of keeping its own copy of the fence pattern. The core's pattern is
pinned against `python-frontmatter` in `tests/test_frontmatter_block.py`, so
these tests pin only that this script defers to the core and keeps no fence
logic of its own.

Issue #4918 is what an unpinned fence costs: a gate keying on the literal
`"---"` silently passed memory files the real parser rejected, because the
actual boundary accepts three OR MORE dashes. A gate with false negatives is
decorative.
"""

from __future__ import annotations

import ast
import re
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

SCRIPT = ".claude/skills/adr-review/scripts/detect_adr_changes.py"
mod = import_skill_script(SCRIPT)

_split_frontmatter = mod._split_frontmatter


def _script_source() -> str:
    return (Path(PROJECT_ROOT) / SCRIPT).read_text(encoding="utf-8")


class TestScriptUsesTheCore:
    """The script defers to `hook_utilities.frontmatter_block`, with no fence copy."""

    def test_imports_the_shared_parser(self) -> None:
        tree = ast.parse(_script_source())
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "hook_utilities.frontmatter_block"
            for alias in node.names
        }
        assert {"parse_frontmatter", "split_frontmatter"} <= imported

    def test_keeps_no_fence_pattern_of_its_own(self) -> None:
        source = _script_source()
        assert not re.search(r"-\{3,\}", source)
        assert not hasattr(mod, "FRONTMATTER_BOUNDARY")
        assert not hasattr(mod, "FRONTMATTER_DELIM")

    def test_does_not_cite_the_retired_contract_module(self) -> None:
        assert "frontmatter_contract" not in _script_source()


class TestSplitFollowsTheSharedFenceRule:
    """Shape-by-shape fence behavior, so a drift names the shape it broke."""

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
    def test_close_fence_shapes(self, label: str, fence: str, is_close: bool) -> None:
        raw, _body = _split_frontmatter(f"---\nid: ADR-1\n{fence}\nBody.\n")
        assert (raw != "") is is_close, label

    def test_four_dash_close_is_accepted(self) -> None:
        """The regression issue #5275 reported from this side."""
        raw, body = _split_frontmatter("---\nid: ADR-1\nstatus: accepted\n----\nBody.\n")
        assert "id: ADR-1\nstatus: accepted\n" in raw
        assert body == "Body.\n"

    def test_padded_close_is_accepted(self) -> None:
        """The exact input from issue #5275: one trailing space."""
        raw, body = _split_frontmatter("---\nid: ADR-1\n--- \nBody.\n")
        assert "id: ADR-1" in raw
        assert body == "Body.\n"

    def test_trailing_text_is_not_a_close(self) -> None:
        raw, body = _split_frontmatter("---\nid: ADR-1\n--- nope\nBody.\n")
        assert raw == ""
        assert body == "---\nid: ADR-1\n--- nope\nBody.\n"

    def test_crlf_close_is_accepted(self) -> None:
        raw, _body = _split_frontmatter("---\r\nid: ADR-1\r\n---\r\nBody.\r\n")
        assert "id: ADR-1" in raw


class TestSplitFrontmatter:
    """Tests for _split_frontmatter helper."""

    def test_splits_frontmatter_and_body(self) -> None:
        content = "---\nstatus: proposed\n---\n\n# Body\n\nText.\n"
        frontmatter, body = _split_frontmatter(content)
        assert "status: proposed" in frontmatter
        # The shared fence rule's trailing `\s*` absorbs blank lines after the close.
        assert body == "# Body\n\nText.\n"

    def test_no_frontmatter_returns_empty_and_full_content(self) -> None:
        content = "# Body only\n\nNo frontmatter.\n"
        frontmatter, body = _split_frontmatter(content)
        assert frontmatter == ""
        assert body == content

    def test_unterminated_frontmatter_treated_as_body(self) -> None:
        content = "---\nstatus: proposed\n# never closes\n"
        frontmatter, body = _split_frontmatter(content)
        assert frontmatter == ""
        assert body == content
