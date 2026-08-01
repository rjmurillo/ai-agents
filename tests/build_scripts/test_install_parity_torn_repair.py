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
        text=True,
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
        ("src/claude/alpha.md", hand),
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
def test_torn_group_repair_is_not_a_violation(torn_repo: Path) -> None:
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


# Negative: a genuinely forgotten install copy is still caught.
def test_forgotten_install_copy_still_fails(torn_repo: Path) -> None:
    # The template gains a section the hand-maintained copies never got.
    _apply_repair(torn_repo, "\n## Budget\n\nCap at 5.\n\n## Novel\n\nNew.\n")
    touched = [
        "templates/agents/alpha.shared.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ]
    violations = vip.find_violations(
        touched, repo_root=torn_repo, base="HEAD"
    )
    assert len(violations) == 1
    assert ".claude/agents/alpha.md" in violations[0].missing
    assert "src/claude/alpha.md" in violations[0].missing


# Negative: a changed section whose text disagrees is caught.
def test_diverging_section_body_still_fails(torn_repo: Path) -> None:
    _apply_repair(torn_repo, "\n## Budget\n\nCap at 99.\n")
    touched = [
        "templates/agents/alpha.shared.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ]
    violations = vip.find_violations(
        touched, repo_root=torn_repo, base="HEAD"
    )
    assert len(violations) == 1


# Edge: unrelated pre-existing drift in an untouched section is tolerated.
def test_unrelated_preexisting_drift_does_not_block_repair(
    torn_repo: Path,
) -> None:
    # The hand-maintained copies carry an extra section nobody is changing
    # (Issue #4082 drift). The repair must still pass.
    for rel in (".claude/agents/alpha.md", "src/claude/alpha.md"):
        (torn_repo / rel).write_text(
            "# alpha\n\n## Budget\n\nCap at 5.\n\n## Stale\n\nOld drift.\n"
        )
    _run_git(torn_repo, "add", "-A")
    _run_git(torn_repo, "commit", "-q", "-m", "drift")
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


# Edge: without a base there is no "before", so the gate fails closed.
def test_no_base_fails_closed(torn_repo: Path) -> None:
    _apply_repair(torn_repo)
    touched = [
        "templates/agents/alpha.shared.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ]
    violations = vip.find_violations(touched, repo_root=torn_repo, base=None)
    assert len(violations) == 1


# Edge: an unresolvable base fails closed rather than passing.
def test_unresolvable_base_fails_closed(torn_repo: Path) -> None:
    _apply_repair(torn_repo)
    touched = [
        "templates/agents/alpha.shared.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ]
    violations = vip.find_violations(
        touched, repo_root=torn_repo, base="no-such-ref-zzqx"
    )
    assert len(violations) == 1


# Edge: frontmatter differences must not defeat the section comparison.
def test_frontmatter_differences_are_ignored(torn_repo: Path) -> None:
    for rel in (".claude/agents/alpha.md", "src/claude/alpha.md"):
        (torn_repo / rel).write_text(
            "---\nname: alpha\nmodel: opus\n---\n\n"
            "# alpha\n\n## Budget\n\nCap at 5.\n"
        )
    _run_git(torn_repo, "add", "-A")
    _run_git(torn_repo, "commit", "-q", "-m", "frontmatter")
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


# Edge: the hand-maintained-only carve-out is unaffected by this change.
def test_hand_maintained_only_carve_out_still_applies(torn_repo: Path) -> None:
    violations = vip.find_violations(
        [".claude/agents/alpha.md"], repo_root=torn_repo, base="HEAD"
    )
    assert violations == []


# --- Parser soundness of the section model ------------------------------
#
# The carve-out above is only as trustworthy as its section model. Each test
# below pins one way that model could be fooled into vouching for a change it
# never actually verified. All of them must fail closed.

_LAGGING = (
    "templates/agents/alpha.shared.md",
    "src/copilot-cli/agents/alpha.agent.md",
    "src/vs-code-agents/alpha.agent.md",
)
_TOUCHED = list(_LAGGING)


def _write_lagging(repo: Path, text: str) -> None:
    for rel in _LAGGING:
        (repo / rel).write_text(text)


def _amend_base(repo: Path) -> None:
    """Fold the current tree into the base commit."""
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "--amend", "--no-edit")


def _set_hand_copies(repo: Path, text: str) -> None:
    for rel in (
        ".claude/agents/alpha.md",
        "src/claude/alpha.md",
        ".github/agents/alpha.agent.md",
    ):
        (repo / rel).write_text(text)
    _amend_base(repo)


# Negative: a preamble edit cannot ride along with a verified section repair.
def test_preamble_change_riding_along_fails_closed(torn_repo: Path) -> None:
    _write_lagging(torn_repo, "# alpha v2\n\n## Budget\n\nCap at 5.\n")
    violations = vip.find_violations(_TOUCHED, repo_root=torn_repo, base="HEAD")
    assert violations != []


# Negative: a deleted section cannot ride along with a verified repair.
def test_section_deletion_riding_along_fails_closed(torn_repo: Path) -> None:
    _write_lagging(torn_repo, "# alpha\n\n## Extra\n\nx.\n")
    _amend_base(torn_repo)
    _write_lagging(torn_repo, "# alpha\n\n## Budget\n\nCap at 5.\n")
    violations = vip.find_violations(_TOUCHED, repo_root=torn_repo, base="HEAD")
    assert violations != []


# Edge: a fenced ``## `` is sample text, not a heading, and must not shadow
# the real section of the same name.
def test_fenced_heading_is_not_a_section(torn_repo: Path) -> None:
    body = "# alpha\n\n## Budget\n\nExample:\n\n```md\n## Budget\n\nsample\n```\n"
    _set_hand_copies(torn_repo, body)
    _write_lagging(torn_repo, body)
    violations = vip.find_violations(_TOUCHED, repo_root=torn_repo, base="HEAD")
    assert violations == []


# Negative: a repeated heading makes the flat section map lossy, so the
# carve-out must refuse to vouch rather than compare the surviving copy.
def test_duplicate_heading_fails_closed(torn_repo: Path) -> None:
    body = "# alpha\n\n## Budget\n\nCap at 5.\n\n## Budget\n\nAgain.\n"
    _set_hand_copies(torn_repo, body)
    _write_lagging(torn_repo, body)
    violations = vip.find_violations(_TOUCHED, repo_root=torn_repo, base="HEAD")
    assert violations != []


# Negative: an unterminated fence swallows the rest of the document.
def test_unterminated_fence_fails_closed(torn_repo: Path) -> None:
    body = "# alpha\n\n## Budget\n\n```md\nno closing fence\n"
    _set_hand_copies(torn_repo, body)
    _write_lagging(torn_repo, body)
    violations = vip.find_violations(_TOUCHED, repo_root=torn_repo, base="HEAD")
    assert violations != []


# Edge: frontmatter is per-harness, so a change to it is not a body change
# and must not make the repair look unverifiable.
def test_reference_frontmatter_change_is_ignored(torn_repo: Path) -> None:
    _write_lagging(torn_repo, "---\nmodel: a\n---\n# alpha\n")
    _amend_base(torn_repo)
    _write_lagging(
        torn_repo, "---\nmodel: b\n---\n# alpha\n\n## Budget\n\nCap at 5.\n"
    )
    violations = vip.find_violations(_TOUCHED, repo_root=torn_repo, base="HEAD")
    assert violations == []


# Negative: when the reference's only change is frontmatter, nothing in the
# section model changed, so the carve-out has nothing to verify against the
# missing siblings and must refuse rather than vouch vacuously.
def test_frontmatter_only_change_fails_closed(torn_repo: Path) -> None:
    body = "---\nmodel: a\n---\n# alpha\n\n## Budget\n\nCap at 5.\n"
    _set_hand_copies(torn_repo, body)
    _write_lagging(torn_repo, body)
    _amend_base(torn_repo)
    _write_lagging(
        torn_repo, "---\nmodel: b\n---\n# alpha\n\n## Budget\n\nCap at 5.\n"
    )
    violations = vip.find_violations(_TOUCHED, repo_root=torn_repo, base="HEAD")
    assert violations != []


# Negative: the carve-out must not launder a regression. A diff that ADDS one
# section (which the carve-out can verify) while EDITING another that already
# existed at base drags the reference BACKWARDS onto whatever the stale
# missing siblings say. Content then agrees, but only because the canonical
# was degraded. The added section alone must not vouch for the edited one.
def test_body_edit_riding_along_with_addition_fails_closed(
    torn_repo: Path,
) -> None:
    _set_hand_copies(
        torn_repo, "# alpha\n\n## Budget\n\nCap at 5.\n\n## Extra\n\nx.\n"
    )
    _write_lagging(torn_repo, "# alpha\n\n## Budget\n\nCap at 15.\n")
    _amend_base(torn_repo)
    _write_lagging(
        torn_repo, "# alpha\n\n## Budget\n\nCap at 5.\n\n## Extra\n\nx.\n"
    )
    violations = vip.find_violations(_TOUCHED, repo_root=torn_repo, base="HEAD")
    assert violations != []
