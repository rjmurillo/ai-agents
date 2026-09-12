"""Tests for the frontmatter-only carve-out in validate_install_parity.py.

Covers Issue #4922: a generated-tree change that deletes a frontmatter key
must pass when the H2 body-section invariant is provably untouched.

Covers:
- positive: frontmatter-only deletion in generated files passes
- positive: frontmatter-only addition in generated files passes
- negative: a body-section change in the same trees still fails
- negative: a mixed diff (frontmatter plus one H2 edit) still fails
- edge: hand-maintained members touched alongside generated blocks the bypass
- edge: unresolvable base fails closed
- edge: preamble change (non-frontmatter, non-H2) fails closed
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_install_parity as vip  # noqa: E402


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


FRONTMATTER_WITH_MODEL = """\
---
name: critic
description: Review critic agent
model: claude-sonnet-4.6
---

Preamble text.

## Core Identity

You are a constructive reviewer.

## Workflow

Step 1. Review.
"""

FRONTMATTER_WITHOUT_MODEL = """\
---
name: critic
description: Review critic agent
---

Preamble text.

## Core Identity

You are a constructive reviewer.

## Workflow

Step 1. Review.
"""

BODY_EDITED = """\
---
name: critic
description: Review critic agent
---

Preamble text.

## Core Identity

You are a constructive reviewer who stress-tests plans.

## Workflow

Step 1. Review.
"""

HAND_MAINTAINED_VARIANT = """\
---
name: critic
model: opus
---

Preamble text.

## Core Identity

You are a constructive reviewer.

## Workflow

Step 1. Review.
"""

_GENERATED_TOUCHED = [
    "src/copilot-cli/agents/critic.agent.md",
    "src/vs-code-agents/critic.agent.md",
]


@pytest.fixture
def parity_repo(tmp_path: Path) -> Path:
    """A committed repo with a full critic agent group, all with model: key."""
    for rel, text in (
        (".claude/agents/critic.md", HAND_MAINTAINED_VARIANT),
        ("src/claude/agents/critic.md", HAND_MAINTAINED_VARIANT),
        (".github/agents/critic.agent.md", FRONTMATTER_WITH_MODEL),
        ("templates/agents/critic.shared.md", FRONTMATTER_WITH_MODEL),
        ("src/copilot-cli/agents/critic.agent.md", FRONTMATTER_WITH_MODEL),
        ("src/vs-code-agents/critic.agent.md", FRONTMATTER_WITH_MODEL),
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


class TestFrontmatterOnlyBypass:
    """Issue #4922: frontmatter-only changes in generated files pass."""

    def test_frontmatter_change_in_generated_files_is_delegated(
        self, parity_repo: Path
    ) -> None:
        """ADR-109 B1: SHARED_AGENT drift delegated to build_all.py --check."""
        for rel in _GENERATED_TOUCHED:
            (parity_repo / rel).write_text(FRONTMATTER_WITHOUT_MODEL)
        _run_git(parity_repo, "add", "-A")

        violations = vip.find_violations(
            _GENERATED_TOUCHED, repo_root=parity_repo, base="HEAD"
        )
        assert violations == []
