"""Tests for build/sync_slim_agents.py (Refs #5282).

The script copies an agent body from `.claude/agents/{name}.md` into three
hand-maintained mirrors, preserving each mirror's own frontmatter. Default mode
reports drift and exits non-zero; `--write` applies the copy.

Tests:
- Positive: matching bodies report zero drift and exit 0.
- Negative: a drifted body exits 1 and names the file.
- Negative: a declared agent missing from the source exits 2 (config).
- Negative: a declared agent missing from one mirror exits 2 (config).
- Positive: --write replaces the body and preserves each mirror's frontmatter.
- Edge: --write is idempotent; the second run reports zero changed files.
- Edge: a mirror with no frontmatter receives the body verbatim.
- Edge: non-ASCII bodies survive the round trip (explicit UTF-8 encoding).
- Edge: split_frontmatter handles absent and unterminated frontmatter.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "build" / "sync_slim_agents.py"

_spec = importlib.util.spec_from_file_location("sync_slim_agents", _SCRIPT)
assert _spec is not None and _spec.loader is not None
sync_slim_agents = importlib.util.module_from_spec(_spec)
sys.modules["sync_slim_agents"] = sync_slim_agents
_spec.loader.exec_module(sync_slim_agents)


AGENT = "analyst"
SOURCE_BODY = "# Analyst\n\nBody from the Claude tree.\n"
STALE_BODY = "# Analyst\n\nStale body.\n"

CLAUDE_FRONTMATTER = "---\nname: analyst\nmodel: sonnet\n---\n"
GITHUB_FRONTMATTER = "---\nname: analyst\ntools:\n  - read\n---\n"
TEMPLATE_FRONTMATTER = "---\nrole: support\ntools_vscode:\n  - read\n---\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a four-tree fixture and point the module at it."""
    claude_agents = tmp_path / ".claude" / "agents"
    src_claude = tmp_path / "src" / "claude"
    templates = tmp_path / "templates" / "agents"
    github_agents = tmp_path / ".github" / "agents"

    _write(claude_agents / f"{AGENT}.md", CLAUDE_FRONTMATTER + SOURCE_BODY)
    _write(src_claude / f"{AGENT}.md", CLAUDE_FRONTMATTER + SOURCE_BODY)
    _write(templates / f"{AGENT}.shared.md", TEMPLATE_FRONTMATTER + SOURCE_BODY)
    _write(github_agents / f"{AGENT}.agent.md", GITHUB_FRONTMATTER + SOURCE_BODY)

    destination = sync_slim_agents.Destination
    monkeypatch.setattr(sync_slim_agents, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sync_slim_agents, "CLAUDE_AGENTS", claude_agents)
    monkeypatch.setattr(
        sync_slim_agents,
        "DESTINATIONS",
        (
            destination("src/claude", src_claude, ".md"),
            destination("templates/agents", templates, ".shared.md"),
            destination(".github/agents", github_agents, ".agent.md"),
        ),
    )
    monkeypatch.setattr(sync_slim_agents, "SLIMMED_AGENTS", (AGENT,))
    return tmp_path


def test_check_reports_no_drift_when_bodies_match(tree: Path, capsys) -> None:
    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_OK
    assert "drifted: 0 of 3 destination files" in capsys.readouterr().out


def test_check_exits_nonzero_and_names_the_drifted_file(tree: Path, capsys) -> None:
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_DRIFT

    out = capsys.readouterr().out
    assert "drifted: 1 of 3 destination files" in out
    assert "templates/agents/analyst.shared.md" in out


def test_check_does_not_mutate_the_drifted_file(tree: Path) -> None:
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, TEMPLATE_FRONTMATTER + STALE_BODY)

    sync_slim_agents.main([])

    assert target.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + STALE_BODY


def test_missing_source_agent_is_a_config_error(tree: Path, capsys) -> None:
    (tree / ".claude" / "agents" / f"{AGENT}.md").unlink()

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_CONFIG

    err = capsys.readouterr().err
    assert ".claude/agents/analyst.md" in err
    assert "Refusing to sync a partial set." in err


def test_missing_mirror_file_is_a_config_error(tree: Path, capsys) -> None:
    (tree / ".github" / "agents" / f"{AGENT}.agent.md").unlink()

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_CONFIG
    assert ".github/agents/analyst.agent.md" in capsys.readouterr().err


def test_write_replaces_body_and_preserves_each_frontmatter(tree: Path) -> None:
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    github = tree / ".github" / "agents" / f"{AGENT}.agent.md"
    _write(template, TEMPLATE_FRONTMATTER + STALE_BODY)
    _write(github, GITHUB_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK

    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + SOURCE_BODY
    assert github.read_text(encoding="utf-8") == GITHUB_FRONTMATTER + SOURCE_BODY


def test_write_is_idempotent(tree: Path, capsys) -> None:
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)

    sync_slim_agents.main(["--write"])
    capsys.readouterr()

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK
    assert "wrote: 0 of 3 destination files" in capsys.readouterr().out


def test_write_then_check_is_clean(tree: Path) -> None:
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)

    sync_slim_agents.main(["--write"])

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_OK


def test_mirror_without_frontmatter_receives_the_body_verbatim(tree: Path) -> None:
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK
    assert target.read_text(encoding="utf-8") == SOURCE_BODY


def test_non_ascii_body_survives_the_round_trip(tree: Path) -> None:
    body = "# Analyst\n\nRoundtrip: café 中文 ✓\n"
    _write(tree / ".claude" / "agents" / f"{AGENT}.md", CLAUDE_FRONTMATTER + body)
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK
    assert target.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + body


def test_split_frontmatter_returns_whole_text_when_absent() -> None:
    assert sync_slim_agents.split_frontmatter("no frontmatter\n") == (
        "",
        "no frontmatter\n",
    )


def test_split_frontmatter_returns_whole_text_when_unterminated() -> None:
    text = "---\nname: analyst\nstill open\n"
    assert sync_slim_agents.split_frontmatter(text) == ("", text)


def test_split_frontmatter_keeps_both_delimiters_in_the_frontmatter() -> None:
    frontmatter, body = sync_slim_agents.split_frontmatter(
        CLAUDE_FRONTMATTER + SOURCE_BODY
    )
    assert frontmatter == CLAUDE_FRONTMATTER
    assert body == SOURCE_BODY


def test_shipped_slimmed_agents_all_exist_in_every_tree() -> None:
    """The real declared list must not name an agent that no tree has.

    An earlier draft carried `spec-generator`, which is a skill, not an agent.
    """
    assert sync_slim_agents.find_missing_paths(sync_slim_agents.SLIMMED_AGENTS) == []
