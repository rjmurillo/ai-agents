from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.ci import diff_line_scope


def completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_normalize_path_strips_dot_prefix_and_backslashes() -> None:
    assert diff_line_scope.normalize_path("  ./scripts\\ci\\a.py  ") == "scripts/ci/a.py"


def test_normalize_path_leaves_plain_path_untouched() -> None:
    assert diff_line_scope.normalize_path("scripts/ci/a.py") == "scripts/ci/a.py"


def test_unquote_diff_path_passes_through_unquoted_path() -> None:
    assert diff_line_scope.unquote_diff_path("scripts/ci/a.py") == "scripts/ci/a.py"


def test_unquote_diff_path_decodes_escaped_quote() -> None:
    assert diff_line_scope.unquote_diff_path('"scripts/od\\"d.py"') == 'scripts/od"d.py'


def test_unquote_diff_path_decodes_escaped_backslash() -> None:
    assert diff_line_scope.unquote_diff_path('"scripts/od\\\\d.py"') == "scripts/od\\d.py"


def test_unquote_diff_path_keeps_raw_non_ascii() -> None:
    # core.quotePath=false leaves UTF-8 bytes raw inside the quotes; git's
    # own output decoding already handled them, so they pass through as-is.
    assert diff_line_scope.unquote_diff_path('"scripts/café\\"x.py"') == 'scripts/café"x.py'


def test_unquote_diff_path_decodes_octal_run_as_one_character() -> None:
    # core.quotePath=true still octal-escapes non-ASCII; a multi-byte UTF-8
    # character spans several escapes and must decode as one unit.
    assert diff_line_scope.unquote_diff_path('"caf\\303\\251.py"') == "café.py"


def test_unquote_diff_path_replaces_undecodable_octal_byte() -> None:
    # A byte that is not valid UTF-8 must not raise: a lint gate may never
    # crash on a pathological filename.
    assert diff_line_scope.unquote_diff_path('"a\\377b.py"') == "a�b.py"


def test_unquote_diff_path_keeps_unknown_escape_literal() -> None:
    # ``\\x`` is not an escape git emits; keeping it literal is safer than
    # guessing at an encoding the gate cannot verify.
    assert diff_line_scope.unquote_diff_path('"a\\xffb.py"') == "a\\xffb.py"


def test_unquote_diff_path_keeps_trailing_lone_backslash() -> None:
    assert diff_line_scope.unquote_diff_path('"ab\\"') == "ab\\"


def test_unquote_diff_path_ignores_single_character_input() -> None:
    assert diff_line_scope.unquote_diff_path('"') == '"'


def test_parse_changed_lines_collects_added_span() -> None:
    diff = "+++ b/scripts/a.py\n@@ -0,0 +1,3 @@\n"

    assert diff_line_scope.parse_changed_lines(diff) == {"scripts/a.py": {1, 2, 3}}


def test_parse_changed_lines_treats_missing_count_as_one_line() -> None:
    diff = "+++ b/scripts/a.py\n@@ -4 +7 @@\n"

    assert diff_line_scope.parse_changed_lines(diff) == {"scripts/a.py": {7}}


def test_parse_changed_lines_ignores_deletion_only_hunk() -> None:
    # ``+9,0`` touches no post-image line. Recording line 9 would block on an
    # unchanged neighbor, the exact false positive issue #2993 is about.
    diff = "+++ b/scripts/a.py\n@@ -9,2 +9,0 @@\n"

    assert diff_line_scope.parse_changed_lines(diff) == {"scripts/a.py": set()}


def test_parse_changed_lines_keeps_pure_rename_absent() -> None:
    diff = (
        "diff --git a/old.py b/new.py\n"
        "similarity index 100%\n"
        "rename from old.py\n"
        "rename to new.py\n"
    )

    assert diff_line_scope.parse_changed_lines(diff) == {}


def test_parse_changed_lines_separates_multiple_files() -> None:
    diff = "+++ b/a.py\n@@ -1 +1 @@\n+++ b/b.py\n@@ -0,0 +5,2 @@\n"

    assert diff_line_scope.parse_changed_lines(diff) == {"a.py": {1}, "b.py": {5, 6}}


def test_parse_changed_lines_unquotes_file_header() -> None:
    diff = '+++ "b/scripts/od\\"d.py"\n@@ -0,0 +2,1 @@\n'

    assert diff_line_scope.parse_changed_lines(diff) == {'scripts/od"d.py': {2}}


def test_parse_changed_lines_ignores_hunk_before_any_file_header() -> None:
    assert diff_line_scope.parse_changed_lines("@@ -1 +1 @@\n") == {}


