#!/usr/bin/env python3
"""Tests for the one frontmatter parser, ``scripts/hook_utilities/frontmatter_block.py``.

Covers positive, negative and edge cases per `.agents/governance/TESTING-RIGOR.md`,
a negative control for each integration hazard recorded at
`.project-toolkit/analysis/frontmatter-parser-build-vs-buy.md`, and parity with
``python-frontmatter``, which stays installed as the test oracle for the fence rule.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from frontmatter.default_handlers import YAMLHandler

import scripts.hook_utilities.frontmatter_block as frontmatter_block
from scripts.hook_utilities.frontmatter_block import (
    FM_BOUNDARY,
    FM_BOUNDARY_PATTERN,
    FrontmatterError,
    FrontmatterStatus,
    load_frontmatter,
    split_frontmatter,
)

parse = functools.partial(frontmatter_block.parse_frontmatter, yaml=yaml)

BODY = "id: ADR-999\nstatus: accepted"


class TestAcceptedFences:
    """Fence shapes the contract accepts, with the mapping intact."""

    @pytest.mark.parametrize(
        ("label", "text"),
        [
            ("clean", f"---\n{BODY}\n---\nBody.\n"),
            # The exact case issue #5275 reported: one trailing space crashed
            # generate_adr_index.py while the lifecycle gate passed it.
            ("closing fence with one trailing space", f"---\n{BODY}\n--- \nBody.\n"),
            ("closing fence with a tab", f"---\n{BODY}\n---\t\nBody.\n"),
            ("four dashes", f"---\n{BODY}\n----\nBody.\n"),
            ("opening fence padded", f"--- \n{BODY}\n---\nBody.\n"),
            ("crlf line endings", f"---\r\n{BODY}\r\n---\r\nBody.\r\n"),
            ("closing fence at EOF, no newline", f"---\n{BODY}\n---"),
        ],
    )
    def test_accepts(self, label: str, text: str) -> None:
        result = parse(text)
        assert result.status is FrontmatterStatus.VALID, label
        assert result.metadata == {"id": "ADR-999", "status": "accepted"}, label
        assert result.ok and result.present, label


class TestRejectedFences:
    """Shapes that must not be read as a closed block."""

    def test_trailing_text_after_fence_is_not_a_close(self) -> None:
        """`--- nope` is the one slip that signals a real authoring mistake."""
        result = parse(f"---\n{BODY}\n--- nope\nBody.\n")
        assert result.status is FrontmatterStatus.UNTERMINATED
        assert result.metadata is None
        assert result.present is True

    def test_no_closing_fence(self) -> None:
        result = parse(f"---\n{BODY}\nBody.\n")
        assert result.status is FrontmatterStatus.UNTERMINATED
        assert result.error is not None
        assert "closing" in result.error

    def test_bom_before_opening_fence_is_absent(self) -> None:
        """A BOM means the file does not start with the fence. Matches every
        pre-existing parser, all of which returned "no frontmatter" here."""
        result = parse(f"﻿---\n{BODY}\n---\nBody.\n")
        assert result.status is FrontmatterStatus.ABSENT

    def test_no_frontmatter_at_all(self) -> None:
        result = parse("Just body text.\n")
        assert result.status is FrontmatterStatus.ABSENT
        assert result.metadata is None
        assert result.body == "Just body text.\n"
        assert result.present is False


class TestStatusDiscrimination:
    """H1: `frontmatter.loads()` collapses these four into `metadata == {}`.

    Each must stay distinguishable; generate_adr_index.py raises a named error
    for one of them and routes another to "Needs backfill".
    """

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Just body.\n", FrontmatterStatus.ABSENT),
            (f"---\n{BODY}\nBody.\n", FrontmatterStatus.UNTERMINATED),
            ("---\n---\nBody.\n", FrontmatterStatus.EMPTY),
            ("---\n- a\n- b\n---\nBody.\n", FrontmatterStatus.NOT_A_MAPPING),
            ("---\njust a string\n---\nBody.\n", FrontmatterStatus.NOT_A_MAPPING),
            ('---\nid: "ADR-1\n---\nBody.\n', FrontmatterStatus.MALFORMED),
            ("---\ndesc: foo: bar\n---\nBody.\n", FrontmatterStatus.MALFORMED),
            (f"---\n{BODY}\n---\nBody.\n", FrontmatterStatus.VALID),
        ],
    )
    def test_each_state_is_distinct(self, text: str, expected: FrontmatterStatus) -> None:
        assert parse(text).status is expected

    def test_all_four_would_collapse_under_the_naive_library_call(self) -> None:
        """Negative control proving the distinction is not free.

        If this ever fails, upstream started distinguishing these and the
        adapter's reason for existing should be re-examined.
        """
        import frontmatter

        collapsing = [
            "Just body.\n",
            f"---\n{BODY}\nBody.\n",
            "---\n---\nBody.\n",
            "---\n- a\n---\nBody.\n",
        ]
        assert all(frontmatter.loads(t).metadata == {} for t in collapsing)
        assert len({parse(t).status for t in collapsing}) == 4

    def test_empty_block_parses_to_an_empty_mapping(self) -> None:
        result = parse("---\n---\nBody.\n")
        assert result.metadata == {}
        assert result.ok is True


class TestDuplicateKeys:
    """Repeated keys are a defect for the ADR gates, not last-one-wins."""

    def test_duplicate_key_rejected_by_default(self) -> None:
        result = parse("---\nid: A\nid: B\n---\nBody.\n")
        assert result.status is FrontmatterStatus.MALFORMED
        assert result.error is not None
        assert "duplicate key" in result.error

    def test_duplicate_key_nested_in_a_value_is_rejected(self) -> None:
        text = "---\nmeta:\n  a: 1\n  a: 2\n---\nBody.\n"
        assert parse(text).status is FrontmatterStatus.MALFORMED

    def test_duplicate_key_allowed_when_opted_in(self) -> None:
        result = parse("---\nid: A\nid: B\n---\nBody.\n", allow_duplicate_keys=True)
        assert result.status is FrontmatterStatus.VALID
        assert result.metadata == {"id": "B"}

    def test_merge_key_loads_strict_but_a_repeated_explicit_key_does_not(self) -> None:
        """`<<` is a merge, not a repeated key; an explicit override of a merged key is fine."""
        text = "---\nbase: &b {x: 1}\nchild:\n  <<: *b\n  x: 2\n---\nBody.\n"

        merged = parse(text)
        repeated = parse(text.replace("  x: 2\n", "  x: 2\n  x: 3\n"))

        assert merged.status is FrontmatterStatus.VALID
        assert merged.metadata == {"base": {"x": 1}, "child": {"x": 2}}
        assert repeated.status is FrontmatterStatus.MALFORMED

    def test_unhashable_key_does_not_raise_typeerror(self) -> None:
        """`? [a, b]` builds a list key. A set-based duplicate check raises
        TypeError here, escaping the caller's YAMLError handling and turning a
        documented exit code into a traceback."""
        result = parse("---\n? [a, b]\n: value\n---\nBody.\n")
        assert result.status in (FrontmatterStatus.VALID, FrontmatterStatus.MALFORMED)

    def test_genuinely_duplicated_unhashable_keys_are_caught(self) -> None:
        result = parse("---\n? [a, b]\n: 1\n? [a, b]\n: 2\n---\nBody.\n")
        assert result.status is FrontmatterStatus.MALFORMED


class TestLoaderPin:
    """H4 and H5: loader selection must be explicit and must not leak."""

    def test_loader_is_not_injected_into_metadata(self) -> None:
        """The obvious spelling, `frontmatter.loads(text, Loader=...)`, puts a
        `Loader` key in the parsed mapping because that parameter means default
        metadata. This is the negative control for that footgun."""
        import frontmatter

        naive = frontmatter.loads(f"---\n{BODY}\n---\nB\n", Loader=yaml.SafeLoader)
        assert "Loader" in naive.metadata

        result = parse(f"---\n{BODY}\n---\nB\n")
        assert result.metadata is not None
        assert "Loader" not in result.metadata

    def test_unsafe_python_tags_are_rejected(self) -> None:
        text = "---\na: 1\nb: !!python/object/apply:os.system []\n---\nX\n"
        assert parse(text).status is FrontmatterStatus.MALFORMED


class TestBodySplit:
    """The body is what prose consumers read."""

    def test_body_excludes_the_frontmatter(self) -> None:
        result = parse(f"---\n{BODY}\n---\n# Title\n\nPara.\n")
        assert result.body == "# Title\n\nPara.\n"
        assert "status: accepted" not in result.body

    def test_body_keeps_a_later_horizontal_rule(self) -> None:
        """Only the first two fences delimit the block; `---` in prose stays."""
        result = parse(f"---\n{BODY}\n---\nA.\n\n---\n\nB.\n")
        assert "---" in result.body
        assert result.body.endswith("B.\n")

    def test_raw_is_the_text_between_the_fences(self) -> None:
        result = parse(f"---\n{BODY}\n---\nBody.\n")
        assert "id: ADR-999" in result.raw
        assert "Body." not in result.raw

    def test_absent_frontmatter_returns_the_whole_text_as_body(self) -> None:
        text = "# Title\n\nNo frontmatter here.\n"
        assert parse(text).body == text


class TestStrictMode:
    """`strict` is for callers that already propagate an exception."""

    @pytest.mark.parametrize(
        "text",
        [
            f"---\n{BODY}\nBody.\n",
            '---\nid: "ADR-1\n---\nBody.\n',
            "---\n- a\n---\nBody.\n",
        ],
    )
    def test_strict_raises_on_a_broken_block(self, text: str) -> None:
        with pytest.raises(FrontmatterError):
            parse(text, strict=True)

    def test_strict_does_not_raise_on_absent_frontmatter(self) -> None:
        """A file with no block is a routine input, not a defect."""
        result = parse("Just body.\n", strict=True)
        assert result.status is FrontmatterStatus.ABSENT

    def test_strict_does_not_raise_on_a_valid_block(self) -> None:
        result = parse(f"---\n{BODY}\n---\nBody.\n", strict=True)
        assert result.status is FrontmatterStatus.VALID


PARITY_SHAPES = [
    f"---\n{BODY}\n---\nBody.\n",
    f"---\n{BODY}\n--- \nBody.\n",
    f"---\n{BODY}\n----\nBody.\n",
    f"---\n{BODY}\n--- nope\nBody.\n",
    f"---\n{BODY}\nBody.\n",
    f"----\n{BODY}\n---\n",
    f"\n---\n{BODY}\n---\n",
    f"---\r\n{BODY}\r\n---\r\nBody.\r\n",
    "---\n---\n",
    f"---\n\n\n{BODY}\n---\n\n\nBody.\n",
    f"\ufeff---\n{BODY}\n---\n",
    "---",
    f"---\n{BODY}\n---",
    "Just body.\n",
    "",
]


class TestLibraryParity:
    """The fence rule is python-frontmatter's, checked against the installed library."""

    def test_pattern_and_flags_equal_the_library(self) -> None:
        assert FM_BOUNDARY_PATTERN == YAMLHandler.FM_BOUNDARY.pattern
        assert FM_BOUNDARY.flags == YAMLHandler.FM_BOUNDARY.flags

    @pytest.mark.parametrize("text", PARITY_SHAPES)
    def test_detect_and_split_equal_the_library(self, text: str) -> None:
        handler = YAMLHandler()
        result = split_frontmatter(text)

        if not handler.detect(text):
            assert result.status is FrontmatterStatus.ABSENT
            return
        try:
            raw, content = handler.split(text)
        except ValueError:
            assert result.status is FrontmatterStatus.UNTERMINATED
            return
        assert result.status is FrontmatterStatus.VALID
        assert result.raw == raw
        assert result.body == content.removeprefix("\n")


