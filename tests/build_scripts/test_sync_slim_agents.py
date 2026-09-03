"""Behavior tests for build/sync_slim_agents.py (Refs #5282).

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
- Edge: an I/O failure exits 3, not 1.
- CLI: --check is accepted, matches the default, and excludes --write.

The frontmatter parsing contract and the shipped-constant checks live in
`test_sync_slim_agents_contract.py`; every case here drives the `tree` fixture.
- Platform: reported paths use forward slashes.
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


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    """Follow tests/build_scripts/test_build_all.py: skip where links are denied."""
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable; issue #4632: {exc}")


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


def test_check_flag_is_accepted_and_matches_the_default(tree: Path) -> None:
    """The docs spell the default mode `--check`, so the parser must take it."""
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main(["--check"]) == sync_slim_agents.EXIT_DRIFT
    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_DRIFT


def test_check_and_write_are_mutually_exclusive(tree: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        sync_slim_agents.main(["--check", "--write"])

    assert excinfo.value.code == 2


def test_relative_paths_use_forward_slashes(tree: Path) -> None:
    reported = sync_slim_agents._relative(
        tree / "templates" / "agents" / f"{AGENT}.shared.md"
    )

    assert reported == "templates/agents/analyst.shared.md"


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
    _symlink_or_skip(template, external)

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
    _symlink_or_skip(source, external)
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    assert "src/claude/analyst.md" in capsys.readouterr().err
    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + SOURCE_BODY


def test_undecodable_file_is_an_external_failure(tree: Path, capsys) -> None:
    """AGENTS.md reserves 3 for external failures. Exit 1 would read as drift.

    UnicodeDecodeError is the deterministic half of the pair the CLI boundary
    catches; OSError reaches the same handler and needs no separate case.
    """
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    target.write_bytes(b"---\nname: analyst\n---\n\xff\xfe not utf-8\n")

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_EXTERNAL
    assert "sync-slim-agents:" in capsys.readouterr().err


def test_write_names_both_follow_up_steps(tree: Path, capsys) -> None:
    """The installed copy is not synced here, so the output must say so."""
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK

    out = capsys.readouterr().out
    assert "build/generate_agents.py" in out
    assert ".claude/agents/" in out
    assert "check_agent_content_parity.py" in out


def test_mirror_that_is_only_a_bare_delimiter_is_a_config_error(tree: Path,
                                                                capsys) -> None:
    """A file that is exactly `---` opens a block with no newline after it."""
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, "---")

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    assert "templates/agents/analyst.shared.md" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "---"


def test_mirror_whose_frontmatter_ends_the_file_keeps_a_separator(tree: Path) -> None:
    """End to end, not just the parser: `---` plus a body must stay two lines.

    A closing delimiter at end of file carries no newline of its own, so a
    straight concatenation produces `---# Analyst` and the block stops parsing.
    """
    target = tree / ".github" / "agents" / f"{AGENT}.agent.md"
    _write(target, "---\nname: analyst\n---")

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK
    assert target.read_text(encoding="utf-8") == "---\nname: analyst\n---\n" + SOURCE_BODY


def test_symlinked_mirror_inside_the_root_is_still_refused(tree: Path,
                                                          capsys) -> None:
    """Isolates the `is_symlink()` clause: this link stays inside the root.

    Both escaping-symlink tests above also fail containment, so deleting
    `path.is_symlink()` still leaves them red. This one passes containment and
    fails only on the symlink test itself.
    """
    inside = tree / "elsewhere.md"
    inside.write_text(TEMPLATE_FRONTMATTER + STALE_BODY, encoding="utf-8")
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    template.unlink()
    _symlink_or_skip(template, inside)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    assert "templates/agents/analyst.shared.md" in capsys.readouterr().err
    assert inside.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + STALE_BODY


def test_mirror_under_a_symlinked_directory_is_refused(tree: Path,
                                                       capsys) -> None:
    """Isolates the containment clause: the leaf here is a real file.

    `path.is_symlink()` is false because the link is the parent directory, so
    only the resolved-path check can catch this one.
    """
    external_dir = tree.parent / f"{tree.name}-external-dir"
    external_dir.mkdir(exist_ok=True)
    (external_dir / f"{AGENT}.shared.md").write_text(
        TEMPLATE_FRONTMATTER + STALE_BODY, encoding="utf-8"
    )
    agents_dir = tree / "templates" / "agents"
    (agents_dir / f"{AGENT}.shared.md").unlink()
    agents_dir.rmdir()
    _symlink_or_skip(agents_dir, external_dir, directory=True)

    assert not (agents_dir / f"{AGENT}.shared.md").is_symlink()
    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    assert "templates/agents/analyst.shared.md" in capsys.readouterr().err
    assert (external_dir / f"{AGENT}.shared.md").read_text(
        encoding="utf-8"
    ) == TEMPLATE_FRONTMATTER + STALE_BODY


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


def test_mirror_with_an_empty_frontmatter_block_keeps_it(tree: Path) -> None:
    """The whole path, not just the parser: an empty block must survive --write."""
    target = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(target, "---\n---\n" + STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK
    assert target.read_text(encoding="utf-8") == "---\n---\n" + SOURCE_BODY
