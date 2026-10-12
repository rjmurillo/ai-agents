"""Tests that documented citation and link syntax inside code is preserved."""

from __future__ import annotations

import pytest

from memory_enhancement.serena_integration import (
    load_memory,
    parse_citation_block,
    parse_link_block,
)


class TestCodeExamplesSurvive:
    """Documented syntax inside code is neither parsed nor stripped."""

    @pytest.mark.unit
    def test_inline_code_in_citation_context_is_kept(self):
        text = "[cite:file](README.md) - see `render()` for details"
        citations = parse_citation_block(text)
        assert citations[0].context == "see `render()` for details"

    @pytest.mark.unit
    def test_link_example_in_fence_is_not_parsed(self):
        text = "```\n[link:related_to](other-memory)\n```\n"
        assert parse_link_block(text) == []

    @pytest.mark.unit
    def test_link_context_keeps_inline_code(self):
        links = parse_link_block("[link:related_to](other) - uses `x`\n")
        assert links[0].context == "uses `x`"

    @pytest.mark.unit
    def test_round_trip_keeps_examples_in_code(self, tmp_path):
        body = (
            "# Syntax (2026-01-01)\n\n"
            "Write `[cite:file](a.py)` or:\n\n"
            "```\n[cite:file](b.py)\n[link:related_to](c)\n```\n"
        )
        path = tmp_path / "syntax.md"
        path.write_text(body, encoding="utf-8")
        memory = load_memory(path)
        assert memory is not None
        assert "[cite:file](a.py)" in memory.content
        assert "[cite:file](b.py)" in memory.content
        assert "[link:related_to](c)" in memory.content
        assert memory.citations == ()

    @pytest.mark.unit
    def test_live_inline_citation_outside_code_is_still_stripped(self, tmp_path):
        path = tmp_path / "live.md"
        path.write_text("# Live (2026-01-01)\n\nText [cite:file](a.py) end.\n", encoding="utf-8")
        memory = load_memory(path)
        assert memory is not None
        assert "[cite:file]" not in memory.content
