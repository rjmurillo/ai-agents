"""Markup tests for check_review_thread_resolution_shas.py (issue #6195)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)
sys.path.insert(0, str(_SCRIPTS_DIR))

import check_review_thread_resolution_shas as _mod  # noqa: E402

_MARKER = "<!-- cr-comment:v1:75f6c599dff6a5b0a7422ab3 -->"


def test_inline_html_anchor_href_is_checked() -> None:
    body = 'Fixed in <a href="https://x/commit/abc1234">the fix</a>.'
    assert _mod.extract_shas(body) == ["abc1234"]


def test_html_block_anchor_href_is_checked() -> None:
    body = '<p>\n<a href="https://x/commit/abc1234">fix</a>\n</p>'
    assert _mod.extract_shas(body) == ["abc1234"]


def test_image_target_is_checked() -> None:
    assert _mod.extract_shas("![shot](https://x/commit/abc1234/a.png)") == ["abc1234"]


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
    with patch.object(_mod, "check_ancestor", return_value=(True, "reachable")) as ancestor:
        report = _mod.build_report("o", "r", 1, "b" * 40, [thread], True, ".")
    assert [call.args[0] for call in ancestor.call_args_list] == ["abc1234"]
    assert report["invalid_count"] == 0
    assert report["reachable_count"] == 1
