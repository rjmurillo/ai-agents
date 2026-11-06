"""Remote-deleting push forms that the sink scan must report (issue #6506)."""

from __future__ import annotations

from pathlib import Path

import pytest
import sink_scan


def _labels(tmp_path: Path, source: str) -> list[str]:
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    report = sink_scan.scan([tmp_path], tmp_path, [])
    return [s["label"] for s in report["sinks"]]


@pytest.mark.parametrize(
    ("argv", "label"),
    [
        ("['push', '--delete', 'origin', 'topic']", "push --delete origin topic"),
        ("['push', 'origin', '--mirror']", "push origin --mirror"),
        ("['push', 'origin', ':topic']", "push origin :topic"),
    ],
)
def test_remote_deleting_push_argv_is_reported(tmp_path: Path, argv: str, label: str) -> None:
    assert label in _labels(tmp_path, f"def f(git):\n    git({argv})\n")


@pytest.mark.parametrize(
    "command",
    [
        "git push --delete origin topic",
        "git push origin --mirror",
        "git push origin :topic",
    ],
)
def test_remote_deleting_push_shell_text_is_reported(tmp_path: Path, command: str) -> None:
    labels = _labels(tmp_path, f"import os\ndef f():\n    os.system({command!r})\n")
    assert command in labels


def test_plain_push_and_url_colon_are_not_reported(tmp_path: Path) -> None:
    source = (
        "def f(git):\n"
        "    git(['push', 'origin', 'main'])\n"
        "    git(['push', 'https://example.com/r.git', 'main'])\n"
    )
    assert _labels(tmp_path, source) == []
