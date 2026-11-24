"""Linked memories stay inside their store, on every reader (ADR-126).

A committed symlink such as ``notes/x.md -> ../../.env`` resolves inside the
repository but outside the store. Every reader must refuse it, so no memory
search or recall can surface another repository file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_enhancement import search
from memory_enhancement.hooks import session_end_memory
from memory_enhancement.hooks import user_prompt_submit_memory as recall_hook
from memory_enhancement.serena_integration import load_memory

SCRIPTS = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent))

import search_memory
from memory_core import memory_router

NOTES = Path(".project-toolkit", "memory", "notes")


def _repo_with_links(tmp_path: Path) -> Path:
    """A repo whose notes store holds one real note, one in-store link, one .env link."""
    repo = tmp_path / "repo"
    notes = repo / NOTES
    notes.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".env").write_text("# Secret\n\nSECRET-VALUE retry\n", encoding="utf-8")
    (notes / "retry-real.md").write_text("# Retry\n\nRetry policy.\n", encoding="utf-8")
    try:
        (notes / "retry-alias.md").symlink_to(notes / "retry-real.md")
        (notes / "retry-env.md").symlink_to(repo / ".env")
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    return repo


def test_search_script_refuses_a_link_to_a_repository_file(tmp_path: Path) -> None:
    repo = _repo_with_links(tmp_path)

    names = {p.name for p in search_memory._corpus_files(repo / NOTES)}

    assert names == {"retry-real.md", "retry-alias.md"}


def test_router_refuses_a_link_to_a_repository_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_with_links(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    memory_router.reset_caches()

    results = memory_router.search_memory("retry")

    assert {r.name for r in results} == {"retry-real", "retry-alias"}
    assert all("SECRET-VALUE" not in (r.content or "") for r in results)


@pytest.mark.parametrize(("name", "loads"), [("retry-alias.md", True), ("retry-env.md", False)])
def test_loader_bounds_links_to_the_store(tmp_path: Path, name: str, loads: bool) -> None:
    repo = _repo_with_links(tmp_path)

    loaded = load_memory(repo / NOTES / name, repo / NOTES)

    assert (loaded is not None) is loads


def test_ripgrep_failure_reports_the_grep_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(search, "resolve_tool", lambda name, roots: f"/usr/bin/{name}")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=2, stdout="", stderr="rg: unreadable file"),
    )

    assert search._search_with_ripgrep("retry policy", tmp_path) is None

    err = capsys.readouterr().err
    assert "rg exited 2; falling back to grep" in err
    assert "recall skipped" not in err


def test_session_end_starts_from_the_project_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".serena" / "memories").mkdir(parents=True)
    (project / NOTES).mkdir(parents=True)
    (project / NOTES / "old.md").write_text("# Old\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / ".git").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.chdir(elsewhere)

    assert session_end_memory.main() == 0

    assert "git mv .project-toolkit/memory/notes/* .serena/memories/" in capsys.readouterr().err


def test_recall_fails_open_when_store_resolution_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_links(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))

    def _boom(root: Path) -> Path:
        raise OSError("resolve failed")

    monkeypatch.setattr("memory_enhancement.stores.repository_memory_dir", _boom)

    block = recall_hook.recall_block("what is the retry policy here")

    assert block == ""
    assert "memory recall failed: OSError: resolve failed" in capsys.readouterr().err


def test_search_script_skips_the_env_link_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_links(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))

    assert search_memory.main(["retry"]) == 0

    out = json.loads(capsys.readouterr().out)
    assert all("SECRET-VALUE" not in r.get("Content", "") for r in out["Results"])
    assert {r["Name"] for r in out["Results"]} >= {"retry-real"}
