"""Tests for the plugin-root routing invariant.

Pins behaviour of scripts/validation/check_shipped_skill_routes.py:

- pos: a root whose routes all resolve returns exit 0
- neg: the #2026 drift shape (canonical keeps the skill, the shipped root drops
  it, the routing prose stays) returns exit 1 and names the file, the line, and
  the skill; so does a typo and a mixed-case name
- config: no plugin root, a vacuous scan, an unreadable file or directory,
  undecodable bytes, and nesting past the parser limit are exit 2 per ADR-035
- regression: the live repository satisfies the invariant

Markdown scoping (which text counts as a route at all) is pinned separately in
test_check_shipped_skill_routes_markdown.py.

The negatives deliberately use several different skill names. An earlier
revision of this suite only ever used ``merge-resolver``, so a validator that
hard-coded that one string would have passed it.

See the module docstring in the validator for the incident this encodes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.validation.shipped_skill_routes_helpers import (
    EXIT_CONFIG,
    EXIT_DRIFT,
    EXIT_OK,
    REPO_ROOT,
    TREES,
    drop_skill,
    repo,
    run_gate,
    write_doc,
    write_manifest,
    write_skill,
)

__all__ = ["repo"]


def test_passes_when_every_route_resolves(repo: Path) -> None:
    result = run_gate(repo)
    assert result.returncode == EXIT_OK
    assert "[PASS]" in result.stdout


def test_pass_message_reports_route_and_root_counts(repo: Path) -> None:
    result = run_gate(repo)
    # Two roots, one route each. A count in the pass line is what makes a
    # vacuous run visible to a human reading CI output.
    assert "2 Skill: route(s)" in result.stdout
    assert "2 plugin root(s)" in result.stdout


def test_root_without_skills_is_not_an_error(repo: Path) -> None:
    """src/claude ships a plugin manifest and zero skills. That is legal."""
    write_manifest(repo, "src/claude")
    result = run_gate(repo)
    assert result.returncode == EXIT_OK


# --- negative ---


@pytest.mark.parametrize("name", ["merge-resolver", "github", "session-init"])
def test_drift_is_reported_for_any_skill_name(repo: Path, name: str) -> None:
    """The #2026 shape: canonical keeps the skill, the shipped root drops it."""
    write_skill(repo, ".claude", name)
    write_skill(repo, "src/copilot-cli", name)
    for tree in TREES:
        write_skill(
            repo, tree, "autoplan", f"| Task | Route |\n| --- | --- |\n| Do it | Skill: {name} |\n"
        )
    drop_skill(repo, "src/copilot-cli", name)

    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "[FAIL]" in result.stdout
    assert name in result.stdout


def test_failure_names_file_line_and_missing_path(repo: Path) -> None:
    write_skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "# autoplan\n\n| Task | Route |\n| --- | --- |\n| Merge | Skill: merge-resolver |\n",
    )
    drop_skill(repo, "src/copilot-cli", "merge-resolver")

    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "src/copilot-cli/skills/autoplan/SKILL.md:5:" in result.stdout
    assert "src/copilot-cli/skills/merge-resolver/SKILL.md does not exist" in result.stdout


def test_typo_route_is_reported(repo: Path) -> None:
    """No allowlist, so a name that exists in neither root still fails."""
    write_skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "| Task | Route |\n| --- | --- |\n| X | Skill: githbu |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "githbu" in result.stdout


def test_mixed_case_route_is_checked(repo: Path) -> None:
    """The live tree routes to `Skill: SkillForge`; a lowercase-only regex was blind."""
    write_skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "| Task | Route |\n| --- | --- |\n| X | Skill: SkillForge |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "SkillForge" in result.stdout


def test_canonical_root_is_gated_too(repo: Path) -> None:
    """The invariant is symmetric: .claude must resolve its own routes."""
    write_skill(
        repo, ".claude", "autoplan", "| Task | Route |\n| --- | --- |\n| X | Skill: ghost |\n"
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert ".claude/skills/autoplan/SKILL.md" in result.stdout


def test_routes_outside_the_skills_directory_are_checked(repo: Path) -> None:
    """Agents and instructions route too, so the walk covers the whole root."""
    agent = repo / "src/copilot-cli" / "agents" / "router.agent.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text("| Task | Route |\n| --- | --- |\n| X | Skill: ghost |\n", encoding="utf-8")

    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "agents/router.agent.md" in result.stdout


def test_remediation_hint_names_the_agent_fallback(repo: Path) -> None:
    write_skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "| Task | Route |\n| --- | --- |\n| X | Skill: ghost |\n",
    )
    result = run_gate(repo)
    assert "Task(subagent_type=" in result.stdout


# --- edge: false-positive suppression ---


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


def test_zero_routes_is_a_vacuous_pass_and_fails(tmp_path: Path) -> None:
    """A renamed skills directory must not read as success."""
    for tree in TREES:
        write_manifest(tmp_path, tree)
        write_skill(tmp_path, tree, "autoplan", "# autoplan\n\nNo routing table here.\n")
    result = run_gate(tmp_path)
    assert result.returncode == EXIT_CONFIG
    assert "vacuous" in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
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
    """Pruning is exempt directly under skills/, so a name collision is safe."""
    write_skill(
        repo, "src/copilot-cli", "venv", "| M | R |\n| --- | --- |\n| Merge | Skill: ghost |\n"
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "ghost" in result.stdout


def test_populated_root_with_zero_routes_is_a_config_error(repo: Path) -> None:
    """One root going dark must not hide behind a sibling's route count."""
    write_skill(repo, "src/copilot-cli", "autoplan", "# autoplan\n\nNo table here.\n")
    result = run_gate(repo)
    assert result.returncode == EXIT_CONFIG
    assert "src/copilot-cli" in result.stderr
    assert "vacuous" in result.stderr


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


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
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


def test_live_repository_satisfies_the_invariant() -> None:
    result = run_gate(REPO_ROOT)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
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


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
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
