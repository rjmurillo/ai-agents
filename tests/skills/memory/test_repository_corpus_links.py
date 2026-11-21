"""Compatibility tests for linked repository memory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from memory_enhancement.hooks import repository_memory_dir
from memory_enhancement.serena_integration import load_memory

SCRIPTS = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from search_memory import main, search_serena


@pytest.mark.parametrize("inside_checkout", [True, False])
def test_search_keeps_only_local_default_corpus_links(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    inside_checkout: bool,
) -> None:
    repo = tmp_path / "checkout"
    legacy = repo / ".serena" / "memories"
    legacy.parent.mkdir(parents=True)
    target = (repo if inside_checkout else tmp_path) / "existing-corpus"
    target.mkdir()
    try:
        legacy.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    (target / "retry-legacy.md").write_text("Legacy retries.", encoding="utf-8")
    notes = repo / ".project-toolkit" / "memory" / "notes"
    notes.mkdir(parents=True)
    (notes / "retry-note.md").write_text("Fallback retries.", encoding="utf-8")
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(repo)

    assert repository_memory_dir(repo) == (target if inside_checkout else notes)
    assert main(["retry"]) == 0

    (result,) = json.loads(capsys.readouterr().out)["Results"]
    assert result["Name"] == ("retry-legacy" if inside_checkout else "retry-note")


@pytest.mark.parametrize("has_git", [True, False])
def test_search_keeps_links_inside_the_checkout(tmp_path: Path, has_git: bool) -> None:
    repo = tmp_path / "checkout"
    corpus = repo / ".serena" / "memories"
    corpus.mkdir(parents=True)
    if has_git:
        (repo / ".git").mkdir()
    internal = repo / "details.md"
    internal.write_text("Local evidence.", encoding="utf-8")
    external = tmp_path / "details.md"
    external.write_text("External evidence.", encoding="utf-8")
    try:
        (corpus / "retry-internal.md").symlink_to(internal)
        (corpus / "retry-external.md").symlink_to(external)
    except OSError as exc:
        pytest.skip(f"file symlinks unavailable: {exc}")

    (result,) = search_serena("retry", corpus, 10)
    assert result["Name"] == "retry-internal"


@pytest.mark.unit
@pytest.mark.parametrize("inside_checkout", [True, False])
@pytest.mark.parametrize("layout", ["git", "archive", "nested archive"])
def test_load_limits_note_symlinks_to_the_checkout(tmp_path, inside_checkout, layout):
    repo = tmp_path / "checkout"
    corpus = repo / ".serena" / "memories"
    corpus.mkdir(parents=True)
    if layout == "git":
        (repo / ".git").mkdir()
    if layout == "nested archive":
        (tmp_path / ".git").mkdir()
    target = (repo if inside_checkout else tmp_path) / "real-note.md"
    target.write_text("# Real note\n\nContent.\n", encoding="utf-8")
    link = corpus / "linked-note.md"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"file symlinks unavailable: {exc}")

    assert (load_memory(link, corpus) is not None) is inside_checkout