class TestSplit:
    """split_frontmatter reads no YAML and reports where the body starts."""

    def test_body_start_slices_the_source(self) -> None:
        text = f"---\n{BODY}\n---\nBody.\n"

        result = split_frontmatter(text)

        assert result.found
        assert result.raw == f"\n{BODY}\n"
        assert text[result.body_start :] == "Body.\n"
        assert text.count("\n", 0, result.body_start) == 4

    def test_offsets_locate_both_fences(self) -> None:
        text = f"---\n{BODY}\n----\n\n\nBody.\n"

        result = split_frontmatter(text)

        assert text[: result.raw_start] == "---"
        assert text[result.raw_start : result.raw_end] == result.raw
        assert text[result.raw_end : result.fence_end] == "----\n"
        assert text[result.fence_end :] == "\n\nBody.\n"
        assert result.body == "Body.\n"

    def test_fence_end_is_text_length_when_the_closing_fence_ends_the_file(self) -> None:
        text = f"---\n{BODY}\n---"

        result = split_frontmatter(text)

        assert result.fence_end == len(text)
        assert result.body == ""

    def test_absent_block_returns_whole_text(self) -> None:
        result = split_frontmatter("Body.\n")

        assert (result.status, result.raw, result.body, result.body_start) == (
            FrontmatterStatus.ABSENT,
            "",
            "Body.\n",
            0,
        )
        assert (result.raw_start, result.raw_end, result.fence_end) == (0, 0, 0)
        assert not result.found

    def test_unterminated_block_returns_whole_text(self) -> None:
        text = f"---\n{BODY}\n"

        result = split_frontmatter(text)

        assert result.status is FrontmatterStatus.UNTERMINATED
        assert (result.raw, result.body, result.body_start) == ("", text, 0)

    def test_malformed_yaml_still_splits(self) -> None:
        result = split_frontmatter("---\na: [\n---\nBody.\n")

        assert result.found
        assert result.body == "Body.\n"


