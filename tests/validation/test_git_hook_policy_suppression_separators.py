"""Only a newline ends a scanned line in the suppression gate (issue #7591).

Form feed, vertical tab, U+2028, a lone carriage return, and similar
separators must not split one physical line, or an allowed directive could
hide a second rule id after the separator.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy
from tests.validation._suppression_gate_repo import (
    ENTRY_IDS,
    ENTRY_POINTS,
    EXEC_RULE,
    SOURCE,
    SUBPROCESS_RULE,
    allowed,
    body,
    git,
    repo_with_change,
)

SEPARATORS = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029", "\r"]


def test_scan_lines_split_on_newline_only() -> None:
    assert policy.suppression_scan_lines("a\x0cb\r\nc\n") == ["a\x0cb", "c"]
    assert policy.suppression_scan_lines("a\n\nb") == ["a", "", "b"]
    assert policy.suppression_scan_lines("") == []


@pytest.mark.parametrize("separator", SEPARATORS, ids=[f"U+{ord(c):04X}" for c in SEPARATORS])
def test_separator_cannot_hide_a_rule_list(separator: str) -> None:
    line = allowed(EXEC_RULE) + separator + ", python.lang.other.other"
    text = body(line)
    assert policy._full_content_suppression_violations("HEAD", SOURCE, text) == [f"HEAD:{SOURCE}:5"]


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=ENTRY_IDS)
@pytest.mark.parametrize("separator", ["\x0c", "\u2028", "\r"], ids=["U+000C", "U+2028", "U+000D"])
def test_separator_bypass_blocks_at_every_entry_point(
    tmp_path: Path,
    entry_point: Callable[[Path, str], int],
    separator: str,
) -> None:
    line = allowed(EXEC_RULE) + separator + ", " + SUBPROCESS_RULE
    repo, base = repo_with_change(tmp_path, SOURCE, line)
    assert entry_point(repo, base) == 1


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=ENTRY_IDS)
def test_crlf_file_still_allows_the_listed_line(
    tmp_path: Path,
    entry_point: Callable[[Path, str], int],
) -> None:
    repo, base = repo_with_change(tmp_path, SOURCE, allowed(EXEC_RULE))
    target = repo / SOURCE
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    git(repo, "add", "-A")
    assert entry_point(repo, base) == 0


@pytest.mark.parametrize(
    "text",
    ['["a\u2028b"]', '{"cells": "a\u2028b"}', "a\u2028b"],
    ids=["list", "cells", "bad"],
)
def test_notebook_fallbacks_split_on_newline_only(text: str) -> None:
    assert "\u2028" in text
    assert policy._notebook_code_lines(text) == [text]


def test_unreadable_object_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo, _base = repo_with_change(tmp_path, SOURCE, allowed(EXEC_RULE))
    assert policy._suppression_text_or_none("HEAD:missing.py", repo) is None
    assert "missing.py" in capsys.readouterr().err
    assert policy._diff_full_content_suppression_violations(["missing.py"], repo) is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(allowed(EXEC_RULE), [], id="listed"),
        pytest.param(
            allowed(EXEC_RULE) + "\x0c, " + SUBPROCESS_RULE, [f"HEAD:{SOURCE}:5"], id="ff"
        ),
    ],
)
def test_diff_full_content_reads_exact_bytes(
    tmp_path: Path, line: str, expected: list[str]
) -> None:
    repo, _base = repo_with_change(tmp_path, SOURCE, line)
    git(repo, "commit", "-q", "-m", "head")
    assert policy._diff_full_content_suppression_violations([SOURCE], repo) == expected
