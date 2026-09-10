"""Contract and drift tests for the narrowed Windows marker run (issue #5380).

The narrowing is only safe while it selects exactly what a whole-tree
`pytest -m windows_path` selects. `test_narrowed_collection_matches_whole_tree`
is that proof and is deliberately expensive: it is the one check that catches a
marker applied to a module that never spells `windows_path`, which is the only
way textual discovery can under-select.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import run_pytest_windows as _rpw

REPO_ROOT = Path(__file__).resolve().parents[2]

# pytest's own addopts carry -v, which turns --collect-only into a tree render
# with no node IDs. Replacing addopts wholesale is what makes -q emit them.
_COLLECT_BASE = [
    sys.executable,
    "-m",
    "pytest",
    "-o",
    "addopts=--import-mode=importlib",
    "-p",
    "no:cacheprovider",
    "--collect-only",
    "-q",
    "--no-header",
    "-m",
    _rpw.MARKER,
]


def _collect(extra: list[str]) -> set[str]:
    """Node IDs `pytest -m windows_path` collects for ``extra`` arguments."""
    result = subprocess.run(
        [*_COLLECT_BASE, *extra],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {line.strip() for line in result.stdout.splitlines() if "::" in line}


def test_marked_files_returns_repo_relative_test_modules() -> None:
    files = _rpw.marked_files(REPO_ROOT)

    assert files, "the repository has windows_path tests, so discovery must find them"
    for rel in files:
        assert rel.startswith("tests/")
        assert Path(rel).name.startswith("test_")
        assert (REPO_ROOT / rel).is_file()
    assert files == sorted(files), "order must be deterministic for a reproducible command"


def test_marked_files_skips_a_module_that_does_not_name_the_marker(tmp_path: Path) -> None:
    tests_dir = tmp_path / _rpw.TESTS_DIR / "nested"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_marked.py").write_text(
        f"import pytest\npytestmark = pytest.mark.{_rpw.MARKER}\n", encoding="utf-8"
    )
    (tests_dir / "test_plain.py").write_text("def test_x() -> None:\n    pass\n", encoding="utf-8")
    (tests_dir / "helper_marked.py").write_text(_rpw.MARKER, encoding="utf-8")

    assert _rpw.marked_files(tmp_path) == [f"{_rpw.TESTS_DIR}/nested/test_marked.py"]


def test_narrowed_collection_matches_whole_tree(tmp_path: Path) -> None:
    """The drift gate: textual discovery must select the whole-tree node IDs.

    A marker reaching a module that never spells `windows_path`, through a
    conftest hook or an aliased mark, would be dropped from the only job that
    runs Windows path contracts. Nothing cheaper than collecting both ways can
    see that, so this test collects both ways.
    """
    whole_tree = _collect([])
    narrowed = _collect(_rpw.marked_files(REPO_ROOT))

    assert whole_tree, "whole-tree collection produced no windows_path node IDs"
    missing = whole_tree - narrowed
    assert not missing, (
        f"{len(missing)} windows_path test(s) are invisible to textual discovery, "
        f"so the Windows job would not run them: {sorted(missing)[:5]}"
    )
    assert narrowed == whole_tree


def test_main_exits_config_when_no_module_names_the_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A discovery that finds nothing must fail, never run zero tests green."""
    monkeypatch.setattr(_rpw, "marked_files", lambda _root: [])

    assert _rpw.main([]) == _rpw.EXIT_CONFIG


def test_main_returns_external_when_pytest_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_rpw, "marked_files", lambda _root: ["tests/test_x.py"])
    monkeypatch.setattr(
        _rpw.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no exec"))
    )

    assert _rpw.main([]) == _rpw.EXIT_EXTERNAL


def test_main_passes_the_marker_extra_args_and_files_to_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(_rpw, "marked_files", lambda _root: ["tests/test_x.py"])
    monkeypatch.setattr(_rpw.subprocess, "run", fake_run)

    assert _rpw.main(["-v"]) == 1
    command = captured["command"]
    assert command[-1] == "tests/test_x.py"
    marker_flag = command.index("pytest") + 1
    assert command[marker_flag : marker_flag + 2] == ["-m", _rpw.MARKER]
    assert "-v" in command
