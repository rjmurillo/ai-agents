"""Tests for build/sync_slim_agents.py (Refs #5282).

The script copies an agent body from `src/claude/{name}.md` into two
hand-maintained mirrors, preserving each mirror's own frontmatter. Default mode
reports drift and exits non-zero; `--write` applies the copy.

Tests:
- Positive: matching bodies report zero drift and exit 0.
- Negative: a drifted body exits 1 and names the file.
- Negative: a declared agent missing from the source exits 2 (config).
- Negative: a declared agent missing from one mirror exits 2 (config).
- Negative: the installed `.claude/agents/` copy is neither read nor written.
- Negative: unterminated frontmatter in the source or a mirror exits 2 and
  writes nothing.
- Negative: a source or mirror symlinked outside the root exits 2 and leaves
  the external file untouched.
- Negative: `--write` from outside the repository root exits 2 and writes
  nothing; from a subdirectory of the root it proceeds.
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

UNTERMINATED_FRONTMATTER = "---\nname: analyst\nstill open\n\n# Body\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a source-plus-mirrors fixture and point the module at it.

    `.claude/agents/` is written with a stale body on purpose. It is the
    installed runtime copy, so the script must neither read nor write it; a
    test below pins that.
    """
    src_claude = tmp_path / "src" / "claude"
    templates = tmp_path / "templates" / "agents"
    github_agents = tmp_path / ".github" / "agents"
    installed = tmp_path / ".claude" / "agents"

    _write(src_claude / f"{AGENT}.md", CLAUDE_FRONTMATTER + SOURCE_BODY)
    _write(templates / f"{AGENT}.shared.md", TEMPLATE_FRONTMATTER + SOURCE_BODY)
    _write(github_agents / f"{AGENT}.agent.md", GITHUB_FRONTMATTER + SOURCE_BODY)
    _write(installed / f"{AGENT}.md", CLAUDE_FRONTMATTER + STALE_BODY)

    destination = sync_slim_agents.Destination
    monkeypatch.setattr(sync_slim_agents, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sync_slim_agents, "AGENT_SOURCE", src_claude)
    monkeypatch.setattr(
        sync_slim_agents,
        "DESTINATIONS",
        (
            destination("templates/agents", templates, ".shared.md"),
            destination(".github/agents", github_agents, ".agent.md"),
        ),
    )
    monkeypatch.setattr(sync_slim_agents, "SLIMMED_AGENTS", (AGENT,))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_check_reports_no_drift_when_bodies_match(tree: Path, capsys) -> None:
    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_OK
    assert "drifted: 0 of 2 destination files" in capsys.readouterr().out


def test_check_exits_nonzero_and_names_the_drifted_file(tree: Path, capsys) -> None:
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_DRIFT

    out = capsys.readouterr().out
    assert "drifted: 1 of 2 destination files" in out
    assert "templates/agents/analyst.shared.md" in out


def test_check_does_not_mutate_the_drifted_file(tree: Path) -> None:
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, TEMPLATE_FRONTMATTER + STALE_BODY)

    sync_slim_agents.main([])

    assert target.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + STALE_BODY


def test_missing_source_agent_is_a_config_error(tree: Path, capsys) -> None:
    (tree / "src" / "claude" / f"{AGENT}.md").unlink()

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_CONFIG

    err = capsys.readouterr().err
    assert "src/claude/analyst.md" in err
    assert "Refusing to sync a partial set." in err


def test_missing_mirror_file_is_a_config_error(tree: Path, capsys) -> None:
    (tree / ".github" / "agents" / f"{AGENT}.agent.md").unlink()

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_CONFIG
    assert ".github/agents/analyst.agent.md" in capsys.readouterr().err


def test_installed_claude_copy_is_neither_read_nor_written(tree: Path) -> None:
    """`.claude/agents/` is the runtime copy, so it is not in the path set.

    Its body is stale in the fixture. If it were the source, --write would push
    that stale body into both mirrors; if it were a destination, --write would
    overwrite it. Neither happens.
    """
    installed = tree / ".claude" / "agents" / f"{AGENT}.md"
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"

    assert installed not in set(
        sync_slim_agents.declared_paths(sync_slim_agents.SLIMMED_AGENTS)
    )
    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK

    assert installed.read_text(encoding="utf-8") == CLAUDE_FRONTMATTER + STALE_BODY
    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + SOURCE_BODY


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
    assert "wrote: 0 of 2 destination files" in capsys.readouterr().out


def test_write_then_check_is_clean(tree: Path) -> None:
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)

    sync_slim_agents.main(["--write"])

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_OK


def test_write_from_a_subdirectory_of_the_root_proceeds(tree: Path,
                                                        monkeypatch) -> None:
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, TEMPLATE_FRONTMATTER + STALE_BODY)
    monkeypatch.chdir(tree / "templates" / "agents")

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK
    assert target.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + SOURCE_BODY


def test_write_from_outside_the_root_is_a_config_error(tree: Path, monkeypatch,
                                                       capsys) -> None:
    """MUST 7: the write must not land in a checkout the caller is not in."""
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, TEMPLATE_FRONTMATTER + STALE_BODY)
    monkeypatch.chdir(tree.parent)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    assert "outside the repository root" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + STALE_BODY


def test_check_from_outside_the_root_still_runs(tree: Path, monkeypatch) -> None:
    """The guard is scoped to --write; a read-only run has nothing to protect."""
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)
    monkeypatch.chdir(tree.parent)

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_DRIFT


