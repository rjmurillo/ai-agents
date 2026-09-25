"""Tests for tool-confined filesystem access (CWE-22) in
scripts/metrics/sg_reference_ab_toolloop.py (#5856, REQ-8 support):
_confine_path/_confine_walked_candidate, _tool_read_file, and _tool_grep.

Split out of ``tests/metrics/test_sg_reference_ab.py`` under the taste-lints
file-size gate. run_investigate_loop's own tests (the tool loop built on top
of these handlers) live in the sibling
``tests/metrics/test_sg_reference_ab_toolloop_loop.py``, split out under the
same gate; transport and failure classification are tested in
``tests/metrics/test_sg_reference_ab_api.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.metrics import sg_reference_ab_toolloop as toolloop

# ---------------------------------------------------------------------------
# Tool confinement (CWE-22)
# ---------------------------------------------------------------------------


def test_tool_read_file_reads_relative_path_within_fixture(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello\n", encoding="utf-8")

    assert toolloop._tool_read_file(tmp_path, "a.py") == "hello\n"


def test_tool_read_file_rejects_absolute_path(tmp_path: Path) -> None:
    assert "rejected" in toolloop._tool_read_file(tmp_path, "/etc/passwd")


def test_tool_read_file_rejects_parent_traversal(tmp_path: Path) -> None:
    assert "rejected" in toolloop._tool_read_file(tmp_path, "../outside.txt")


def test_tool_read_file_reports_missing_file(tmp_path: Path) -> None:
    assert "not a file" in toolloop._tool_read_file(tmp_path, "missing.py")


def test_confine_path_rejects_a_symlink_that_resolves_outside_the_root(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (fixture_dir / "link.txt").symlink_to(outside)

    assert toolloop._confine_path(fixture_dir, "link.txt") is None


def test_tool_read_file_oserror_on_permission_denied(tmp_path: Path) -> None:
    target = tmp_path / "denied.py"
    target.write_text("secret", encoding="utf-8")
    os.chmod(target, 0)

    try:
        result = toolloop._tool_read_file(tmp_path, "denied.py")
    finally:
        os.chmod(target, 0o600)

    if os.geteuid() == 0:
        pytest.skip("running as root; chmod 0 does not deny root read access")
    assert "Error reading" in result


def test_tool_grep_finds_matches_with_path_and_line(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("line one\nvuln here\nline three\n", encoding="utf-8")

    result = toolloop._tool_grep(tmp_path, "vuln", None)

    assert result == "a.py:2:vuln here"


def test_tool_grep_scoped_to_one_path(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("vuln here\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("vuln here too\n", encoding="utf-8")

    result = toolloop._tool_grep(tmp_path, "vuln", "b.py")

    assert result == "b.py:1:vuln here too"


def test_tool_grep_no_matches(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("nothing interesting here\n", encoding="utf-8")

    result = toolloop._tool_grep(tmp_path, "absolutely_no_such_token_here", None)

    assert result == "No matches."


def test_tool_grep_rejects_invalid_pattern(tmp_path: Path) -> None:
    assert "invalid pattern" in toolloop._tool_grep(tmp_path, "(unclosed", None)


def test_tool_grep_rejects_absolute_scoped_path(tmp_path: Path) -> None:
    assert "rejected" in toolloop._tool_grep(tmp_path, "x", "/etc/passwd")


def test_tool_grep_requires_pattern(tmp_path: Path) -> None:
    assert "pattern is required" in toolloop._tool_grep(tmp_path, "", None)


def test_tool_grep_skips_directory_entries(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")

    result = toolloop._tool_grep(tmp_path, "needle", None)

    assert result == "a.py:1:needle"


def test_tool_grep_skips_a_file_symlink_that_resolves_outside_the_fixture(
    tmp_path: Path,
) -> None:
    """_tool_read_file already rejects a caller-supplied path that is (or
    traverses through) a symlink escaping the root, via _confine_path. This
    proves _tool_grep applies the same confinement to every file it *walks*
    with rglob(), not only to a caller-supplied path: a file symlink sitting
    inside the fixture must not leak the outside file's content into a grep
    result.
    """
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("vuln secret outside\n", encoding="utf-8")
    (fixture_dir / "link.txt").symlink_to(outside)
    (fixture_dir / "real.py").write_text("vuln here\n", encoding="utf-8")

    result = toolloop._tool_grep(fixture_dir, "vuln", None)

    assert result == "real.py:1:vuln here"
    assert "outside" not in result
    assert "link.txt" not in result


def test_tool_grep_skips_unreadable_file(tmp_path: Path) -> None:
    denied = tmp_path / "denied.py"
    denied.write_text("needle\n", encoding="utf-8")
    (tmp_path / "readable.py").write_text("needle too\n", encoding="utf-8")
    os.chmod(denied, 0)

    try:
        result = toolloop._tool_grep(tmp_path, "needle", None)
    finally:
        os.chmod(denied, 0o600)

    if os.geteuid() == 0:
        pytest.skip("running as root; chmod 0 does not deny root read access")
    assert "readable.py:1:needle too" in result
    assert "denied.py" not in result