class TestValueType:
    """A non-mapping block names the type YAML built, so callers need no reparse."""

    @pytest.mark.parametrize(
        ("text", "expected"), [("---\n- a\n---\n", "list"), ("---\nhello\n---\n", "str")]
    )
    def test_not_a_mapping_names_the_type(self, text: str, expected: str) -> None:
        result = parse(text)

        assert result.status is FrontmatterStatus.NOT_A_MAPPING
        assert result.value_type == expected

    def test_other_statuses_carry_no_type(self) -> None:
        assert parse(f"---\n{BODY}\n---\n").value_type is None
        assert parse("---\na: [\n---\n").value_type is None


class TestLoad:
    """load_frontmatter returns only a mapping, last-one-wins by default."""

    def test_returns_mapping(self) -> None:
        assert load_frontmatter(f"---\n{BODY}\n---\n", yaml) == {
            "id": "ADR-999",
            "status": "accepted",
        }

    @pytest.mark.parametrize(
        "text",
        ["Body.\n", f"---\n{BODY}\n", "---\n---\n", "---\n- a\n---\n", "---\na: [\n---\n"],
    )
    def test_returns_none_for_unusable_blocks(self, text: str) -> None:
        assert load_frontmatter(text, yaml) is None

    def test_duplicate_keys_last_one_wins_by_default(self) -> None:
        assert load_frontmatter("---\nid: A\nid: B\n---\n", yaml) == {"id": "B"}

    def test_duplicate_keys_rejected_on_request(self) -> None:
        assert (
            load_frontmatter("---\nid: A\nid: B\n---\n", yaml, allow_duplicate_keys=False) is None
        )


