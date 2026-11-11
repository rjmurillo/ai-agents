"""``build/scripts/orphan_outputs.py`` scan: owners, trees, and declared hand-maintained entries.

Issue #7224. Cases run in temp git repositories built by ``orphan_test_helpers``.
The one real-tree test is read-only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_all  # noqa: E402
import orphan_outputs as oo  # noqa: E402
import orphan_prune as op  # noqa: E402
from orphan_test_helpers import (  # noqa: E402
    delete_agent_templates,
    delete_skill_template,
    make_repo,
    names,
    symlink_or_skip,
    write,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


# --- Positive: a clean tree passes ------------------------------------------


def test_clean_tree_has_no_orphans(repo: Path) -> None:
    found = oo.scan(repo)

    assert found.orphans == []
    assert found.examined > 0
    assert op.exit_code(found, None) == 0


def test_real_repository_has_no_orphans() -> None:
    found = oo.scan(REPO_ROOT)

    assert found.orphans == []
    assert found.trees >= 10
    assert found.examined > 500


def test_scan_reports_counts_even_when_clean(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    op.report_scan(repo, oo.scan(repo), check=True)

    assert "examined" in capsys.readouterr().out


# --- Negative: a removed template fails the check and names every path -------


def test_removed_skill_template_is_named_in_every_harness_tree(repo: Path) -> None:
    delete_skill_template(repo, "alpha")

    found = oo.scan(repo)

    assert names(found, repo) == {
        "src/claude/skills/alpha",
        "src/codex/skills/alpha",
        ".claude/skills/alpha",
    }
    assert op.exit_code(found, None) == 2


def test_removed_agent_template_is_named_in_every_harness_tree(repo: Path) -> None:
    delete_agent_templates(repo, "planner")

    found = oo.scan(repo)

    assert names(found, repo) == {
        "src/claude/agents/planner.md",
        "src/cursor/agents/planner.md",
        "src/vs-code-agents/planner.agent.md",
        ".claude/agents/planner.md",
    }
    assert op.exit_code(found, None) == 2


def test_agent_with_one_surviving_template_is_not_an_orphan(repo: Path) -> None:
    (repo / "templates" / "agents" / "planner.shared.md").unlink()
    (repo / "templates" / "agents" / "planner.copilot.md.tmpl").unlink()

    assert oo.scan(repo).orphans == []


def test_check_mode_prints_each_orphan_and_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    delete_skill_template(repo, "alpha")
    delete_agent_templates(repo, "critic")

    result = build_all._build_orphans(repo, check=True)

    err = capsys.readouterr().err
    assert result.exit_code == 2
    for expected in (
        "src/claude/skills/alpha",
        "src/codex/skills/alpha",
        ".claude/skills/alpha",
        "src/vs-code-agents/critic.agent.md",
        ".claude/agents/critic.md",
    ):
        assert f"ORPHANED OUTPUT: {expected} " in err
    assert (repo / "src/codex/skills/alpha/SKILL.md").exists()


def test_check_mode_on_clean_tree_exits_zero(repo: Path) -> None:
    assert build_all._build_orphans(repo, check=True).exit_code == 0


def test_malformed_platform_config_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo / "templates" / "platforms" / "bad.yaml", 'provider: "bad"\nschemaVersion: "9.0"\n')

    result = build_all._build_orphans(repo, check=True)

    assert result.exit_code == 2
    assert "orphan scan" in capsys.readouterr().err


# --- Edge: declared hand-maintained entries are not flagged -------------------


def test_vscode_copilot_instructions_is_not_an_agent_file(repo: Path) -> None:
    write(repo / "src/vs-code-agents/copilot-instructions.md")

    assert oo.scan(repo).orphans == []


def test_repo_local_skill_without_template_is_not_flagged(repo: Path) -> None:
    write(
        repo / ".claude/skills/solo/SKILL.md",
        "---\nname: solo\nmetadata:\n  distribution: repo-local\n---\n",
    )

    assert oo.scan(repo).orphans == []


def test_real_skill_directory_without_declaration_is_flagged(repo: Path) -> None:
    write(repo / ".claude/skills/solo/SKILL.md", "---\nname: solo\n---\n")

    assert names(oo.scan(repo), repo) == {".claude/skills/solo"}


def test_no_regen_agent_file_is_not_flagged(repo: Path) -> None:
    write(repo / "src/claude/agents/handmade.md", "<!-- NO-REGEN: hand written -->\nbody\n")

    assert oo.scan(repo).orphans == []


def test_agent_file_under_independent_surface_is_not_flagged(repo: Path) -> None:
    write(repo / "src/claude/agents/handmade.md", "body\n")
    write(
        repo / "templates" / "platforms" / "surface-parity.yaml",
        'schemaVersion: "1.0"\n'
        "roots:\n  - src\n"
        "surfaces:\n"
        "  - id: handmade-agent\n"
        "    path: src/claude/agents\n"
        "    relation: independent\n"
        "    include: ['handmade.md']\n"
        "    reason: Authored in place for this test.\n",
    )

    assert oo.scan(repo).orphans == []


def test_malformed_surface_manifest_is_a_config_error(repo: Path) -> None:
    write(repo / "templates" / "platforms" / "surface-parity.yaml", 'schemaVersion: "1.0"\n')

    with pytest.raises(oo.OrphanScanError):
        oo.scan(repo)


def test_stray_file_inside_surviving_skill_is_left_alone(repo: Path) -> None:
    stray = write(repo / "src/claude/skills/alpha/notes.txt")

    found = oo.scan(repo)
    done = op.prune(repo, found.orphans)

    assert found.orphans == []
    assert done.pruned == []
    assert stray.exists()


def test_non_skill_names_in_skill_trees_are_ignored(repo: Path) -> None:
    write(repo / "src/claude/skills/__pycache__/x.pyc")
    write(repo / "src/claude/skills/AGENTS.md")

    assert oo.scan(repo).orphans == []


# --- Edge: symlinked install entries ---------------------------------------------


def test_no_regen_agent_is_exempt_through_its_install_link(repo: Path) -> None:
    write(repo / "src/claude/agents/hand.md", "<!-- NO-REGEN: hand maintained -->\n")
    symlink_or_skip(repo / ".claude/agents/hand.md", "../../src/claude/agents/hand.md")

    assert oo.scan(repo).orphans == []


def test_dangling_install_link_is_flagged_even_when_it_names_an_exempt_file(repo: Path) -> None:
    symlink_or_skip(repo / ".claude/agents/hand.md", "../../src/claude/agents/hand.md")

    assert names(oo.scan(repo), repo) == {".claude/agents/hand.md"}


def test_install_link_to_an_unprotected_file_is_still_flagged(repo: Path) -> None:
    write(repo / "src/claude/agents/plain.md", "plain\n")
    symlink_or_skip(repo / ".claude/agents/plain.md", "../../src/claude/agents/plain.md")

    assert ".claude/agents/plain.md" in names(oo.scan(repo), repo)


def test_symlink_for_surviving_skill_is_not_flagged(repo: Path) -> None:
    assert (repo / ".claude/skills/alpha").is_symlink()

    assert oo.scan(repo).orphans == []
