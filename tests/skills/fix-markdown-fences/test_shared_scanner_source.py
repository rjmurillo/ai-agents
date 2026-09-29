#!/usr/bin/env python3
"""Tests for the shared CommonMark scanner source in ``scripts/hook_utilities``.

The skill scripts import the mirrored copy under ``.claude/lib``. Those tests
cover behaviour but measure the mirror. This file imports the canonical source
(``scripts.hook_utilities.commonmark_*``) directly, so a change to the source
is exercised and measured where it is edited (issue #5352).

The curated case table and the reference parser are the oracle: the container
model must agree with ``markdown-it-py`` on every curated document when driven
by the same loop the scanner uses.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_HERE = Path(__file__).resolve()
for entry in (str(PROJECT_ROOT), str(_HERE.parents[1]), str(_HERE.parent)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import test_fix_fences_contracts as contracts
from commonmark_fence_cases import CASES as FENCE_CASES
from commonmark_fence_cases import oracle_fence_lines

from scripts.hook_utilities import commonmark_containers as containers_src
from scripts.hook_utilities import commonmark_links as links_src


@pytest.fixture
def shared_scanner(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """The fix_fences module with its shared pieces swapped for the source copy."""
    scanner = types.SimpleNamespace(**vars(contracts.mod))
    scanner.ListContainers = containers_src.ListContainers
    scanner.container_closed = containers_src.container_closed
    scanner.is_blank = containers_src.is_blank
    scanner.fence_match = containers_src.fence_match
    monkeypatch.setattr(contracts, "mod", scanner)
    return scanner


@pytest.mark.parametrize("name", sorted(FENCE_CASES))
def test_source_container_model_matches_the_reference_parser(
    name: str, shared_scanner: types.SimpleNamespace
) -> None:
    text = FENCE_CASES[name]
    assert contracts.TestCommonMarkOracle._inside_fence(text) == oracle_fence_lines(text), name


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("```", True),
        ("~~~python", True),
        ("   ```js", True),
        ("``` a ` b", False),
        ("`` not a fence", False),
        ("text", False),
        ("", False),
    ],
)
def test_fence_match_and_starts_fence(line: str, expected: bool) -> None:
    assert containers_src.starts_fence(line) is expected
    assert (containers_src.fence_match(line) is not None) is expected


def test_tilde_fence_may_carry_a_backtick_in_its_info_string() -> None:
    assert containers_src.starts_fence("~~~ a`b")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", True), ("  \t", True), ("x", False), (" ", False)],
)
def test_is_blank_counts_only_spaces_and_tabs(text: str, expected: bool) -> None:
    assert containers_src.is_blank(text) is expected


@pytest.mark.parametrize(
    ("line", "base", "expected"),
    [
        ("text", 0, False),
        ("", 4, False),
        ("  x", 4, True),
        ("    x", 4, False),
        ("\tx", 4, False),
    ],
)
def test_container_closed_when_a_line_dedents_past_the_base(
    line: str, base: int, expected: bool
) -> None:
    assert containers_src.container_closed(line, base) is expected


@pytest.mark.parametrize(
    ("body", "awaiting_title", "open_title"),
    [
        ("[foo]: /url", True, None),
        ("[foo]: <a b>", True, None),
        ('[foo]: /url "title"', False, None),
        ("[foo]: /url 'title'", False, None),
        ("[foo]: /url (t)", False, None),
        ('[foo]: /url "unclosed', False, '"'),
    ],
)
def test_link_reference_reports_what_a_definition_still_expects(
    body: str, awaiting_title: bool, open_title: str | None
) -> None:
    definition = links_src.link_reference(body)

    assert definition == links_src.Definition(awaiting_title=awaiting_title, open_title=open_title)


@pytest.mark.parametrize(
    "body",
    ["[foo]: <broken", "[]: /url", "[foo] /url", "plain prose", "[foo]:", "[foo]: /url trailing"],
)
def test_link_reference_rejects_prose_and_broken_definitions(body: str) -> None:
    assert links_src.link_reference(body) is None


def test_label_only_line_awaits_a_destination() -> None:
    assert links_src.LINK_LABEL_ONLY.match("[foo]:")
    assert links_src.label_opens("[foo")
    assert not links_src.label_opens("plain text")


def test_bare_title_and_title_only_pattern() -> None:
    assert links_src.LINK_TITLE_ONLY.match('"a title"')
    assert not links_src.LINK_TITLE_ONLY.match("not a title")
    assert links_src.bare_title('"title"') is not None
    assert links_src.bare_title("prose") in (None, False)


# Documents that reach the label, destination, and indent branches the curated
# table leaves alone. The reference parser is the oracle for each.
_EXTRA_DOCUMENTS = {
    "escaped bracket inside a multi-line label": "[foo\\]\nbar]: /url\n2. ```\n   code\n   ```\n",
    "label continued on the next line": "[foo\n]: /url\n2. ```\n   code\n   ```\n",
    "destination on the next line, broken": "[foo]:\n<broken\n2. ```\n   code\n   ```\n",
    "destination indented as code on the next line": (
        "[foo]:\n    /url\n2. ```\n   code\n   ```\n"
    ),
    "destination on the next line, valid": "[foo]:\n/url\n2. ```\n   code\n   ```\n",
    "unclosed title then a list marker": '[foo]: /url "open\n2. ```\n   code\n   ```\n',
    "setext-looking line after a label": "[foo]:\n===\n2. ```\n   code\n   ```\n",
    "escape inside a label that spans lines": "[foo\nbar\\]baz]: /url\n2. ```\n   code\n   ```\n",
    "label closes on a later line onto a broken destination": (
        "[foo\n]: <broken\n2. ```\n   code\n   ```\n"
    ),
    "indented continuation of an open label": (
        "[foo\n     bar\n]: /url\n2. ```\n   code\n   ```\n"
    ),
}


@pytest.mark.parametrize("name", sorted(_EXTRA_DOCUMENTS))
def test_extra_documents_match_the_reference_parser(
    name: str, shared_scanner: types.SimpleNamespace
) -> None:
    text = _EXTRA_DOCUMENTS[name]
    assert contracts.TestCommonMarkOracle._inside_fence(text) == oracle_fence_lines(text), name


def test_link_tail_past_the_end_of_the_line_is_none() -> None:
    assert links_src.link_tail("[foo]:", len("[foo]:")) is None


def test_parenthesised_title_rejects_an_unescaped_open_paren() -> None:
    assert links_src.link_reference("[foo]: /url (a(b)") is None


def test_title_must_be_separated_from_an_angle_destination() -> None:
    assert links_src.link_reference('[foo]: <a>"t"') is None


def test_title_end_at_the_end_of_the_line_is_none() -> None:
    assert links_src._title_end("x", 1) is None
