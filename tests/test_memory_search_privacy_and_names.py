"""Recall search keeps prompt terms out of argv and finds filename-only matches (issue #7493)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from memory_enhancement import search


def _memories(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    directory = tmp_path / ".serena" / "memories"
    directory.mkdir(parents=True)
    return directory


@pytest.mark.parametrize("searcher", [search._search_with_ripgrep, search._search_with_grep])
def test_prompt_terms_go_through_stdin_not_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, searcher
) -> None:
    directory = _memories(tmp_path)
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["input"] = cmd, kwargs.get("input")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    monkeypatch.setattr(search, "resolve_tool", lambda name, _roots: f"/usr/bin/{name}")
    monkeypatch.setattr(search.subprocess, "run", fake_run)

    searcher("secretterm otherterm", directory)

    assert not any("secretterm" in part or "otherterm" in part for part in seen["cmd"])
    assert seen["input"] == "secretterm\notherterm\n"
    assert "-f" in seen["cmd"] and "-e" not in seen["cmd"]


def test_a_memory_named_only_by_its_filename_is_recalled(tmp_path: Path) -> None:
    directory = _memories(tmp_path)
    (directory / "database-cutover.md").write_text(
        "# Notes\n\nSet the connection pool to 10.\n", encoding="utf-8"
    )

    results = search.search_memories("database cutover", directory, repo_root=tmp_path)

    assert [r.memory_id for r in results] == ["database-cutover"]


def test_control_content_without_a_name_match_is_not_added(tmp_path: Path) -> None:
    directory = _memories(tmp_path)
    (directory / "pool-settings.md").write_text(
        "# Notes\n\nSet the connection pool to 10.\n", encoding="utf-8"
    )

    assert search.search_memories("database cutover", directory, repo_root=tmp_path) == []


def test_a_name_match_outside_the_memories_dir_is_dropped(tmp_path: Path) -> None:
    directory = _memories(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "database-cutover.md").write_text("# Notes\n\nOutside.\n", encoding="utf-8")
    (directory / "linked").symlink_to(outside, target_is_directory=True)

    results = search.search_memories("database cutover", directory, repo_root=tmp_path)

    assert results == []


def _ranked_paths(monkeypatch: pytest.MonkeyPatch) -> list[list[Path]]:
    seen: list[list[Path]] = []
    real_rank = search.rank_results

    def spy_rank(paths, *args, **kwargs):
        seen.append(list(paths))
        return real_rank(paths, *args, **kwargs)

    monkeypatch.setattr(search, "rank_results", spy_rank)
    return seen


def test_the_name_scan_stops_at_half_the_budget_and_keeps_content_hits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _memories(tmp_path)
    (directory / "notes.md").write_text("# Notes\n\nThe database cutover runs at night.\n")
    late = directory / "z-late"
    late.mkdir()
    (late / "database-cutover.md").write_text("# Late\n\nNothing here.\n", encoding="utf-8")
    clock = {"now": 1000.0}
    real_scandir = search.os.scandir

    def slow_scandir(path):
        clock["now"] += 3.0
        return real_scandir(path)

    monkeypatch.setattr(search.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(search.os, "scandir", slow_scandir)
    ranked = _ranked_paths(monkeypatch)

    results = search.search_memories(
        "database cutover", directory, repo_root=tmp_path, deadline=1010.0
    )

    assert not any(p.parent.name == "z-late" for p in ranked[0])
    assert [r.memory_id for r in results] == ["notes"]


def test_the_name_scan_stops_inside_one_large_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _memories(tmp_path)
    (directory / "notes.md").write_text("# Notes\n\nThe database cutover runs at night.\n")
    for index in range(20):
        (directory / f"database-cutover-{index:02d}.md").write_text("# Name\n\nNo terms.\n")
    clock = {"now": 1000.0}
    real_relevance = search.query_relevance

    def slow_relevance(query: str, label: str) -> float:
        clock["now"] += 1.0
        return real_relevance(query, label)

    monkeypatch.setattr(search.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(search, "query_relevance", slow_relevance)
    ranked = _ranked_paths(monkeypatch)

    results = search.search_memories(
        "database cutover", directory, repo_root=tmp_path, deadline=1010.0
    )

    named = [p for p in ranked[0] if p.name.startswith("database-cutover-")]
    assert 0 < len(named) <= 5
    assert "notes" in [r.memory_id for r in results]


def test_no_entry_is_read_after_the_cutoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _memories(tmp_path)
    (directory / "database-cutover.md").write_text("# Name\n\nNo terms.\n", encoding="utf-8")
    clock = {"now": 1000.0, "reads": 0}
    real_scandir = search.os.scandir

    class CountingEntries:
        def __init__(self, inner):
            self.inner = inner

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.inner.close()

        def __iter__(self):
            return self

        def __next__(self):
            clock["reads"] += 1
            return next(self.inner)

    def late_scandir(path):
        clock["now"] += 6.0
        return CountingEntries(real_scandir(path))

    monkeypatch.setattr(search.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(search.os, "scandir", late_scandir)

    search.search_memories("database cutover", directory, repo_root=tmp_path, deadline=1010.0)

    assert clock["reads"] == 0


def test_dot_entries_are_skipped_like_ripgrep(tmp_path: Path) -> None:
    directory = _memories(tmp_path)
    hidden = directory / ".obsidian"
    hidden.mkdir()
    (hidden / "gamma-notes.md").write_text("# Hidden\n\nNothing.\n", encoding="utf-8")
    (directory / ".gamma-notes.md").write_text("# Hidden\n\nNothing.\n", encoding="utf-8")

    assert search.search_memories("gamma notes", directory, repo_root=tmp_path) == []


def test_a_path_that_cannot_resolve_does_not_stop_recall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _memories(tmp_path)
    (directory / "notes.md").write_text("# Notes\n\nThe gamma rollout.\n", encoding="utf-8")
    (directory / "sub").mkdir()
    (directory / "sub" / "gamma-loop.md").write_text("# Loop\n\nNothing.\n", encoding="utf-8")
    real_resolve = Path.resolve

    def looping_resolve(self, *args, **kwargs):
        if self.name == "gamma-loop.md":
            raise RuntimeError("Symlink loop")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", looping_resolve)

    results = search.search_memories("gamma", directory, repo_root=tmp_path)

    assert [r.memory_id for r in results] == ["notes"]


def test_real_grep_reads_patterns_from_stdin(tmp_path: Path) -> None:
    directory = _memories(tmp_path)
    (directory / "alpha.md").write_text("# A\n\nThe gateway moved.\n", encoding="utf-8")
    (directory / "beta.md").write_text("# B\n\nA cutover plan.\n", encoding="utf-8")
    (directory / "gamma.md").write_text("# C\n\nUnrelated.\n", encoding="utf-8")

    found = search._search_with_grep("gateway cutover", directory, repo_root=tmp_path)

    assert found is not None
    assert sorted(p.name for p in found) == ["alpha.md", "beta.md"]
