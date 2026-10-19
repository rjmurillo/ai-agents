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


# Whole-tree collection measured at 26.70s on a 4-CPU container and narrowed
# collection at 1.67s. This bound is roughly 10x the slower of the two, so it
# reports a hung collect rather than sitting until the job's own cap, and has
# enough headroom that a loaded runner does not trip it.
_COLLECT_TIMEOUT_SECONDS = 300


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
        timeout=_COLLECT_TIMEOUT_SECONDS,
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


def test_marked_files_raises_when_a_module_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable module must not be skipped into a smaller passing run."""
    tests_dir = tmp_path / _rpw.TESTS_DIR
    tests_dir.mkdir()
    unreadable = tests_dir / "test_unreadable.py"
    unreadable.write_text("x = 1\n", encoding="utf-8")

    def boom(self: Path, *_args: object, **_kwargs: object) -> str:
        if self == unreadable:
            raise OSError("permission denied")
        return ""

    monkeypatch.setattr(Path, "read_text", boom)

    with pytest.raises(_rpw.DiscoveryError) as excinfo:
        _rpw.marked_files(tmp_path)
    assert "test_unreadable.py" in str(excinfo.value)


def test_main_exits_external_when_discovery_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_root: Path) -> list[str]:
        raise _rpw.DiscoveryError("could not read tests/test_x.py: permission denied")

    monkeypatch.setattr(_rpw, "marked_files", boom)

    assert _rpw.main([]) == _rpw.EXIT_EXTERNAL


_DISCOVERED = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]


@pytest.mark.parametrize("raw", ["", "   ", "[]"])
def test_selected_files_runs_every_module_when_nothing_is_selected(raw: str) -> None:
    assert _rpw.selected_files(raw, _DISCOVERED) == _DISCOVERED


def test_selected_files_keeps_discovery_order_for_a_subset() -> None:
    raw = '["tests/test_c.py", "tests/test_a.py"]'

    assert _rpw.selected_files(raw, _DISCOVERED) == ["tests/test_a.py", "tests/test_c.py"]


@pytest.mark.parametrize(
    "raw", ["not json", "{}", '"tests/test_a.py"', "[1]", '["tests/test_a.py", 2]']
)
def test_selected_files_rejects_a_malformed_selection(raw: str) -> None:
    with pytest.raises(_rpw.SelectionError):
        _rpw.selected_files(raw, _DISCOVERED)


def test_selected_files_rejects_a_module_that_is_not_marked() -> None:
    """A stale name must fail the run, not shrink the suite unseen."""
    with pytest.raises(_rpw.SelectionError, match="tests/test_gone.py"):
        _rpw.selected_files('["tests/test_a.py", "tests/test_gone.py"]', _DISCOVERED)


def test_main_hands_pytest_only_the_selected_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(_rpw, "marked_files", lambda _root: _DISCOVERED)
    monkeypatch.setattr(_rpw.subprocess, "run", fake_run)
    monkeypatch.setenv(_rpw.ENV_SELECTED, '["tests/test_b.py"]')

    assert _rpw.main([]) == 0
    assert captured["command"][-1:] == ["tests/test_b.py"]
    assert "tests/test_a.py" not in captured["command"]


def test_main_runs_every_module_when_the_selection_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(_rpw, "marked_files", lambda _root: _DISCOVERED)
    monkeypatch.setattr(_rpw.subprocess, "run", fake_run)
    monkeypatch.delenv(_rpw.ENV_SELECTED, raising=False)

    assert _rpw.main([]) == 0
    assert captured["command"][-3:] == _DISCOVERED


def test_main_exits_config_on_a_stale_selection_without_starting_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pytest must not start on a bad selection")

    monkeypatch.setattr(_rpw, "marked_files", lambda _root: _DISCOVERED)
    monkeypatch.setattr(_rpw.subprocess, "run", fail_run)
    monkeypatch.setenv(_rpw.ENV_SELECTED, '["tests/test_gone.py"]')

    assert _rpw.main([]) == _rpw.EXIT_CONFIG


def _fake_project(root: Path) -> None:
    """A tree with one module that only names the marker and one that applies it."""
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_names_only.py").write_text(
        "def test_detects_windows_path() -> None:\n    pass\n", encoding="utf-8"
    )
    (tests_dir / "test_applies.py").write_text(
        "import pytest\n\n\n@pytest.mark.windows_path\ndef test_marked() -> None:\n    pass\n",
        encoding="utf-8",
    )


def test_narrowed_run_that_selects_no_item_passes_under_real_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A change that reaches only a zero-hit module must not turn the job red (exit 5)."""
    _fake_project(tmp_path)
    monkeypatch.setattr(_rpw, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv(_rpw.ENV_SELECTED, '["tests/test_names_only.py"]')

    assert _rpw.main(["-p", "no:cacheprovider"]) == _rpw.EXIT_OK


def test_whole_run_that_selects_no_item_still_fails_under_real_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no narrowing, zero selected items means the marker suite vanished."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_names_only.py").write_text(
        "def test_detects_windows_path() -> None:\n    pass\n", encoding="utf-8"
    )
    monkeypatch.setattr(_rpw, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv(_rpw.ENV_SELECTED, raising=False)

    assert _rpw.main(["-p", "no:cacheprovider"]) == _rpw.PYTEST_NO_TESTS


def test_narrowed_run_with_a_failing_test_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_project(tmp_path)
    (tmp_path / "tests" / "test_applies.py").write_text(
        "import pytest\n\n\n"
        "@pytest.mark.windows_path\n"
        "def test_marked() -> None:\n    assert False\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_rpw, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv(_rpw.ENV_SELECTED, '["tests/test_applies.py"]')

    assert _rpw.main(["-p", "no:cacheprovider"]) == 1


def test_narrowed_zero_item_run_prints_a_warning_naming_the_modules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Issue #6506: a green job that ran zero tests must say so."""
    _fake_project(tmp_path)
    monkeypatch.setattr(_rpw, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv(_rpw.ENV_SELECTED, '["tests/test_names_only.py"]')

    assert _rpw.main(["-p", "no:cacheprovider"]) == _rpw.EXIT_OK

    err = capsys.readouterr().err
    assert "::warning::windows_path run collected 0 items from 1 selected module(s)" in err
    assert "tests/test_names_only.py" in err


def test_narrowed_run_that_collects_items_prints_no_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _fake_project(tmp_path)
    monkeypatch.setattr(_rpw, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv(_rpw.ENV_SELECTED, '["tests/test_applies.py"]')

    assert _rpw.main(["-p", "no:cacheprovider"]) == _rpw.EXIT_OK

    assert "::warning::" not in capsys.readouterr().err


def test_whole_run_with_zero_items_prints_no_warning_and_still_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(_rpw, "marked_files", lambda _root: _DISCOVERED)
    monkeypatch.setattr(
        _rpw.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, _rpw.PYTEST_NO_TESTS),
    )
    monkeypatch.delenv(_rpw.ENV_SELECTED, raising=False)

    assert _rpw.main([]) == _rpw.PYTEST_NO_TESTS
    assert "::warning::" not in capsys.readouterr().err


def test_zero_collected_warning_truncates_a_long_module_list() -> None:
    modules = [f"tests/test_{n}.py" for n in range(8)]

    warning = _rpw.zero_collected_warning(modules)

    assert "from 8 selected module(s)" in warning
    assert "(+3 more)" in warning
    assert "tests/test_7.py" not in warning


def test_narrowed_exit_code_maps_only_no_tests_to_ok() -> None:
    assert _rpw.exit_code(_rpw.PYTEST_NO_TESTS, narrowed=True) == _rpw.EXIT_OK
    assert _rpw.exit_code(_rpw.PYTEST_NO_TESTS, narrowed=False) == _rpw.PYTEST_NO_TESTS
    assert _rpw.exit_code(1, narrowed=True) == 1
    assert _rpw.exit_code(0, narrowed=True) == 0
