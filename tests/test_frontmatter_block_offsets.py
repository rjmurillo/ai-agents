"""Opening-line offset and loader cache of the one parser.

Follow-ups from PR #7531's review:
- ``open_end`` lets callers read the payload from the physical opening line,
  where the fence match can swallow whitespace-only lines.
- The strict loader is cached per ``yaml`` module object, not per ``id()``.
"""

from __future__ import annotations

import types

import yaml

import scripts.hook_utilities.frontmatter_block as frontmatter_block
from scripts.hook_utilities.frontmatter_block import (
    split_frontmatter,
)


class TestOpenEnd:
    def test_open_end_is_just_past_the_opening_line(self) -> None:
        text = "---\nname: x\n---\nBody\n"

        split = split_frontmatter(text)

        assert split.open_end == 4
        assert text[split.open_end : split.raw_end] == "name: x\n"

    def test_open_end_keeps_a_tab_line_the_fence_match_swallows(self) -> None:
        text = "---\n\t\nname: x\n---\nBody\n"

        split = split_frontmatter(text)

        assert split.raw_start > split.open_end
        assert text[split.open_end : split.raw_end] == "\t\nname: x\n"

    def test_open_end_on_crlf_text_starts_the_next_line(self) -> None:
        text = "---\r\nname: x\r\n---\r\nBody\r\n"

        split = split_frontmatter(text)

        assert text[split.open_end : split.raw_end] == "name: x\r\n"

    def test_open_end_is_zero_without_a_closed_block(self) -> None:
        assert split_frontmatter("no fence\n").open_end == 0
        assert split_frontmatter("---\nname: x\n").open_end == 0


class TestLoaderCache:
    def test_the_cache_is_keyed_by_module_object(self) -> None:
        loader = frontmatter_block._strict_loader(yaml)

        assert frontmatter_block._STRICT_LOADERS[yaml] is loader
        assert frontmatter_block._strict_loader(yaml) is loader

    def test_a_distinct_module_object_gets_its_own_loader(self) -> None:
        stand_in = types.ModuleType("yaml_stand_in")
        stand_in.__dict__.update(yaml.__dict__)
        own = frontmatter_block._strict_loader(yaml)
        try:
            loader = frontmatter_block._strict_loader(stand_in)
            assert frontmatter_block._STRICT_LOADERS[stand_in] is loader
            assert own is not loader
        finally:
            frontmatter_block._STRICT_LOADERS.pop(stand_in, None)
