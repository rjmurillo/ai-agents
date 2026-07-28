"""Tests for scripts/validation/check_shipped_skill_routes.py.

Pins behaviour of the plugin-root routing gate:

- pos: a root whose routes all resolve returns exit 0
- neg: the #2026 drift shape (canonical keeps the skill, the shipped root
  drops it, the routing prose stays) returns exit 1 and names the file, the
  line, and the skill; so does a typo and a mixed-case name
- edge: fenced blocks (including nested, longer, and tilde fences), HTML
  comments, indented code, inline code spans, and non-table prose do not trip
  the gate; nested working copies are not walked
- config: no plugin root, a vacuous scan, and an unreadable file are exit 2
  per ADR-035
- regression: the live repository satisfies the invariant

The negatives deliberately use several different skill names. An earlier
revision of this suite only ever used ``merge-resolver``, so a validator that
hard-coded that one string would have passed it.

See the module docstring in the validator for the incident this encodes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_shipped_skill_routes.py"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2

TREES = (".claude", "src/copilot-cli")


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def _manifest(root: Path, tree: str) -> None:
    path = root / tree / ".claude-plugin" / "plugin.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")


def _skill(root: Path, tree: str, name: str, body: str = "") -> Path:
    path = root / tree / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body or f"# {name}\n", encoding="utf-8")
    return path


def _drop(root: Path, tree: str, name: str) -> None:
    (root / tree / "skills" / name / "SKILL.md").unlink()


def _doc(root: Path, tree: str, name: str, body: str) -> Path:
    """Write a non-SKILL markdown file inside a skill directory."""
    path = root / tree / "skills" / "autoplan" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal two-root repo in which every route resolves."""
    for tree in TREES:
        _manifest(tmp_path, tree)
        _skill(tmp_path, tree, "autoplan", "| Task | Route |\n| Merge | Skill: merge-resolver |\n")
        _skill(tmp_path, tree, "merge-resolver")
    return tmp_path


# --- positive ---


def test_passes_when_every_route_resolves(repo: Path) -> None:
    result = _run(repo)
    assert result.returncode == EXIT_OK
    assert "[PASS]" in result.stdout


def test_pass_message_reports_route_and_root_counts(repo: Path) -> None:
    result = _run(repo)
    # Two roots, one route each. A count in the pass line is what makes a
    # vacuous run visible to a human reading CI output.
    assert "2 Skill: route(s)" in result.stdout
    assert "2 plugin root(s)" in result.stdout


def test_root_without_skills_is_not_an_error(repo: Path) -> None:
    """src/claude ships a plugin manifest and zero skills. That is legal."""
    _manifest(repo, "src/claude")
    result = _run(repo)
    assert result.returncode == EXIT_OK


# --- negative ---


@pytest.mark.parametrize("name", ["merge-resolver", "github", "session-init"])
def test_drift_is_reported_for_any_skill_name(repo: Path, name: str) -> None:
    """The #2026 shape: canonical keeps the skill, the shipped root drops it."""
    _skill(repo, ".claude", name)
    _skill(repo, "src/copilot-cli", name)
    for tree in TREES:
        _skill(repo, tree, "autoplan", f"| Task | Route |\n| Do it | Skill: {name} |\n")
    _drop(repo, "src/copilot-cli", name)

    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert "[FAIL]" in result.stdout
    assert name in result.stdout


def test_failure_names_file_line_and_missing_path(repo: Path) -> None:
    _skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "# autoplan\n\n| Task | Route |\n| Merge | Skill: merge-resolver |\n",
    )
    _drop(repo, "src/copilot-cli", "merge-resolver")

    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert "src/copilot-cli/skills/autoplan/SKILL.md:4:" in result.stdout
    assert "src/copilot-cli/skills/merge-resolver/SKILL.md does not exist" in result.stdout


def test_typo_route_is_reported(repo: Path) -> None:
    """No allowlist, so a name that exists in neither root still fails."""
    _skill(repo, "src/copilot-cli", "autoplan", "| Task | Route |\n| X | Skill: githbu |\n")
    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert "githbu" in result.stdout


def test_mixed_case_route_is_checked(repo: Path) -> None:
    """The live tree routes to `Skill: SkillForge`; a lowercase-only regex was blind."""
    _skill(repo, "src/copilot-cli", "autoplan", "| Task | Route |\n| X | Skill: SkillForge |\n")
    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert "SkillForge" in result.stdout


def test_canonical_root_is_gated_too(repo: Path) -> None:
    """The invariant is symmetric: .claude must resolve its own routes."""
    _skill(repo, ".claude", "autoplan", "| Task | Route |\n| X | Skill: ghost |\n")
    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert ".claude/skills/autoplan/SKILL.md" in result.stdout


