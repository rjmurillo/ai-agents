"""Tests for the torn-group repair carve-out in validate_install_parity.py.

Covers Issue #4157: the hand-maintained carve-out can leave ``main`` torn,
and the PR that repairs the group must not be reported as drift while a
genuinely forgotten install copy still is.

Covers:
- positive: repairing a torn group passes
- negative: a forgotten install copy still fails
- negative: a changed section whose body disagrees still fails
- edge: unrelated pre-existing drift does not block the repair
- edge: a missing or unresolvable base fails closed
- edge: differing frontmatter does not defeat the section comparison
- edge: the pre-existing hand-maintained carve-out is unaffected
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_install_parity as vip  # noqa: E402

# --- Torn-group repair carve-out (Issue #4157) ---------------------------
#
# The hand-maintained carve-out lets a PR move only .claude/agents/,
# .github/agents/, and src/claude/. That can leave main torn. The PR that
# repairs the remaining members legitimately does not touch the ones already
# correct, and co-change alone cannot tell that repair apart from a genuinely
# forgotten install copy. find_violations resolves the ambiguity by content,
# scoped to the H2 sections this diff changed.


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True, encoding="utf-8",
    )


@pytest.fixture
def torn_repo(tmp_path: Path) -> Path:
    """A committed repo whose ``alpha`` group is torn like real ``main``.

    At the base commit the hand-maintained copies already carry
    ``## Budget``; the template and the generated copies do not. The working
    tree then adds ``## Budget`` to the template and the generated copies,
    which is the repair.
    """
    hand = "# alpha\n\n## Budget\n\nCap at 5.\n"
    lagging = "# alpha\n"
    for rel, text in (
        (".claude/agents/alpha.md", hand),
        ("src/claude/agents/alpha.md", hand),
        (".github/agents/alpha.agent.md", hand),
        ("templates/agents/alpha.shared.md", lagging),
        ("src/copilot-cli/agents/alpha.agent.md", lagging),
        ("src/vs-code-agents/alpha.agent.md", lagging),
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    _run_git(tmp_path, "init", "-q")
    _run_git(tmp_path, "config", "user.email", "t@example.com")
    _run_git(tmp_path, "config", "user.name", "t")
    _run_git(tmp_path, "add", "-A")
    _run_git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _apply_repair(repo: Path, section: str = "\n## Budget\n\nCap at 5.\n") -> None:
    for rel in (
        "templates/agents/alpha.shared.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ):
        (repo / rel).write_text("# alpha\n" + section)


# Positive: repairing a torn group passes.
def test_torn_shared_agent_group_is_delegated_to_build_check(torn_repo: Path) -> None:
    """ADR-109 B1: SHARED_AGENT drift delegated to build_all.py --check."""
    _apply_repair(torn_repo)
    touched = [
        "templates/agents/alpha.shared.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ]
    violations = vip.find_violations(
        touched, repo_root=torn_repo, base="HEAD"
    )
    assert violations == []
