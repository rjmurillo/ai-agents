"""Tests for which files the plugin-root routing gate is willing to read.

Pins the walk discipline of scripts/validation/check_shipped_skill_routes.py.
Every test here answers one question: given a path the gate encounters, does it
read it, skip it, or refuse to guess?

- pos: a real skill directory whose name collides with a tooling name is still
  scanned, and a manifest reached through a working symlink is still discovered
- neg: a nested working copy, and tooling directly under the skills directory,
  are pruned before their contents are read
- config: an unreadable file, an unlistable directory, undecodable bytes, a
  symlinked plugin root, a wrong-kind path, and a dangling markdown symlink are
  all exit 2 per ADR-035, because a gate that cannot read a file must not
  report that the file holds no routes

The fail-open shape this suite exists to catch: a path the gate silently treats
as absent removes routes from the scan while the run still reports PASS. Round
six of adversarial review found two of them. A broken manifest symlink dropped
an entire plugin root, and a broken skill marker counted as an installed skill
to the inventory while reading as absent to the pruner, so a directory the
inventory had already credited was never entered. Both returned exit 0.

Assertions here check the exit code and the message, never the traversal order,
so the walk can be rewritten without rewriting the suite.

Routing verdicts are pinned in test_check_shipped_skill_routes.py; which text
counts as a route is pinned in test_check_shipped_skill_routes_markdown.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.validation.shipped_skill_routes_helpers import (
    EXIT_CONFIG,
    EXIT_DRIFT,
    EXIT_OK,
    drop_skill,
    repo,
    run_gate,
    write_doc,
    write_skill,
)

__all__ = ["repo"]

# Four tests below build their precondition out of file permissions. Root
# ignores the mode bits and Windows does not carry them, so on either the
# barrier is absent and the gate succeeds where the test expects a refusal,
# which reads as a defect in the gate rather than a missing precondition.
# ``os.geteuid`` itself is absent on Windows, and a bare call in a skipif
# argument is evaluated at import, so an unguarded call fails collection for
# the whole module rather than skipping one test. Mirrors the idiom in
# tests/eval/test_optimize_artifact_cli.py.
_NO_PERMISSION_BARRIER = os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0)
_NEEDS_PERMISSION_BARRIER = pytest.mark.skipif(
    _NO_PERMISSION_BARRIER, reason="root and Windows do not honour the barrier this needs"
)


def test_nested_working_copies_are_not_walked(repo: Path) -> None:
    """A worktree carries a full copy of the repo; drift there is not ours."""
    nested = repo / "src/copilot-cli" / "worktrees" / "wt1" / "skills" / "autoplan"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "SKILL.md").write_text(
        "| X | R |\n| --- | --- |\n| X | Skill: ghost |\n", encoding="utf-8"
    )

    assert run_gate(repo).returncode == EXIT_OK


# --- config errors (ADR-035: exit 2) ---


def test_missing_plugin_root_is_config_error(tmp_path: Path) -> None:
    result = run_gate(tmp_path)
    assert result.returncode == EXIT_CONFIG
    assert "no plugin roots" in result.stderr


def test_manifestless_directory_is_not_a_root(tmp_path: Path) -> None:
    write_skill(tmp_path, ".claude", "autoplan", "| X | R |\n| --- | --- |\n| X | Skill: ghost |\n")
    result = run_gate(tmp_path)
    # No plugin.json, so .claude is not a root and nothing is scanned.
    assert result.returncode == EXIT_CONFIG
    assert "no plugin roots" in result.stderr


@_NEEDS_PERMISSION_BARRIER
def test_unreadable_file_is_config_error_not_a_silent_pass(repo: Path) -> None:
    """Swallowing OSError would let an unreadable file hide a live route."""
    blocked = write_doc(
        repo, "src/copilot-cli", "blocked.md", "| X | R |\n| --- | --- |\n| X | Skill: ghost |\n"
    )
    blocked.chmod(0o000)
    try:
        result = run_gate(repo)
    finally:
        blocked.chmod(0o644)
    assert result.returncode == EXIT_CONFIG
    assert "cannot read" in result.stderr


def test_nesting_past_the_parser_limit_is_refused(repo: Path) -> None:
    """Content the parser cannot fully represent is an incomplete scan.

    markdown-it stops at ``maxNesting``, so a table nested past the limit is
    dropped from the token stream. Reporting success on a file the parser
    truncated would pass a root whose routes were never read, so the file is
    refused as a config error instead.
    """
    quote = "> " * 40
    write_doc(
        repo,
        "src/copilot-cli",
        "deep.md",
        f"{quote}| X | R |\n{quote}| --- | --- |\n{quote}| X | Skill: ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "cannot parse" in result.stdout + result.stderr


def test_a_tooling_directory_nested_in_a_skill_is_pruned(repo: Path) -> None:
    """A venv or node_modules inside a skill is tool output, not content.

    Root-only pruning walked these. That scans thousands of third-party files
    and trips the symlink refusal on the interpreter links every virtualenv
    carries, which hard-fails the gate and blocks every push in the repo.
    Measured across the live plugin roots, no such directory holds authored
    content today, so the blocking failure is the expensive one to allow.
    """
    path = repo / "src/copilot-cli/skills/autoplan/venv/notes.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("| M | R |\n| --- | --- |\n| Merge | Skill: ghost |\n", encoding="utf-8")
    result = run_gate(repo)
    assert result.returncode == EXIT_OK


def test_a_symlink_inside_a_nested_tooling_directory_does_not_block(repo: Path) -> None:
    """npm ci leaves symlinks in node_modules/.bin. That is not a config error."""
    nested = repo / "src/copilot-cli/skills/autoplan/node_modules"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / ".bin").symlink_to(repo, target_is_directory=True)
    result = run_gate(repo)
    assert result.returncode == EXIT_OK


def test_a_skill_named_venv_is_still_scanned(repo: Path) -> None:
    """A SKILL.md under skills/ exempts the name, so a collision is safe."""
    write_skill(
        repo, "src/copilot-cli", "venv", "| M | R |\n| --- | --- |\n| Merge | Skill: ghost |\n"
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "ghost" in result.stdout


@pytest.mark.parametrize("name", [".venv", "venv", "node_modules"])
def test_real_tooling_directly_under_skills_is_pruned(repo: Path, name: str) -> None:
    """Exempting the whole skills namespace by location was too broad.

    A virtualenv created in that directory is a direct child of ``skills/``
    too. Exempting by location walked into it and the interpreter symlinks
    every virtualenv carries hit the symlink refusal, which is exit 2 on every
    push in the repository. The marker file is what separates a real skill
    from tooling that happens to sit beside one.
    """
    tooling = repo / "src/copilot-cli" / "skills" / name
    (tooling / "lib").mkdir(parents=True)
    (tooling / "lib64").symlink_to("lib")
    (tooling / "notes.md").write_text(
        "| M | R |\n| --- | --- |\n| Merge | Skill: ghost |\n", encoding="utf-8"
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_tooling_under_skills_is_pruned_before_its_contents_are_read(
    repo: Path,
) -> None:
    """Pruning has to happen ahead of the per-directory symlink refusal.

    Order is the whole point: a refusal that ran first would report the
    virtualenv's own interpreter links and block the push before the name
    check ever got a say.
    """
    tooling = repo / ".claude" / "skills" / ".venv" / "bin"
    tooling.mkdir(parents=True)
    (tooling / "python3").symlink_to("/usr/bin/python3")
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_skill_named_worktrees_is_scanned(repo: Path) -> None:
    """Reserving worktree container names globally would hide a real skill."""
    write_skill(
        repo,
        "src/copilot-cli",
        "worktrees",
        "| I | R |\n| --- | --- |\n| M | Skill: ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "ghost" in result.stdout


def test_undecodable_bytes_are_a_config_error(repo: Path) -> None:
    """errors='replace' would corrupt a route into a silent pass."""
    path = repo / "src/copilot-cli/skills/autoplan/broken.md"
    path.write_bytes(b"| I | R |\n| --- | --- |\n| M | Skill: gh\xffost |\n")
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG
    assert "cannot decode" in result.stderr


@_NEEDS_PERMISSION_BARRIER
def test_unreadable_directory_is_config_error_not_a_silent_skip(repo: Path) -> None:
    """os.walk swallows directory errors by default, shrinking the scan."""
    blocked = repo / "src/copilot-cli/skills/autoplan/locked"
    blocked.mkdir(parents=True)
    (blocked / "x.md").write_text("| I | R |\n| --- | --- |\n| M | Skill: ghost |\n")
    blocked.chmod(0o000)
    try:
        result = run_gate(repo)
    finally:
        blocked.chmod(0o755)
    assert result.returncode == EXIT_CONFIG
    assert "cannot walk" in result.stderr


# --- regression ---


@_NEEDS_PERMISSION_BARRIER
def test_unlistable_platform_parent_is_a_config_error(repo: Path) -> None:
    """A root the process cannot enumerate must fail closed, not vanish.

    Dropping src/copilot-cli silently would leave .claude to carry the pass,
    which is the same vacuous-success shape the per-root guard exists to stop.
    """
    (repo / "src").chmod(0o000)
    try:
        result = run_gate(repo)
    finally:
        (repo / "src").chmod(0o755)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "cannot list" in result.stderr


@_NEEDS_PERMISSION_BARRIER
def test_unstattable_manifest_is_a_config_error(repo: Path) -> None:
    """``Path.is_file`` answers False for a manifest it cannot stat.

    That turns an inaccessible plugin root into an absent one, so the gate
    would scan fewer roots than the repository ships and still report success.
    """
    (repo / "src" / "copilot-cli" / ".claude-plugin").chmod(0o000)
    try:
        result = run_gate(repo)
    finally:
        (repo / "src" / "copilot-cli" / ".claude-plugin").chmod(0o755)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "cannot stat" in result.stderr


def test_symlinked_directory_inside_a_root_is_refused(repo: Path) -> None:
    """os.walk will not descend into it, so its markdown would go unscanned.

    A route that drifted inside a symlinked directory passed silently. The
    gate refuses rather than following the link, because followlinks=True
    walks a cycle dozens of times and double-reports any file reachable two
    ways. No plugin root ships a symlinked directory today.
    """
    outside = repo / "shared-docs"
    outside.mkdir()
    (outside / "doc.md").write_text(
        "| T | R |\n| --- | --- |\n| M | Skill: ghost |\n", encoding="utf-8"
    )
    (repo / "src" / "copilot-cli" / "linked").symlink_to(outside)
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "symlinked directory" in result.stderr


def test_a_manifest_that_is_a_directory_is_a_config_error(repo: Path) -> None:
    """Reporting it absent would drop that root and let a sibling carry a pass."""
    manifest = repo / "src/copilot-cli/.claude-plugin/plugin.json"
    manifest.unlink()
    manifest.mkdir()
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "not a regular file" in result.stderr


def test_a_skills_path_that_is_a_file_is_a_config_error(repo: Path) -> None:
    """An empty skill set would report every route in that root as drift."""
    skills = repo / "src/copilot-cli/skills"
    for child in sorted(skills.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    skills.rmdir()
    skills.write_text("not a directory\n", encoding="utf-8")
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "not a directory" in result.stderr


def test_a_regular_file_beside_a_plugin_root_is_not_a_config_error(repo: Path) -> None:
    """src/ holds AGENTS.md beside the roots; a non-directory sibling is normal."""
    (repo / "src" / "AGENTS.md").write_text("# notes\n", encoding="utf-8")
    assert run_gate(repo).returncode == EXIT_OK


def test_a_symlinked_plugin_root_is_refused(repo: Path) -> None:
    """os.walk follows its own top path, so the symlink policy would not hold.

    The refusal inside a root covers directories found during the walk. A
    root that is itself a link slips past it, which would apply one policy to
    the root and another to everything under it.
    """
    elsewhere = repo / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".claude-plugin").mkdir()
    (elsewhere / ".claude-plugin" / "plugin.json").write_text("{}\n", encoding="utf-8")
    (repo / "src" / "linked").symlink_to(elsewhere, target_is_directory=True)
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "symlinked plugin root" in result.stderr


def test_a_broken_manifest_symlink_does_not_hide_a_root(repo: Path) -> None:
    """A link is a statement that something should be there.

    Reading its missing target as absence drops the whole platform root from
    discovery, and the roots that remain carry a pass over a route that was
    never scanned.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "hidden.md",
        "| I | R |\n| --- | --- |\n| M | Skill: ghost |\n",
    )
    manifest = repo / "src/copilot-cli/.claude-plugin/plugin.json"
    manifest.unlink()
    manifest.symlink_to("missing-plugin.json")
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "cannot resolve symlink" in result.stderr


