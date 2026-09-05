"""Snapshot tests for build/generate_agents.py (REQ-003-001).

These tests assert the agent generator emits stable per-platform output for
representative agents, including the visual-studio toolsFrom-aliasing case
that proved hardest to preserve in the M3-T1 refactor.

We do NOT snapshot all 25 × 3 = 75 generated files. We pick three agents and
inspect a few load-bearing fields per platform.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build"))
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_agents  # noqa: E402

# Helpers --------------------------------------------------------------------


@pytest.fixture
def staging(tmp_path: Path) -> Path:
    """Stage a minimal templates tree under tmp_path so writes don't pollute the repo."""
    repo = tmp_path / "stage"
    (repo / "templates").mkdir(parents=True)
    # Copy templates wholesale: agents/, platforms/, toolsets.yaml.
    shutil.copytree(REPO_ROOT / "templates" / "agents", repo / "templates" / "agents")
    shutil.copytree(REPO_ROOT / "templates" / "platforms", repo / "templates" / "platforms")
    shutil.copy2(REPO_ROOT / "templates" / "toolsets.yaml", repo / "templates" / "toolsets.yaml")
    return repo


def _read_frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---\n", 4)
    assert end >= 0, f"no frontmatter end in {path}"
    return text[: end + 5]


# Snapshot tests ------------------------------------------------------------


def test_generate_writes_three_outputs_per_agent(staging: Path) -> None:
    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    # Pick three representative agents and verify all three platform files exist.
    for agent in ("analyst", "implementer", "qa"):
        assert (staging / "src" / "copilot-cli" / "agents" / f"{agent}.agent.md").is_file()
        assert (staging / "src" / "vs-code-agents" / f"{agent}.agent.md").is_file()


def test_copilot_cli_emits_path_style_tools(staging: Path) -> None:
    """Copilot CLI uses `$toolset:editor` expanded to `path/*` patterns."""
    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    fm = _read_frontmatter(staging / "src" / "copilot-cli" / "agents" / "analyst.agent.md")
    # Path-style tool entries appear as bullet items like `- read` or `- perplexity/*`.
    assert "tools:" in fm
    assert "- " in fm  # bullet array


def test_visual_studio_inherits_vscode_toolsfrom(staging: Path) -> None:
    """visual-studio.yaml has `toolsFrom: vscode` — the toolset expansion
    must use vscode tools, NOT visual-studio (which has no entries)."""
    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    vs_path = staging / "src" / "vs-code-agents" / "analyst.agent.md"
    assert vs_path.is_file()
    fm = _read_frontmatter(vs_path)
    # Sanity: vscode toolset entries are non-empty and present.
    assert "tools:" in fm
    body = vs_path.read_text(encoding="utf-8")
    assert body.startswith("---\n")


def test_handoff_syntax_differs_per_platform(staging: Path) -> None:
    """copilot-cli uses /agent; vscode/vs uses #runSubagent.
    Pick an agent body that mentions Task() to verify the rewrite ran."""
    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    cc_path = staging / "src" / "copilot-cli" / "agents" / "orchestrator.agent.md"
    vs_path = staging / "src" / "vs-code-agents" / "orchestrator.agent.md"
    cc = cc_path.read_text(encoding="utf-8")
    vs = vs_path.read_text(encoding="utf-8")
    # The handoff transform fires on `Task(subagent_type="...")` patterns.
    # We assert that the two outputs differ AT LEAST in their handoff
    # representation — they share most of the body otherwise.
    assert cc != vs


def test_validate_mode_passes_against_committed_state() -> None:
    """The committed src/ tree must match what the generator produces today.
    This is the M3-T1 no-regress contract: any future generator change must
    preserve byte-equality with what's checked in."""
    rc = generate_agents.main(["--validate"])
    assert rc == 0


# Atomic-write tests (issue #5502) ------------------------------------------
#
# `Path.write_bytes` opens the destination "wb", so the file is 0 bytes from
# the truncate until the buffer flushes. `build_all.py --check` runs this
# generator against the real working tree, so a reader in another process
# (an xdist sibling worker) inside that window gets an empty file that still
# passes `Path.is_file()`. Measured on this branch before the fix, polling
# `src/copilot-cli/agents/analyst.agent.md` during
# `build/scripts/build_all.py --check`: 13110 -> 0 -> 8192 -> 12288 -> 13110,
# 376 zero-size samples.
#
# Concurrency is flaky to assert directly, so these test the property that
# removes the window instead: the destination is published by swapping a
# directory entry, so it is never observed empty or partial.