def test_unterminated_source_frontmatter_is_a_config_error(tree: Path,
                                                           capsys) -> None:
    """A broken source must not copy its open `---` block into every mirror."""
    _write(tree / "src" / "claude" / f"{AGENT}.md", UNTERMINATED_FRONTMATTER)
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    err = capsys.readouterr().err
    assert "src/claude/analyst.md" in err
    assert "never closes" in err
    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + SOURCE_BODY


def test_unterminated_mirror_frontmatter_is_a_config_error(tree: Path,
                                                           capsys) -> None:
    """A broken mirror must not have its metadata deleted by a successful run."""
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    github = tree / ".github" / "agents" / f"{AGENT}.agent.md"
    _write(template, UNTERMINATED_FRONTMATTER)
    _write(github, GITHUB_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    assert "templates/agents/analyst.shared.md" in capsys.readouterr().err
    assert template.read_text(encoding="utf-8") == UNTERMINATED_FRONTMATTER
    assert github.read_text(encoding="utf-8") == GITHUB_FRONTMATTER + STALE_BODY


def test_symlinked_mirror_outside_the_root_is_a_config_error(tree: Path,
                                                             capsys) -> None:
    """write_text follows symlinks, so an escaping mirror must be refused."""
    external = tree.parent / f"{tree.name}-external.md"
    external.write_text(TEMPLATE_FRONTMATTER + STALE_BODY, encoding="utf-8")
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    template.unlink()
    template.symlink_to(external)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    err = capsys.readouterr().err
    assert "templates/agents/analyst.shared.md" in err
    assert external.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + STALE_BODY


def test_symlinked_source_outside_the_root_is_a_config_error(tree: Path,
                                                             capsys) -> None:
    """read_text follows symlinks too, so an escaping source is refused."""
    external = tree.parent / f"{tree.name}-external-source.md"
    external.write_text(CLAUDE_FRONTMATTER + STALE_BODY, encoding="utf-8")
    source = tree / "src" / "claude" / f"{AGENT}.md"
    source.unlink()
    source.symlink_to(external)
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    assert "src/claude/analyst.md" in capsys.readouterr().err
    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + SOURCE_BODY


def test_mirror_without_frontmatter_receives_the_body_verbatim(tree: Path) -> None:
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK
    assert target.read_text(encoding="utf-8") == SOURCE_BODY


def test_non_ascii_body_survives_the_round_trip(tree: Path) -> None:
    body = "# Analyst\n\nRoundtrip: café 中文 ✓\n"
    _write(tree / "src" / "claude" / f"{AGENT}.md", CLAUDE_FRONTMATTER + body)
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\nname: analyst\nstill open\n", True),
        (UNTERMINATED_FRONTMATTER, True),
        (CLAUDE_FRONTMATTER + SOURCE_BODY, False),
        ("no frontmatter\n", False),
        ("", False),
        ("---\n", True),
        ("---\n---\n" + SOURCE_BODY, False),
        ("---\nname: analyst\n---", False),
        ("---\n---", False),
    ],
)
def test_has_unterminated_frontmatter(text: str, expected: bool) -> None:
    assert sync_slim_agents.has_unterminated_frontmatter(text) is expected


def test_split_frontmatter_accepts_an_empty_block() -> None:
    """`---` on one line and `---` on the next is empty frontmatter, not broken."""
    assert sync_slim_agents.split_frontmatter("---\n---\n" + SOURCE_BODY) == (
        "---\n---\n",
        SOURCE_BODY,
    )


def test_split_frontmatter_accepts_a_closer_at_end_of_file() -> None:
    """A closing `---` with no trailing newline still closes the block."""
    text = "---\nname: analyst\n---"
    assert sync_slim_agents.split_frontmatter(text) == (text, "")


def test_mirror_with_an_empty_frontmatter_block_keeps_it(tree: Path) -> None:
    """The whole path, not just the parser: an empty block must survive --write."""
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, "---\n---\n" + STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK
    assert target.read_text(encoding="utf-8") == "---\n---\n" + SOURCE_BODY


def test_shipped_source_is_the_canonical_claude_tree() -> None:
    """`src/claude/` is the edit-here source; `.claude/agents/` is the runtime copy.

    The fixture above monkeypatches AGENT_SOURCE and DESTINATIONS, so no test
    that uses it can see an inverted shipped direction. This one reads the
    shipped constants directly, which is the only place the inversion shows.
    """
    directories = {destination.directory for destination in sync_slim_agents.DESTINATIONS}

    assert sync_slim_agents.AGENT_SOURCE == _REPO_ROOT / "src" / "claude"
    assert _REPO_ROOT / ".claude" / "agents" not in directories
    assert sync_slim_agents.AGENT_SOURCE not in directories


def test_shipped_slimmed_agents_all_exist_in_every_tree() -> None:
    """The real declared list must not name an agent that no tree has.

    An earlier draft carried `spec-generator`, which is a skill, not an agent.
    """
    assert sync_slim_agents.find_missing_paths(sync_slim_agents.SLIMMED_AGENTS) == []


def test_shipped_trees_carry_no_unsafe_or_malformed_paths() -> None:
    """The live tree passes the two guards, so the gate is not shipping red."""
    assert sync_slim_agents.find_unsafe_paths(sync_slim_agents.SLIMMED_AGENTS) == []
    assert sync_slim_agents.find_malformed_paths(sync_slim_agents.SLIMMED_AGENTS) == []