class TestLoaderOverride:
    """A caller may name its loader, but only a SafeLoader subclass."""

    def test_custom_safe_loader_is_used(self) -> None:
        # Any: mypy sees yaml.SafeLoader as Any in tests, so a class statement
        # subclassing it fails the strict "subclass Any" check.
        upper_loader: Any = type("upper_loader", (yaml.SafeLoader,), {})
        upper_loader.add_constructor(
            "tag:yaml.org,2002:str", lambda loader, node: loader.construct_scalar(node).upper()
        )

        result = parse("---\nid: abc\n---\n", loader=upper_loader)

        assert result.metadata == {"ID": "ABC"}

    def test_non_safe_loader_is_refused(self) -> None:
        with pytest.raises(TypeError, match="SafeLoader"):
            parse("---\nid: abc\n---\n", loader=yaml.UnsafeLoader)

    def test_strict_loader_is_cached_per_yaml_module(self) -> None:
        parse("---\na: 1\n---\n")
        parse("---\na: 1\n---\n")

        assert len(frontmatter_block._STRICT_LOADERS) == 1


class TestDecodeFrontmatterYaml:
    """Raw-text entry point: no fence handling, same loader choice as the parser."""

    # staticmethod: Python 3.14 binds a bare functools.partial class attribute as a method.
    decode = staticmethod(functools.partial(frontmatter_block.decode_frontmatter_yaml, yaml=yaml))

    def test_default_loader_rejects_duplicate_keys(self) -> None:
        with pytest.raises(yaml.YAMLError, match="duplicate key 'a'"):
            self.decode("a: 1\na: 2\n")

    def test_allow_duplicate_keys_is_last_one_wins(self) -> None:
        assert self.decode("a: 1\na: 2\n", allow_duplicate_keys=True) == {"a": 2}

    @pytest.mark.parametrize(
        ("raw", "expected"), [("", None), ("- x\n- y\n", ["x", "y"]), ("s\n", "s")]
    )
    def test_null_list_and_scalar_come_back_unclassified(self, raw: str, expected: object) -> None:
        assert self.decode(raw, allow_duplicate_keys=True) == expected

    def test_fence_lines_are_not_stripped(self) -> None:
        # Raw text is decoded as given. A caller that passes fences gets a
        # multi-document stream, which yaml.load rejects: nothing re-fences or unfences.
        with pytest.raises(yaml.YAMLError):
            self.decode("---\na: 1\n---\n", allow_duplicate_keys=True)

    def test_error_keeps_type_and_marks_of_safe_load(self) -> None:
        bad = "a: 1\nb: [unclosed\n"
        with pytest.raises(yaml.YAMLError) as decoded:
            self.decode(bad, allow_duplicate_keys=True)
        with pytest.raises(yaml.YAMLError) as direct:
            yaml.safe_load(bad)
        assert type(decoded.value) is type(direct.value)
        assert str(decoded.value) == str(direct.value)

    def test_custom_loader_is_used(self) -> None:
        marker: Any = type("marker_loader", (yaml.SafeLoader,), {})
        marker.add_constructor("tag:yaml.org,2002:str", lambda loader, node: "X")
        assert self.decode("a: b\n", loader=marker) == {"X": "X"}

    def test_non_safe_loader_is_refused(self) -> None:
        with pytest.raises(TypeError, match="SafeLoader"):
            self.decode("a: 1\n", loader=yaml.UnsafeLoader)

    def test_parse_frontmatter_reads_through_the_entry_point(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []
        real = frontmatter_block.decode_frontmatter_yaml

        def spy(raw: str, yaml_module: Any, **kwargs: Any) -> Any:
            seen.append(raw)
            return real(raw, yaml_module, **kwargs)

        monkeypatch.setattr(frontmatter_block, "decode_frontmatter_yaml", spy)
        assert parse("---\na: 1\n---\n").metadata == {"a": 1}
        assert seen == ["\na: 1\n"]


class TestShippedLibStaysStdlibOnly:
    """The module ships in the plugin lib trees, so it imports no third-party module."""

    def test_imports_only_stdlib(self) -> None:
        tree = ast.parse(Path(frontmatter_block.__file__).read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])

        assert roots <= {"__future__", "dataclasses", "enum", "re", "types", "typing"}

    def test_boundary_is_the_only_compiled_pattern(self) -> None:
        compiled = [
            value for value in vars(frontmatter_block).values() if isinstance(value, re.Pattern)
        ]

        assert compiled == [FM_BOUNDARY]