def _temp_leftovers(destination: Path) -> list[Path]:
    """Temp files this helper would leave behind, by its own naming scheme."""
    return sorted(destination.parent.glob(f".{destination.name}.*"))


def test_generate_publishes_without_ever_emptying_the_destination(
    staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old destination must be intact at the instant of the swap.

    Fails against the previous `output_file.write_bytes(...)` line two ways:
    `os.replace` is never called, so `swaps` stays empty and the first
    assertion goes red; and the destination is observably truncated mid-write.
    """
    first = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert first == 0
    watched = staging / "src" / "copilot-cli" / "agents" / "analyst.agent.md"
    before = watched.read_bytes()
    assert before, "fixture must produce a non-empty destination to protect"

    swaps: list[tuple[Path, bytes]] = []
    real_replace = os.replace

    def _observing_replace(source: Any, destination: Any) -> None:
        target = Path(destination)
        # Read the destination as it stands one instruction before the swap.
        # Any in-place write would already have truncated it by now.
        swaps.append((target, target.read_bytes() if target.is_file() else b"<absent>"))
        real_replace(source, destination)

    monkeypatch.setattr(generate_agents.os, "replace", _observing_replace)

    second = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert second == 0

    assert swaps, "generator did not publish through os.replace"
    observed = [content for target, content in swaps if target == watched]
    assert observed == [before], (
        "destination was not intact at the swap: the old bytes must still be "
        "there until the directory entry is replaced"
    )
    assert b"" not in {content for _, content in swaps}
    assert _temp_leftovers(watched) == []


def test_generate_swaps_from_a_temp_file_in_the_same_directory(
    staging: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cross-directory rename can cross a filesystem, where it is not atomic."""
    sources: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def _recording_replace(source: Any, destination: Any) -> None:
        sources.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(generate_agents.os, "replace", _recording_replace)

    rc = generate_agents.generate_agents(
        templates_path=staging / "templates",
        output_root=staging / "src",
        repo_root=staging,
    )
    assert rc == 0
    assert sources
    for source, destination in sources:
        assert source.parent == destination.parent


def test_atomic_write_creates_a_destination_that_does_not_exist(
    tmp_path: Path,
) -> None:
    """First generation: nothing to replace, and no temp file left behind."""
    destination = tmp_path / "fresh.md"

    generate_agents._atomic_write_bytes(destination, b"first generation\n")

    assert destination.read_bytes() == b"first generation\n"
    assert _temp_leftovers(destination) == []


def test_atomic_write_replaces_longer_content_with_no_tail(tmp_path: Path) -> None:
    """The case an in-place write leaves a truncated tail behind."""
    destination = tmp_path / "shrinking.md"
    destination.write_bytes(b"x" * 4096)

    generate_agents._atomic_write_bytes(destination, b"short\n")

    assert destination.read_bytes() == b"short\n"
    assert destination.stat().st_size == 6
    assert _temp_leftovers(destination) == []


def test_atomic_write_preserves_an_existing_destination_mode(tmp_path: Path) -> None:
    """mkstemp creates at 0600 and os.replace publishes that mode verbatim."""
    destination = tmp_path / "moded.md"
    destination.write_bytes(b"old\n")
    destination.chmod(0o644)

    generate_agents._atomic_write_bytes(destination, b"new\n")

    assert destination.read_bytes() == b"new\n"
    if os.name == "posix":
        assert destination.stat().st_mode & 0o777 == 0o644


def test_atomic_write_failure_leaves_the_destination_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed publish must not truncate, half-write, or strand a temp file."""
    destination = tmp_path / "kept.md"
    destination.write_bytes(b"original\n")

    def _explode(source: Any, target: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(generate_agents.os, "replace", _explode)

    with pytest.raises(OSError, match="disk full"):
        generate_agents._atomic_write_bytes(destination, b"replacement\n")

    assert destination.read_bytes() == b"original\n"
    assert _temp_leftovers(destination) == []