def test_routes_outside_the_skills_directory_are_checked(repo: Path) -> None:
    """Agents and instructions route too, so the walk covers the whole root."""
    agent = repo / "src/copilot-cli" / "agents" / "router.agent.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text("| Task | Route |\n| X | Skill: ghost |\n", encoding="utf-8")

    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert "agents/router.agent.md" in result.stdout


def test_remediation_hint_names_the_agent_fallback(repo: Path) -> None:
    _skill(repo, "src/copilot-cli", "autoplan", "| Task | Route |\n| X | Skill: ghost |\n")
    result = _run(repo)
    assert "Task(subagent_type=" in result.stdout


# --- edge: false-positive suppression ---


def test_fenced_block_is_ignored(repo: Path) -> None:
    _doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "```markdown\n| Task | Route |\n| X | Skill: ghost |\n```\n",
    )
    assert _run(repo).returncode == EXIT_OK


def test_longer_outer_fence_is_not_closed_by_a_shorter_inner_one(repo: Path) -> None:
    _doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "````markdown\n```\n| X | Skill: ghost |\n```\n````\n",
    )
    assert _run(repo).returncode == EXIT_OK


def test_tilde_fence_is_not_closed_by_backticks(repo: Path) -> None:
    _doc(repo, "src/copilot-cli", "guide.md", "~~~\n```\n| X | Skill: ghost |\n~~~\n")
    assert _run(repo).returncode == EXIT_OK


def test_html_comment_is_ignored(repo: Path) -> None:
    _doc(repo, "src/copilot-cli", "guide.md", "<!--\n| X | Skill: ghost |\n-->\n")
    assert _run(repo).returncode == EXIT_OK


def test_line_numbers_survive_html_comment_stripping(repo: Path) -> None:
    _skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "# autoplan\n<!--\nfiller\nfiller\n-->\n| X | Skill: ghost |\n",
    )
    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert "SKILL.md:6:" in result.stdout


def test_indented_code_block_is_ignored(repo: Path) -> None:
    _doc(repo, "src/copilot-cli", "guide.md", "text\n\n    | X | Skill: ghost |\n")
    assert _run(repo).returncode == EXIT_OK


def test_inline_code_span_is_ignored(repo: Path) -> None:
    _doc(repo, "src/copilot-cli", "guide.md", "| X | route with `Skill: ghost` shown |\n")
    assert _run(repo).returncode == EXIT_OK


def test_prose_outside_a_table_is_ignored(repo: Path) -> None:
    """Heading text such as `# Skill: API Documentation Generator` is not a route."""
    _doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "# Skill: API Documentation Generator\n\n- [ ] Skill: create a test file\n",
    )
    assert _run(repo).returncode == EXIT_OK


def test_compound_word_is_not_a_route(repo: Path) -> None:
    _doc(repo, "src/copilot-cli", "guide.md", "| X | MetaSkill: ghost |\n")
    assert _run(repo).returncode == EXIT_OK


def test_nested_working_copies_are_not_walked(repo: Path) -> None:
    """A worktree carries a full copy of the repo; drift there is not ours."""
    nested = repo / "src/copilot-cli" / "worktrees" / "wt1" / "skills" / "autoplan"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "SKILL.md").write_text("| X | Skill: ghost |\n", encoding="utf-8")

    assert _run(repo).returncode == EXIT_OK


# --- config errors (ADR-035: exit 2) ---


def test_missing_plugin_root_is_config_error(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == EXIT_CONFIG
    assert "no plugin roots" in result.stderr


def test_manifestless_directory_is_not_a_root(tmp_path: Path) -> None:
    _skill(tmp_path, ".claude", "autoplan", "| X | Skill: ghost |\n")
    result = _run(tmp_path)
    # No plugin.json, so .claude is not a root and nothing is scanned.
    assert result.returncode == EXIT_CONFIG
    assert "no plugin roots" in result.stderr


def test_zero_routes_is_a_vacuous_pass_and_fails(tmp_path: Path) -> None:
    """A renamed skills directory must not read as success."""
    for tree in TREES:
        _manifest(tmp_path, tree)
        _skill(tmp_path, tree, "autoplan", "# autoplan\n\nNo routing table here.\n")
    result = _run(tmp_path)
    assert result.returncode == EXIT_CONFIG
    assert "vacuous" in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_unreadable_file_is_config_error_not_a_silent_pass(repo: Path) -> None:
    """Swallowing OSError would let an unreadable file hide a live route."""
    blocked = _doc(repo, "src/copilot-cli", "blocked.md", "| X | Skill: ghost |\n")
    blocked.chmod(0o000)
    try:
        result = _run(repo)
    finally:
        blocked.chmod(0o644)
    assert result.returncode == EXIT_CONFIG
    assert "cannot read" in result.stderr


# --- regression ---


def test_live_repository_satisfies_the_invariant() -> None:
    result = _run(REPO_ROOT)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr
