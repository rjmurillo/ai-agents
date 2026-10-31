"""A file `windows_path_filter` cannot read or parse fails closed (issue #6506).

Returning an empty reference set for a broken transitive file under-selected the
Windows runner with no signal. The failure now raises `ReachError`, which the
`emit` command turns into the match-everything fallback key.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.ci import windows_path_filter as wpf


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _tree(root: Path, files: dict[str, str]) -> wpf.Inventory:
    for rel, text in files.items():
        _write(root, rel, text)
    return wpf.Inventory(files)


def test_unparseable_module_raises_and_names_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"tests/test_a.py": "import broken\n", "lib/broken.py": "def (:\n"}
    inventory = _tree(tmp_path, files)

    with pytest.raises(wpf.ReachError, match="lib/broken.py"):
        wpf.reach(tmp_path, "tests/test_a.py", inventory)

    assert "lib/broken.py" in capsys.readouterr().err


def test_unreadable_module_raises_and_names_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory = wpf.Inventory(["tests/test_a.py"])

    with pytest.raises(wpf.ReachError, match="tests/test_a.py"):
        wpf.reach(tmp_path, "tests/test_a.py", inventory)

    assert "tests/test_a.py" in capsys.readouterr().err


def test_parseable_modules_still_resolve(tmp_path: Path) -> None:
    inventory = _tree(tmp_path, {"tests/test_a.py": "import ok\n", "lib/ok.py": "x = 1\n"})

    assert wpf.reach(tmp_path, "tests/test_a.py", inventory) == {"tests/test_a.py", "lib/ok.py"}


def test_emit_writes_the_match_everything_key_when_reach_error_is_injected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_root: Path, _files: object = None) -> dict[str, list[str]]:
        raise wpf.ReachError("could not read or parse lib/broken.py")

    monkeypatch.setattr(wpf, "filter_patterns", boom)
    out = tmp_path / "filter.yml"

    code = wpf.main(["--repo-root", str(tmp_path), "emit", "--output", str(out)])

    assert code == wpf.EXIT_OK
    assert yaml.safe_load(out.read_text(encoding="utf-8")) == {wpf.FALLBACK_KEY: ["**"]}