def test_a_valid_manifest_symlink_is_still_discovered(repo: Path) -> None:
    """Only the broken link is refused; a link that resolves is a manifest."""
    manifest = repo / "src/copilot-cli/.claude-plugin/plugin.json"
    real = repo / "src/copilot-cli/.claude-plugin/real.json"
    real.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
    manifest.unlink()
    manifest.symlink_to("real.json")
    drop_skill(repo, "src/copilot-cli", "merge-resolver")
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr


def test_a_broken_skill_marker_is_not_an_installed_skill(repo: Path) -> None:
    """The inventory globs markers, and a glob lists a broken link like a file.

    Trusting it lets a route resolve to a skill whose SKILL.md does not exist,
    which is the condition this gate exists to catch.
    """
    marker = write_skill(repo, "src/copilot-cli", "ghost")
    marker.unlink()
    marker.symlink_to("missing-SKILL.md")
    write_doc(
        repo,
        "src/copilot-cli",
        "to-ghost.md",
        "| I | R |\n| --- | --- |\n| M | Skill: ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG, result.stdout + result.stderr
    assert "cannot resolve symlink" in result.stderr


def test_a_pruned_name_cannot_be_a_skill_to_one_call_site_only(repo: Path) -> None:
    """The inventory and the pruning exemption must agree on what a skill is.

    A directory named for tooling is exempt from pruning only when it carries
    a marker. When that marker is a broken link the exemption declines it and
    a glob-only inventory accepts it, so a route to ``venv`` resolved against
    a skill the walk had already refused to enter.
    """
    marker = write_skill(repo, "src/copilot-cli", "venv")
    marker.unlink()
    marker.symlink_to("missing-SKILL.md")
    write_doc(
        repo,
        "src/copilot-cli",
        "to-venv.md",
        "| I | R |\n| --- | --- |\n| M | Skill: venv |\n",
    )
    assert run_gate(repo).returncode == EXIT_CONFIG


def test_a_dangling_markdown_symlink_is_an_error(repo: Path) -> None:
    """The walk lists it, so a file that cannot be read must not be skipped."""
    (repo / "src/copilot-cli/skills/autoplan/gone.md").symlink_to("nowhere.md")
    assert run_gate(repo).returncode == EXIT_CONFIG


def test_a_dangling_symlink_that_is_not_markdown_is_ignored(repo: Path) -> None:
    """Refusing every broken link inside a root would block pushes over litter.

    Only a link that could carry a route matters, so the strictness is scoped
    to the paths the gate would otherwise read.
    """
    (repo / "src/copilot-cli/skills/autoplan/note.lnk").symlink_to("nowhere")
    assert run_gate(repo).returncode == EXIT_OK
