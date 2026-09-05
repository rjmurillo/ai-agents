"""What the reconciliation layer decides, and what --check reports.

Split out of `test_sync_slim_agents.py`, which crossed the 500-line taste
limit, and named for the seam the code took: these cases exercise what
`build/sync_slim_agents_reconcile.py` decides, end to end through the CLI, so a
transform that stopped firing or a guard that stopped blocking fails here, as
does a drift report that stopped telling the two kinds apart. The sibling
module keeps the file-layer cases: path safety, atomic write, exit codes,
frontmatter preservation.

Tests:
- Positive: matching bodies report zero drift and exit 0.
- Negative: a drifted body exits 1 and names the file.
- Positive: the `mcp__github__` prefix is stripped into both destinations.
- Positive: `mcp__serena__` is written through untouched.
- Positive: a destination missing a whole section still syncs; insert-only is
  not blocking.
- Negative: a reworded destination line blocks --write with exit 2, names the
  file and the line, and leaves a second syncable destination untouched.
- Negative: a destination-only line (the delete case) blocks the same way.
- Negative: --check on a blocked tree exits 1 and counts unmechanizable drift
  apart from drift it can apply.
- Edge: a long blocked line is truncated so it cannot bury the rest.
- Edge: apply_sync is handed only the writable set, so a direct call writes
  nothing on a blocked tree.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "build" / "sync_slim_agents.py"

# A distinct module name, for the reason `test_sync_slim_agents_contract.py`
# records: loading here must not displace either sibling's own instance in
# sys.modules, or the `tree` fixture below would monkeypatch constants another
# module is asserting on.
_spec = importlib.util.spec_from_file_location("sync_slim_agents_transforms", _SCRIPT)
assert _spec is not None and _spec.loader is not None
sync_slim_agents = importlib.util.module_from_spec(_spec)
sys.modules["sync_slim_agents_transforms"] = sync_slim_agents
_spec.loader.exec_module(sync_slim_agents)


AGENT = "analyst"
SOURCE_BODY = "# Analyst\n\nBody from the Claude tree.\n"

# Drift the tool may repair: every line here is also in SOURCE_BODY, so the
# reconciliation guard sees inserts alone and lets the copy through.
STALE_BODY = "# Analyst\n"

# Drift the tool must refuse: line 3 says the same thing in wording no
# transform produces, which is a `replace` opcode.
REWORDED_BODY = "# Analyst\n\nBody from the Claude tree, reworded.\n"

# The other blocking shape: a line the source does not have at all.
DESTINATION_ONLY_BODY = SOURCE_BODY + "\nDestination-only note.\n"

GITHUB_TOOL_BODY = "# Analyst\n\nCall `mcp__github__pull_request_read` first.\n"
SERENA_TOOL_BODY = "# Analyst\n\nCall `mcp__serena__read_memory` first.\n"
SECTIONED_BODY = "# Analyst\n\n## Tools\n\nRead, Grep, Glob.\n"

CLAUDE_FRONTMATTER = "---\nname: analyst\nmodel: sonnet\n---\n"
GITHUB_FRONTMATTER = "---\nname: analyst\ntools:\n  - read\n---\n"
TEMPLATE_FRONTMATTER = "---\nrole: support\ntools_vscode:\n  - read\n---\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a source-plus-mirrors fixture and point the module at it.

    Duplicated from the sibling module rather than shared. A pytest fixture
    reaches another module only through a `conftest.py`, and this one is too
    specific to belong to every test under `tests/build_scripts/`.
    """
    src_claude = tmp_path / "src" / "claude"
    templates = tmp_path / "templates" / "agents"
    github_agents = tmp_path / ".github" / "agents"

    _write(src_claude / f"{AGENT}.md", CLAUDE_FRONTMATTER + SOURCE_BODY)
    _write(templates / f"{AGENT}.shared.md", TEMPLATE_FRONTMATTER + SOURCE_BODY)
    _write(github_agents / f"{AGENT}.agent.md", GITHUB_FRONTMATTER + SOURCE_BODY)

    destination = sync_slim_agents.Destination
    monkeypatch.setattr(sync_slim_agents, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sync_slim_agents, "AGENT_SOURCE", src_claude)
    monkeypatch.setattr(
        sync_slim_agents,
        "DESTINATIONS",
        (
            destination(
                "templates/agents",
                templates,
                ".shared.md",
                sync_slim_agents.MIRROR_TRANSFORMS,
            ),
            destination(
                ".github/agents",
                github_agents,
                ".agent.md",
                sync_slim_agents.MIRROR_TRANSFORMS,
            ),
        ),
    )
    monkeypatch.setattr(sync_slim_agents, "SLIMMED_AGENTS", (AGENT,))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_github_tool_prefix_is_stripped_into_both_destinations(tree: Path) -> None:
    """The one mechanizable rule: `mcp__github__x` reaches a mirror as `x`."""
    _write(tree / "src" / "claude" / f"{AGENT}.md",
           CLAUDE_FRONTMATTER + GITHUB_TOOL_BODY)
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    github = tree / ".github" / "agents" / f"{AGENT}.agent.md"
    _write(template, TEMPLATE_FRONTMATTER + STALE_BODY)
    _write(github, GITHUB_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK

    expected = "# Analyst\n\nCall `pull_request_read` first.\n"
    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + expected
    assert github.read_text(encoding="utf-8") == GITHUB_FRONTMATTER + expected


def test_serena_tool_prefix_is_written_through_unchanged(tree: Path) -> None:
    """`mcp__serena__` is in all three trees, so stripping it would be wrong."""
    _write(tree / "src" / "claude" / f"{AGENT}.md",
           CLAUDE_FRONTMATTER + SERENA_TOOL_BODY)
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    github = tree / ".github" / "agents" / f"{AGENT}.agent.md"
    _write(template, TEMPLATE_FRONTMATTER + STALE_BODY)
    _write(github, GITHUB_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK

    assert template.read_text(encoding="utf-8") == (
        TEMPLATE_FRONTMATTER + SERENA_TOOL_BODY
    )
    assert github.read_text(encoding="utf-8") == GITHUB_FRONTMATTER + SERENA_TOOL_BODY


def test_destination_missing_a_whole_section_still_syncs(tree: Path) -> None:
    """Insert-only is the safe shape: the copy adds lines and drops none."""
    _write(tree / "src" / "claude" / f"{AGENT}.md",
           CLAUDE_FRONTMATTER + SECTIONED_BODY)
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    github = tree / ".github" / "agents" / f"{AGENT}.agent.md"
    _write(template, TEMPLATE_FRONTMATTER + "# Analyst\n")
    _write(github, GITHUB_FRONTMATTER + "# Analyst\n")

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_OK

    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + SECTIONED_BODY


def test_reworded_destination_blocks_write_and_writes_nothing(tree: Path,
                                                              capsys) -> None:
    """A `replace` opcode is destination wording no transform reproduces.

    The second mirror carries insert-only drift, so it is writable on its own.
    The refusal covers the whole run, which is what keeps a partial sync from
    landing when one file is blocked.
    """
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    github = tree / ".github" / "agents" / f"{AGENT}.agent.md"
    _write(template, TEMPLATE_FRONTMATTER + REWORDED_BODY)
    _write(github, GITHUB_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    err = capsys.readouterr().err
    assert "templates/agents/analyst.shared.md" in err
    # Frontmatter is 5 lines, the reworded line is body line 3.
    assert "line 8 destination: Body from the Claude tree, reworded." in err
    assert "line 8 source:      Body from the Claude tree." in err
    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + REWORDED_BODY
    assert github.read_text(encoding="utf-8") == GITHUB_FRONTMATTER + STALE_BODY


def test_destination_only_line_blocks_write(tree: Path, capsys) -> None:
    """The `delete` case: a copy would drop a line the source never had.

    `templates/agents/implementer.shared.md` carries a real one, the
    `vendor-portability` declaration comment.
    """
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(template, TEMPLATE_FRONTMATTER + DESTINATION_ONLY_BODY)

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    err = capsys.readouterr().err
    assert "templates/agents/analyst.shared.md" in err
    assert "line 10 destination: Destination-only note." in err
    assert "line 10 source:      (no matching source line)" in err
    assert template.read_text(encoding="utf-8") == (
        TEMPLATE_FRONTMATTER + DESTINATION_ONLY_BODY
    )


def test_check_counts_the_two_kinds_of_drift_apart(tree: Path, capsys) -> None:
    """Both kinds exit 1, but only one of them is cleared by running --write."""
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + REWORDED_BODY)
    _write(tree / ".github" / "agents" / f"{AGENT}.agent.md",
           GITHUB_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main(["--check"]) == sync_slim_agents.EXIT_DRIFT

    out = capsys.readouterr().out
    assert "examined 2 destination files: 0 in sync, 1 with drift" in out
    assert "1 with drift --write can apply" in out
    assert "1 with drift it cannot mechanize" in out
    assert "can apply: .github/agents/analyst.agent.md" in out
    assert "cannot mechanize: templates/agents/analyst.shared.md" in out


def test_blocked_line_is_truncated_in_the_report(tree: Path, capsys) -> None:
    """One 200-character table row must not scroll the other findings away."""
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + "# Analyst\n\n" + "x" * 200 + "\n")

    assert sync_slim_agents.main(["--write"]) == sync_slim_agents.EXIT_CONFIG

    err = capsys.readouterr().err
    assert "x" * 73 + "..." in err
    assert "x" * 77 not in err


def test_apply_sync_skips_a_blocked_file_when_called_directly(tree: Path) -> None:
    """The CLI refuses first, so this pins the second gate behind that one."""
    template = tree / "templates" / "agents" / f"{AGENT}.shared.md"
    _write(template, TEMPLATE_FRONTMATTER + REWORDED_BODY)

    drift = sync_slim_agents.compare(sync_slim_agents.SLIMMED_AGENTS)

    assert sync_slim_agents.apply_sync(drift) == []
    assert template.read_text(encoding="utf-8") == TEMPLATE_FRONTMATTER + REWORDED_BODY


def test_check_reports_no_drift_when_bodies_match(tree: Path, capsys) -> None:
    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_OK

    assert "examined 2 destination files: 2 in sync, 0 with drift" in (
        capsys.readouterr().out
    )


def test_check_exits_nonzero_and_names_the_drifted_file(tree: Path, capsys) -> None:
    _write(tree / "templates" / "agents" / f"{AGENT}.shared.md",
           TEMPLATE_FRONTMATTER + STALE_BODY)

    assert sync_slim_agents.main([]) == sync_slim_agents.EXIT_DRIFT

    out = capsys.readouterr().out
    assert "1 with drift --write can apply" in out
    assert "can apply: templates/agents/analyst.shared.md" in out
