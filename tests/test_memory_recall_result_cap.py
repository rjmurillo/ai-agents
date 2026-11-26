"""The prompt hook recalls at most one memory per prompt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from memory_enhancement import search
from memory_enhancement.hooks import user_prompt_submit_memory as hook

_NAMES = ("gateway-cutover", "gateway-cutover-rollback")


@pytest.fixture
def memories(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    directory = tmp_path / ".serena" / "memories"
    directory.mkdir(parents=True)
    for name in _NAMES:
        (directory / f"{name}.md").write_text(f"# {name}\n\nMove a service.\n", encoding="utf-8")
    return directory


def test_recall_requests_and_injects_one_result(
    memories: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    requested: list[object] = []
    real = search.search_memories

    def spy(*args: Any, **kwargs: Any) -> Any:
        requested.append(kwargs.get("max_results"))
        return real(*args, **kwargs)

    monkeypatch.setattr(search, "search_memories", spy)

    out = hook.recall_block("gateway cutover")

    assert hook._MAX_RECALL_RESULTS == 1
    assert requested == [1]
    assert out.count("\n### ") == 1


def test_control_both_memories_match_without_the_result_cap(memories: Path, tmp_path: Path) -> None:
    results = search.search_memories(
        "gateway cutover", memories, repo_root=tmp_path, min_relevance=hook._MIN_RELEVANCE
    )

    assert sorted(result.memory_id for result in results) == sorted(_NAMES)
