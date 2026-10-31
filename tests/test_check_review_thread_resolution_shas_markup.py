"""Markup tests for check_review_thread_resolution_shas.py (issue #6195)."""

from __future__ import annotations

import _markupbase
import sys
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)
sys.path.insert(0, str(_SCRIPTS_DIR))

import check_review_thread_resolution_shas as _mod  # noqa: E402

_MARKER = "<!-- cr-comment:v1:75f6c599dff6a5b0a7422ab3 -->"


def _pre_fix_html_parser():
    # CPython before gh-135664 inherits ParserBase.parse_comment, which ends a
    # comment only at "-->", and treats only script and style as raw text.
    # Patching the base class reproduces that parser on any interpreter.
    return (
        patch.object(HTMLParser, "parse_comment", _markupbase.ParserBase.parse_comment),
        patch.object(HTMLParser, "CDATA_CONTENT_ELEMENTS", ("script", "style")),
    )


def test_inline_html_anchor_href_is_checked() -> None:
    body = 'Fixed in <a href="https://x/commit/abc1234">the fix</a>.'
    assert _mod.extract_shas(body) == ["abc1234"]


def test_html_block_anchor_href_is_checked() -> None:
    body = '<p>\n<a href="https://x/commit/abc1234">fix</a>\n</p>'
    assert _mod.extract_shas(body) == ["abc1234"]


def test_screenshot_attachment_urls_are_ignored() -> None:
    url = "https://github.com/user-attachments/assets/01234567-89ab-cdef-0123-456789abcdef"
    assert _mod.extract_shas(f'![shot]({url}) <img src="{url}"> Fixed in abc1234') == ["abc1234"]


def test_link_to_non_commit_url_is_ignored() -> None:
    body = "See [comment](https://github.com/o/r/pull/1#issuecomment-4207335806)."
    assert _mod.extract_shas(body) == []


def test_commits_path_in_link_is_checked() -> None:
    assert _mod.extract_shas("[fix](https://x/o/r/pull/1/commits/abc1234)") == ["abc1234"]


def test_html_attributes_other_than_links_are_ignored() -> None:
    assert _mod.extract_shas('<span class="deadbee">Fixed in abc1234</span>') == ["abc1234"]


def test_report_ignores_marker_in_resolved_thread() -> None:
    thread = {
        "id": "T1",
        "isResolved": True,
        "path": "a.py",
        "line": 1,
        "comments": {
            "totalCount": 1,
            "nodes": [
                {
                    "id": "C1",
                    "databaseId": 1,
                    "body": f"Fixed in abc1234.\n\n{_MARKER}",
                    "author": {"login": "coderabbitai"},
                    "createdAt": "2026-10-11T00:00:00Z",
                }
            ],
        },
    }
    with patch.object(_mod, "check_ancestor", return_value=(True, "reachable", "")) as ancestor:
        report = _mod.build_report("o", "r", 1, "b" * 40, [thread], True, ".")
    assert [call.args[0] for call in ancestor.call_args_list] == ["abc1234"]
    assert report["invalid_count"] == 0
    assert report["reachable_count"] == 1


@pytest.mark.parametrize("opener", ["<!-->", "<!--->"])
def test_empty_comment_in_html_block_does_not_hide_later_text(opener: str) -> None:
    # 6195-A1: HTML5 ends "<!-->" and "<!--->" at once; text after them renders.
    body = f"<div>\n{opener} Fixed in abc1234 -->\n</div>"
    comment_patch, cdata_patch = _pre_fix_html_parser()
    with comment_patch, cdata_patch:
        assert _mod.extract_shas(body) == ["abc1234"]
    assert _mod.extract_shas(body) == ["abc1234"]


def test_pre_fix_parser_patch_reproduces_the_hidden_text() -> None:
    # 6195-A1: guard that the emulation above is real, so the test above can fail.
    class _Plain(HTMLParser):
        seen: list[str] = []

        def handle_data(self, data: str) -> None:
            self.seen.append(data)

    comment_patch, cdata_patch = _pre_fix_html_parser()
    with comment_patch, cdata_patch:
        plain = _Plain()
        plain.feed("<div><!--> abc1234 --> def5678</div>")
        plain.close()
    assert "abc1234" not in "".join(_Plain.seen)
    assert "def5678" in "".join(_Plain.seen)


