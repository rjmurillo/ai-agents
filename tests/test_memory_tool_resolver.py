"""rg and grep resolution skips relative PATH entries and the repository (issue #7493).

Portable: an explicit PATH value, a planted executable, and the ``windows``
switch stand in for a Windows host.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memory_enhancement import search
from memory_enhancement.tool_resolver import resolve_tool


def _plant(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    repo = tmp_path / "repo"
    work = tmp_path / "work"
    outside = tmp_path / "outside" / "bin"
    repo.mkdir()
    work.mkdir()
    monkeypatch.chdir(work)
    return {"repo": repo, "work": work, "outside": outside}


def test_an_absolute_entry_outside_the_repository_is_accepted(layout) -> None:
    planted = _plant(layout["outside"], "rg")

    found = resolve_tool("rg", [layout["repo"]], path_value=str(layout["outside"]))

    assert found == str(planted)


def test_an_absolute_entry_inside_the_repository_is_rejected(layout) -> None:
    _plant(layout["repo"] / "tools", "rg")

    found = resolve_tool("rg", [layout["repo"]], path_value=str(layout["repo"] / "tools"))

    assert found is None


def test_a_cwd_above_the_tool_directory_does_not_hide_the_tool(
    layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A user who launches from $HOME keeps ~/.cargo/bin/rg. Refusing hits under
    # the cwd turned recall off for every such user.
    planted = _plant(layout["outside"], "rg")
    monkeypatch.chdir(layout["outside"].parent.parent)

    found = resolve_tool("rg", [layout["repo"]], path_value=str(layout["outside"]))

    assert found == str(planted)


def test_a_refused_candidate_prints_one_recall_note(
    layout, capsys: pytest.CaptureFixture[str]
) -> None:
    planted = _plant(layout["repo"] / "tools", "rg")

    assert resolve_tool("rg", [layout["repo"]], path_value=str(planted.parent)) is None

    assert (
        f"memory-recall: ignoring {planted}: it is inside the repository" in capsys.readouterr().err
    )


def test_a_rejected_entry_does_not_hide_a_later_good_one(layout) -> None:
    _plant(layout["repo"] / "tools", "rg")
    good = _plant(layout["outside"], "rg")
    path_value = os.pathsep.join([str(layout["repo"] / "tools"), str(layout["outside"])])

    assert resolve_tool("rg", [layout["repo"]], path_value=path_value) == str(good)


def test_a_symlink_into_the_repository_is_rejected_by_its_resolved_path(layout) -> None:
    target = _plant(layout["repo"] / "tools", "real-rg")
    link_dir = layout["outside"]
    link_dir.mkdir(parents=True)
    try:
        (link_dir / "rg").symlink_to(target)
    except OSError as exc:  # pragma: no cover - Windows without developer mode
        pytest.skip(f"symlinks unavailable: {exc}")

    assert resolve_tool("rg", [layout["repo"]], path_value=str(link_dir)) is None


@pytest.mark.parametrize("entry", ["", ".", "bin", "./bin", "../bin"])
def test_empty_dot_and_relative_entries_are_skipped(layout, entry: str) -> None:
    """The planted binary is reachable from the cwd through every relative form."""
    _plant(layout["work"] / "bin", "rg")
    _plant(layout["work"], "rg")

    assert resolve_tool("rg", [], path_value=entry) is None


def test_the_process_path_is_used_when_no_value_is_given(
    layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    planted = _plant(layout["outside"], "rg")
    monkeypatch.setenv("PATH", str(layout["outside"]))

    assert resolve_tool("rg", [layout["repo"]]) == str(planted)


def test_windows_applies_pathext_to_an_absolute_entry(layout) -> None:
    planted = _plant(layout["outside"], "rg.exe")

    found = resolve_tool(
        "rg", [layout["repo"]], path_value=str(layout["outside"]), pathext=".EXE;.CMD", windows=True
    )

    assert found == str(planted)


def test_windows_without_pathext_match_finds_nothing(layout) -> None:
    _plant(layout["outside"], "rg")

    assert (
        resolve_tool(
            "rg", [layout["repo"]], path_value=str(layout["outside"]), pathext=".EXE", windows=True
        )
        is None
    )


def test_windows_cwd_binary_is_not_chosen_ahead_of_path(layout) -> None:
    """``shutil.which`` on Windows tries the cwd first. This resolver never does."""
    _plant(layout["work"], "rg.exe")
    good = _plant(layout["outside"], "rg.exe")

    found = resolve_tool(
        "rg", [layout["repo"]], path_value=str(layout["outside"]), pathext=".EXE", windows=True
    )

    assert found == str(good)


def test_a_missing_tool_returns_none(layout) -> None:
    assert resolve_tool("rg", [layout["repo"]], path_value=str(layout["outside"])) is None


# --- the search wiring ---------------------------------------------------------


def test_search_passes_the_repository_and_memories_dir_as_forbidden_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list] = []

    def fake_resolve(name, roots=()):
        seen.append(list(roots))
        return None

    monkeypatch.setattr(search, "resolve_tool", fake_resolve)
    memories = tmp_path / ".serena" / "memories"
    memories.mkdir(parents=True)

    search._search_with_ripgrep("gateway", memories, None, tmp_path)

    assert seen == [[tmp_path, memories]]


def test_search_returns_no_results_when_neither_tool_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There is no pure-Python search path. No tool means no recall, and no subprocess."""
    memories = tmp_path / ".serena" / "memories"
    memories.mkdir(parents=True)
    (memories / "gateway-cutover.md").write_text("# Gateway cutover\n\ngateway\n", encoding="utf-8")
    monkeypatch.setattr(search, "resolve_tool", lambda name, roots=(): None)
    run = MagicMock()
    monkeypatch.setattr(subprocess, "run", run)

    assert search.search_memories("gateway", memories, repo_root=tmp_path) == []
    run.assert_not_called()
