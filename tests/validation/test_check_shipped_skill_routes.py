"""Tests for scripts/validation/check_shipped_skill_routes.py.

Pins behaviour of the cross-tree routing gate:

- pos: a tree whose routes all resolve returns exit 0
- neg: the #2026 drift shape (canonical keeps the skill, the shipped tree
  drops it, the routing prose stays) returns exit 1 and names the file,
  the line, and the skill
- edge: prose that is not a canonical skill name, fenced blocks, and
  inline code spans do not trip the gate; the canonical tree is not
  itself gated
- config: a missing canonical or shipped tree is exit 2 per ADR-035
- regression: the live repository satisfies the invariant

See the module docstring in the validator for the incident this encodes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_shipped_skill_routes.py"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_CONFIG = 2


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def _skill(root: Path, tree: str, name: str, body: str = "") -> Path:
    path = root / tree / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body or f"# {name}\n", encoding="utf-8")
    return path


def _drop(root: Path, tree: str, name: str) -> None:
    (root / tree / "skills" / name / "SKILL.md").unlink()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal two-tree repo in which every route resolves."""
    for tree in (".claude", "src/copilot-cli"):
        _skill(tmp_path, tree, "autoplan")
        _skill(tmp_path, tree, "merge-resolver")
    return tmp_path


# --- positive ---


def test_passes_when_every_route_resolves(repo: Path) -> None:
    _skill(repo, "src/copilot-cli", "autoplan", "| Merge conflicts | Skill: merge-resolver |\n")
    result = _run(repo)
    assert result.returncode == EXIT_OK
    assert "[PASS]" in result.stdout


def test_passes_when_shipped_tree_has_no_routes(repo: Path) -> None:
    assert _run(repo).returncode == EXIT_OK


# --- negative: the real drift shape ---


def test_fails_when_shipped_tree_dropped_the_routed_skill(repo: Path) -> None:
    _skill(repo, "src/copilot-cli", "autoplan", "| Merge conflicts | Skill: merge-resolver |\n")
    _drop(repo, "src/copilot-cli", "merge-resolver")

    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert "src/copilot-cli/skills/autoplan/SKILL.md:1" in result.stdout
    assert "merge-resolver" in result.stdout
    assert 'Task(subagent_type="<name>")' in result.stdout


def test_reports_every_offending_line(repo: Path) -> None:
    _skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "| a | Skill: merge-resolver |\n\n| b | Skill: merge-resolver |\n",
    )
    _drop(repo, "src/copilot-cli", "merge-resolver")

    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert result.stdout.count("routes to 'Skill: merge-resolver'") == 2


def test_scans_reference_files_not_just_skill_md(repo: Path) -> None:
    reference = repo / "src/copilot-cli/skills/autoplan/references/routes.md"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text("Skill: merge-resolver\n", encoding="utf-8")
    _drop(repo, "src/copilot-cli", "merge-resolver")

    assert _run(repo).returncode == EXIT_DRIFT


# --- edge: precision guards ---


def test_ignores_a_name_that_is_not_a_canonical_skill(repo: Path) -> None:
    """`Skill: create ...` is an English verb in a checklist, not a route."""
    _skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "- [ ] Skill: create `.claude/skills/NAME/tests/test_x.py`\n",
    )
    assert _run(repo).returncode == EXIT_OK


def test_ignores_backtick_fenced_blocks(repo: Path) -> None:
    _skill(repo, "src/copilot-cli", "autoplan", "```text\nSkill: merge-resolver\n```\n")
    _drop(repo, "src/copilot-cli", "merge-resolver")
    assert _run(repo).returncode == EXIT_OK


def test_ignores_tilde_fenced_blocks(repo: Path) -> None:
    _skill(repo, "src/copilot-cli", "autoplan", "~~~\nSkill: merge-resolver\n~~~\n")
    _drop(repo, "src/copilot-cli", "merge-resolver")
    assert _run(repo).returncode == EXIT_OK


def test_ignores_inline_code_span(repo: Path) -> None:
    _skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "Write the literal `Skill: merge-resolver` to disable it.\n",
    )
    _drop(repo, "src/copilot-cli", "merge-resolver")
    assert _run(repo).returncode == EXIT_OK


def test_canonical_tree_is_not_itself_gated(repo: Path) -> None:
    """Canonical may route to a skill the shipped tree drops. It is not shipped."""
    _skill(repo, ".claude", "autoplan", "| Merge conflicts | Skill: merge-resolver |\n")
    _drop(repo, "src/copilot-cli", "merge-resolver")
    assert _run(repo).returncode == EXIT_OK


def test_line_numbers_survive_a_preceding_fenced_block(repo: Path) -> None:
    _skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "```\nfiller\n```\n| Merge conflicts | Skill: merge-resolver |\n",
    )
    _drop(repo, "src/copilot-cli", "merge-resolver")

    result = _run(repo)
    assert result.returncode == EXIT_DRIFT
    assert "SKILL.md:4" in result.stdout


# --- config errors (ADR-035) ---


def test_config_error_when_canonical_tree_is_absent(tmp_path: Path) -> None:
    assert _run(tmp_path).returncode == EXIT_CONFIG


def test_config_error_when_shipped_tree_is_absent(tmp_path: Path) -> None:
    _skill(tmp_path, ".claude", "autoplan")
    assert _run(tmp_path).returncode == EXIT_CONFIG


# --- regression ---


def test_the_live_repository_satisfies_the_invariant() -> None:
    """Guards the autoplan route fix that shipped alongside this gate."""
    assert _run(REPO_ROOT).returncode == EXIT_OK