@pytest.mark.parametrize("closer", ["-->", "--!>"])
def test_closed_comment_in_html_block_stays_hidden(closer: str) -> None:
    # 6195-A1: a complete comment still hides its body on every parser.
    body = f"<div>\n<!-- deadbee {closer} Fixed in abc1234\n</div>"
    comment_patch, cdata_patch = _pre_fix_html_parser()
    with comment_patch, cdata_patch:
        assert _mod.extract_shas(body) == ["abc1234"]
    assert _mod.extract_shas(body) == ["abc1234"]


@pytest.mark.parametrize("tag", ["script", "style", "iframe", "noembed", "noframes"])
def test_unrendered_element_data_in_html_block_is_skipped(tag: str) -> None:
    # 6195-A2: GitHub strips these elements, so their text never renders.
    body = f"<div>\n<{tag}><b>deadbee</b> --></{tag}>Fixed in abc1234\n</div>"
    comment_patch, cdata_patch = _pre_fix_html_parser()
    with comment_patch, cdata_patch:
        assert _mod.extract_shas(body) == ["abc1234"]
    assert _mod.extract_shas(body) == ["abc1234"]


@pytest.mark.parametrize("tag", ["script", "iframe"])
def test_self_closing_unrendered_element_still_hides_its_text(tag: str) -> None:
    # 6195-A2: HTML ignores "/>" on raw-text elements, so text runs to the end tag.
    body = f"<div>\n<{tag}/>deadbee</{tag}>Fixed in abc1234\n</div>"
    assert _mod.extract_shas(body) == ["abc1234"]


@pytest.mark.parametrize("tag", ["script", "style", "iframe", "noembed", "noframes"])
def test_commit_link_on_unrendered_element_is_skipped(tag: str) -> None:
    # 6195-A2: GitHub strips the whole element, attributes included.
    body = f'<div>\n<{tag} href="https://x/commit/deadbee">x</{tag}>Fixed in abc1234\n</div>'
    assert _mod.extract_shas(body) == ["abc1234"]


def test_self_closing_ordinary_element_keeps_following_text() -> None:
    # 6195-A2 inverse
    assert _mod.extract_shas("<div>\n<br/>Fixed in abc1234\n</div>") == ["abc1234"]


def test_unclosed_unrendered_element_hides_rest_of_block() -> None:
    # 6195-A2: raw text runs to the end of the block when the end tag is missing.
    assert _mod.extract_shas("<div>\n<script>deadbee\n</div>\n\nFixed in abc1234") == ["abc1234"]


def test_rendered_raw_text_element_is_still_checked() -> None:
    # 6195-A2 inverse: xmp shows its text, so a SHA inside it is checked.
    assert _mod.extract_shas("<div>\n<xmp>abc1234</xmp>\n</div>") == ["abc1234"]


def test_unclosed_comment_in_html_block_runs_to_end_of_input() -> None:
    # 6195-A1: HTML5 ends an unclosed comment at end of input; CPython before
    # gh-135664 emitted it as text. Drive the pinned method at end of input.
    parser = _mod._HtmlText()
    parser.rawdata = "<!-- deadbee"
    assert parser.parse_comment(0) == -1
    parser._at_eof = True
    assert parser.parse_comment(0) == len(parser.rawdata)
    assert _mod.extract_shas("<div>\n<!-- deadbee\n</div>\n\nFixed in abc1234") == ["abc1234"]


def test_comment_text_inside_raw_text_element_is_literal() -> None:
    # 6195-A1: xmp shows "<!--" literally on every parser, so the SHA stays visible.
    body = "<div>\n<xmp><!-- abc1234 --></xmp>\n</div>"
    comment_patch, cdata_patch = _pre_fix_html_parser()
    with comment_patch, cdata_patch:
        assert _mod.extract_shas(body) == ["abc1234"]
    assert _mod.extract_shas(body) == ["abc1234"]


def test_unreachable_sha_only_in_code_block_blocks_report() -> None:
    thread = {
        "id": "T1",
        "isResolved": True,
        "comments": {"nodes": [{"body": "```\ngit show deadbee\n```"}], "totalCount": 1},
    }
    with patch(
        "check_review_thread_resolution_shas.check_ancestor",
        return_value=(False, "unreachable", ""),
    ):
        report = _mod.build_report("o", "r", 1, "b" * 40, [thread], True, ".")
    assert report["fetched_pages_complete"] is True
    assert report["sha_reference_count"] == 1
    assert report["unreachable_count"] == 1
