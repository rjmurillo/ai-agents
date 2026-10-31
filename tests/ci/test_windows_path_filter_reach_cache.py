"""Pins that `windows_path_filter` parses each file once per emit (issue #5380).

The marked modules share most of their reach. Re-parsing a shared file for every
module tripled `test_windows_path_filter_repo.py`'s run time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import windows_path_filter as wpf


def test_a_file_shared_by_two_modules_is_parsed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        "tests/test_a.py": "import shared\nwindows_path = 1\n",
        "tests/test_b.py": "import shared\nwindows_path = 1\n",
        "lib/shared.py": "import leaf\n",
        "lib/leaf.py": "x = 1\n",
    }
    parsed: list[str] = []
    original = wpf._references

    def counting(path: str, repo_root: Path, inventory: wpf.Inventory) -> set[str]:
        parsed.append(path)
        return original(path, repo_root, inventory)

    monkeypatch.setattr(wpf, "_references", counting)

    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    patterns = wpf.filter_patterns(tmp_path, files)

    assert "lib/leaf.py" in patterns["tests/test_a.py"]
    assert "lib/leaf.py" in patterns["tests/test_b.py"]
    assert sorted(parsed) == sorted(files)
