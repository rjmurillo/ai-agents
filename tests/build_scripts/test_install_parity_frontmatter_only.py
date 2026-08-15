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
        ("src/claude/critic.md", HAND_MAINTAINED_VARIANT),
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

    def test_frontmatter_deletion_in_generated_files_passes(
        self, parity_repo: Path
    ) -> None:
        """Removing model: from generated files must not require sibling co-change."""
        for rel in _GENERATED_TOUCHED:
            (parity_repo / rel).write_text(FRONTMATTER_WITHOUT_MODEL)
        _run_git(parity_repo, "add", "-A")

        violations = vip.find_violations(
            _GENERATED_TOUCHED, repo_root=parity_repo, base="HEAD"
        )
        assert violations == [], f"Expected no violations, got: {violations}"

    def test_frontmatter_addition_in_generated_files_passes(
        self, parity_repo: Path
    ) -> None:
        """Adding a frontmatter key to generated files passes."""
        # First remove model: and commit
        for rel in _GENERATED_TOUCHED:
            (parity_repo / rel).write_text(FRONTMATTER_WITHOUT_MODEL)
        _run_git(parity_repo, "add", "-A")
        _run_git(parity_repo, "commit", "-q", "-m", "remove model")

        # Now add a different key (frontmatter-only change from new base)
        added = FRONTMATTER_WITHOUT_MODEL.replace(
            "description: Review critic agent",
            "description: Review critic agent\nversion: 2.0",
        )
        for rel in _GENERATED_TOUCHED:
            (parity_repo / rel).write_text(added)
        _run_git(parity_repo, "add", "-A")

        violations = vip.find_violations(
            _GENERATED_TOUCHED, repo_root=parity_repo, base="HEAD"
        )
        assert violations == []

    def test_body_section_change_still_fails(self, parity_repo: Path) -> None:
        """A body-section edit in generated files must still require co-change."""
        for rel in _GENERATED_TOUCHED:
            (parity_repo / rel).write_text(BODY_EDITED)
        _run_git(parity_repo, "add", "-A")

        violations = vip.find_violations(
            _GENERATED_TOUCHED, repo_root=parity_repo, base="HEAD"
        )
        assert len(violations) == 1
        assert violations[0].name == "critic"

    def test_mixed_diff_frontmatter_plus_body_still_fails(
        self, parity_repo: Path
    ) -> None:
        """Frontmatter removal + body edit must still fail."""
        mixed = FRONTMATTER_WITHOUT_MODEL.replace(
            "You are a constructive reviewer.",
            "You are a constructive reviewer who stress-tests."
        )
        for rel in _GENERATED_TOUCHED:
            (parity_repo / rel).write_text(mixed)
        _run_git(parity_repo, "add", "-A")

        violations = vip.find_violations(
            _GENERATED_TOUCHED, repo_root=parity_repo, base="HEAD"
        )
        assert len(violations) == 1

    def test_hand_maintained_member_blocks_bypass(
        self, parity_repo: Path
    ) -> None:
        """If a hand-maintained member is also touched, bypass does not fire."""
        touched = _GENERATED_TOUCHED + [".claude/agents/critic.md"]
        for rel in touched:
            (parity_repo / rel).write_text(FRONTMATTER_WITHOUT_MODEL)
        _run_git(parity_repo, "add", "-A")

        violations = vip.find_violations(
            touched, repo_root=parity_repo, base="HEAD"
        )
        # The hand-maintained carve-out won't fire (not ALL are hand-maintained).
        # The frontmatter bypass won't fire (has a hand-maintained member).
        # But since .claude/agents/critic.md IS in the group, it might still
        # pass via the hand-maintained carve-out if all touched ARE hand-maintained.
        # Here: mixed set, so neither fires. Violation expected.
        # Actually: the hand-maintained carve-out fires if ALL touched are
        # hand-maintained. Here 2 of 3 are generated, so it won't fire.
        # Result: violation.
        assert len(violations) == 1


class TestFrontmatterOnlyFailsClosed:
    """The bypass fails closed when the property cannot be established."""

    def test_no_base_ref_fails_closed(self, parity_repo: Path) -> None:
        """An invalid base ref must fail closed."""
        for rel in _GENERATED_TOUCHED:
            (parity_repo / rel).write_text(FRONTMATTER_WITHOUT_MODEL)
        _run_git(parity_repo, "add", "-A")

        violations = vip.find_violations(
            _GENERATED_TOUCHED, repo_root=parity_repo, base="nonexistent-ref"
        )
        assert len(violations) == 1

    def test_preamble_change_fails_closed(self, parity_repo: Path) -> None:
        """A preamble change (not frontmatter, not H2) still fails."""
        changed_preamble = FRONTMATTER_WITH_MODEL.replace(
            "Preamble text.", "Different preamble text."
        )
        for rel in _GENERATED_TOUCHED:
            (parity_repo / rel).write_text(changed_preamble)
        _run_git(parity_repo, "add", "-A")

        violations = vip.find_violations(
            _GENERATED_TOUCHED, repo_root=parity_repo, base="HEAD"
        )
        assert len(violations) == 1