def test_changed_line_map_short_circuits_on_empty_paths(tmp_path: Path) -> None:
    assert diff_line_scope.changed_line_map("origin/main", tmp_path, []) == {}


def test_changed_line_map_returns_none_when_git_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        diff_line_scope,
        "git_diff_unified_zero",
        lambda *_args, **_kwargs: completed(128, stderr="fatal: bad revision\n"),
    )

    assert diff_line_scope.changed_line_map("missing", tmp_path, ["a.py"]) is None


def test_changed_line_map_parses_successful_diff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        diff_line_scope,
        "git_diff_unified_zero",
        lambda *_args, **_kwargs: completed(0, "+++ b/a.py\n@@ -0,0 +3,2 @@\n"),
    )

    assert diff_line_scope.changed_line_map("origin/main", tmp_path, ["a.py"]) == {"a.py": {3, 4}}


def test_git_diff_unified_zero_disables_path_quoting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return completed(0)

    monkeypatch.setattr(diff_line_scope.subprocess, "run", fake_run)
    diff_line_scope.git_diff_unified_zero("origin/main", tmp_path)

    assert "core.quotePath=false" in seen[0]
    assert "--unified=0" in seen[0]
    assert "--find-renames" in seen[0]
    # A pathspec would defeat rename detection; callers filter the parsed map.
    assert "--" not in seen[0]


def test_intersects_changed_lines_blocks_when_map_is_unresolved() -> None:
    assert diff_line_scope.intersects_changed_lines(None, "a.py", 1, 1) is True


def test_intersects_changed_lines_ignores_untouched_file() -> None:
    assert diff_line_scope.intersects_changed_lines({"b.py": {1}}, "a.py", 1, 1) is False


def test_intersects_changed_lines_ignores_file_with_empty_span() -> None:
    assert diff_line_scope.intersects_changed_lines({"a.py": set()}, "a.py", 1, 1) is False


def test_intersects_changed_lines_matches_row_inside_range() -> None:
    assert diff_line_scope.intersects_changed_lines({"a.py": {5}}, "a.py", 3, 7) is True


def test_intersects_changed_lines_rejects_row_outside_range() -> None:
    assert diff_line_scope.intersects_changed_lines({"a.py": {9}}, "a.py", 3, 7) is False


def test_intersects_changed_lines_tolerates_reversed_rows() -> None:
    assert diff_line_scope.intersects_changed_lines({"a.py": {5}}, "a.py", 7, 3) is True


def test_intersects_changed_lines_normalizes_reported_path() -> None:
    assert diff_line_scope.intersects_changed_lines({"a/b.py": {2}}, "./a\\b.py", 2, 2) is True


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(repo),
        },
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "--initial-branch=main", ".")
    return tmp_path


def test_real_git_pure_rename_contributes_no_lines(repo: Path) -> None:
    # Regression: a pathspec drops the delete half of the rename pair, so git
    # reports a full-file add and every latent finding in the file blocks.
    (repo / "old.py").write_text("a\nb\nc\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "one")
    git(repo, "mv", "old.py", "new.py")
    git(repo, "commit", "-qam", "two")

    assert diff_line_scope.changed_line_map("HEAD~1", repo, ["new.py"]) == {}


def test_real_git_quoted_path_maps_to_the_reported_name(repo: Path) -> None:
    # Regression: git quotes the ``b/`` prefix inside the quotes, so stripping
    # the prefix before unquoting leaves ``b/`` embedded in the map key.
    name = 'od"d.py'
    (repo / name).write_text("a\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "one")
    (repo / name).write_text("a\nb\n", encoding="utf-8")
    git(repo, "commit", "-qam", "two")

    assert diff_line_scope.changed_line_map("HEAD~1", repo, [name]) == {name: {2}}


def test_real_git_modified_line_lands_in_the_map(repo: Path) -> None:
    (repo / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "one")
    (repo / "a.py").write_text("one\nTWO\nthree\n", encoding="utf-8")
    git(repo, "commit", "-qam", "two")

    assert diff_line_scope.changed_line_map("HEAD~1", repo, ["a.py"]) == {"a.py": {2}}


def test_real_git_filters_out_paths_the_caller_did_not_ask_for(repo: Path) -> None:
    (repo / "a.py").write_text("one\n", encoding="utf-8")
    (repo / "b.py").write_text("one\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "one")
    (repo / "a.py").write_text("two\n", encoding="utf-8")
    (repo / "b.py").write_text("two\n", encoding="utf-8")
    git(repo, "commit", "-qam", "two")

    assert diff_line_scope.changed_line_map("HEAD~1", repo, ["a.py"]) == {"a.py": {1}}
