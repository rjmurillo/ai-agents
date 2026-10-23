"""Equivalence tests for the block-only parse behind ``blank_code_block_lines``.

Issue #6734 stopped ``_blank_block_lines`` from running markdown-it's inline
rule, because blanking reads block tokens only. The change is safe only if the
blanked text is identical to what the full parse produced. These tests compare
the two on curated and randomized input, including cases where inline syntax
sits next to block syntax.
"""

from __future__ import annotations

import random

import pytest

from scripts.utils import markdown_parser as mp


def _full_parse_blank(markdown: str) -> str:
    """The pre-change implementation: parse with the inline rule, then blank."""
    md = mp._create_parser()
    tokens = md.parse(markdown)
    mp._raise_if_nesting_truncated(markdown, tokens, md)
    lines = markdown.split("\n")
    mp._blank_matching_token_lines(lines, tokens, mp._CODE_BLOCK_TOKEN_TYPES)
    return "\n".join(lines)


_CASES = [
    "",
    "plain prose\n",
    "```bash\ncp scripts/x .\n```\nafter\n",
    "~~~\ntilde fence\n~~~\n",
    "````\n```\nnested ticks\n```\n````\n",
    "prose\n\n    indented code scripts/x\n\nmore prose\n",
    "- item\n\n      deep indented in list\n- next\n",
    "> quote\n> ```\n> fenced in quote\n> ```\n",
    "1. step\n   ```sh\n   run build/x\n   ```\n2. step\n",
    "| a | b |\n|---|---|\n| `x|y` | ```z``` |\n\n```\ncode\n```\n",
    "Setext\n=====\n\n```\nafter setext\n```\n",
    "[ref]: scripts/x.py\n\n```\nafter ref def\n```\n",
    "<div>\n```\nnot a fence inside html block\n```\n</div>\n",
    "<!-- comment\n```\nstill comment\n-->\n```\nreal code\n```\n",
    "text with `inline ``` code` and *emph* and [link](scripts/x.md)\n",
    "text `a\n```\nfence after unclosed span\n```\n",
    "*emph\n```\nfence breaks emphasis\n```\n*",
    "\\```\nescaped fence is prose\n",
    "Line one  \nline two\\\n```\nfence\n```\n",
    "unterminated fence\n```\nnever closed\n",
    "- a\n  - b\n    - c\n      ```\n      deep\n      ```\n",
]


class TestBlockOnlyParser:
    @pytest.mark.parametrize("markdown", _CASES)
    def test_blanked_text_equals_full_parse(self, markdown: str) -> None:
        assert mp.blank_code_block_lines(markdown) == _full_parse_blank(markdown)

    def test_inline_rule_is_not_run(self) -> None:
        tokens = mp._create_parser(parse_inline=False).parse("a *b* `c`\n")
        inline = [token for token in tokens if token.type == "inline"]

        assert inline
        assert all(not token.children for token in inline)

    def test_default_parser_still_parses_inline(self) -> None:
        tokens = mp._create_parser().parse("a *b* `c`\n")
        inline = [token for token in tokens if token.type == "inline"]

        assert inline
        assert all(token.children for token in inline)

    @pytest.mark.parametrize("markdown", _CASES)
    def test_block_structure_is_identical(self, markdown: str) -> None:
        """type, tag, nesting level, and source map of every block token."""
        full = mp._create_parser().parse(markdown)
        block_only = mp._create_parser(parse_inline=False).parse(markdown)

        assert mp._block_token_shape(full) == mp._block_token_shape(block_only)

    def test_randomized_markdown_matches_full_parse(self) -> None:
        """Seeded fuzz over block and inline syntax mixed on adjacent lines."""
        fragments = [
            "```", "~~~", "````", "    ", "  ", "\t", "- ", "1. ", "> ", "# ", "===", "---",
            "| a | b |", "|---|---|", "`", "``", "*", "_", "[x](y)", "[r]: u", "<div>",
            "</div>", "<!--", "-->", "text", "scripts/x", "\\", "  ", "", "<b>", "&amp;",
        ]  # fmt: skip
        rng = random.Random(6734)
        for _ in range(2500):
            lines = [
                "".join(rng.choice(fragments) for _ in range(rng.randint(0, 4)))
                for _ in range(rng.randint(1, 10))
            ]
            markdown = "\n".join(lines)
            assert mp.blank_code_block_lines(markdown) == _full_parse_blank(markdown), repr(
                markdown
            )


class TestFailClosedIsKept:
    def test_depth_20_fenced_marker_is_still_refused(self) -> None:
        quote = ">" * 20 + " "
        markdown = quote + "```\n" + quote + "<!-- vendor-portability: x -->\n" + quote + "```\n"

        with pytest.raises(mp.MarkdownNestingError):
            mp.blank_code_block_lines(markdown)

    def test_depth_19_is_still_scanned_and_blanked(self) -> None:
        quote = ">" * 19 + " "
        markdown = quote + "```\n" + quote + "hidden scripts/x\n" + quote + "```\n"

        assert "hidden" not in mp.blank_code_block_lines(markdown)
