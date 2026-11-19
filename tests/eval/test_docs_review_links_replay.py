"""Protect replay scoring and changed-line selection from false passing results."""

from pathlib import Path

import pytest

from scripts.eval import docs_review_links_replay as replay


@pytest.mark.parametrize(
    ("file", "kind", "line", "caught"),
    [
        ("docs/a.md", "missing-target", 7, True),
        ("docs/a.md", "missing-target", 13, True),
        ("docs/a.md", "missing-target", 14, False),
        ("docs/b.md", "missing-target", 10, False),
        ("docs/a.md", "missing-anchor", 10, False),
    ],
)
def test_match_requires_path_class_and_line_window(
    file: str, kind: str, line: int, caught: bool
) -> None:
    expected = {"file": "docs/a.md", "defect_class": "missing-target", "line": 10}
    actual = [{"file": file, "defect_class": kind, "line": line}]

    assert replay.matched(expected, actual) is caught


def test_changed_lines_reads_every_hunk_and_skips_deletions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_git(*args: str, **kwargs: object) -> str:
        if "--name-only" in args:
            return "docs/a.md\0src/example.py\0"
        return (
            "diff --git a/docs/a.md b/docs/a.md\n"
            "@@ -2,0 +3,2 @@\n+one\n+two\n"
            "@@ -10 +12 @@\n-old\n+new\n"
            "@@ -20 +21,0 @@\n-deleted\n"
        )

    monkeypatch.setattr(replay, "git", fake_git)

    assert replay.changed_lines(tmp_path, "base") == {"docs/a.md": {3, 4, 12}}


def test_match_cannot_reuse_a_different_target_at_the_same_line() -> None:
    expected = {
        "file": "docs/a.md",
        "defect_class": "missing-target",
        "line": 10,
        "target": "wanted.md",
    }
    actual = [{**expected, "target": "different.md"}]

    assert not replay.matched(expected, actual)
