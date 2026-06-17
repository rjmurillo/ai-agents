"""Regression test for issue #2641: critic install-copy parity.

The hand-maintained ``.github/agents/critic.agent.md`` drifted from the canonical
``.claude/agents/critic.md`` (which carries the reviewer-asymmetry framing landed
by PR #1894 / #2239). The drift detector's install comparison reported 0.0%
similarity for critic, but install drift is advisory by default, so CI did not
fail. This test pins the reconciled state: the critic install copies MUST stay in
semantic parity (no drift) and the GitHub copy MUST carry the asymmetry framing.

If a future edit lets the two copies diverge again, this test fails immediately
instead of waiting for an advisory drift report nobody reads.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_PATH = str(REPO_ROOT / "build" / "scripts")

sys.path.insert(0, _SCRIPTS_PATH)
try:
    import detect_agent_drift as drift
except ImportError as e:
    raise ImportError("Failed to import detect_agent_drift from build/scripts") from e
finally:
    if _SCRIPTS_PATH in sys.path:
        sys.path.remove(_SCRIPTS_PATH)

_TEMPLATES = REPO_ROOT / "templates" / "agents"
_CLAUDE_INSTALL = REPO_ROOT / ".claude" / "agents"
_GITHUB_INSTALL = REPO_ROOT / ".github" / "agents"
_CRITIC_GITHUB = _GITHUB_INSTALL / "critic.agent.md"
_CRITIC_CLAUDE = _CLAUDE_INSTALL / "critic.md"


def _critic_install_result() -> object:
    """Run the install comparison scoped to the critic family."""
    results = drift.run_install_detection(
        _TEMPLATES,
        _CLAUDE_INSTALL,
        _GITHUB_INSTALL,
        threshold=80,
        restrict_to=frozenset({"critic"}),
    )
    matches = [r for r in results if r.agent_name == "critic"]
    assert matches, "critic must be in the shared-template install comparison set"
    return matches[0]


def test_critic_install_copies_are_in_parity() -> None:
    """`.claude/agents/critic.md` and `.github/agents/critic.agent.md` must not drift.

    The section-based comparison in ``compare_agent`` uses legacy section names
    (e.g., 'Core Mission', 'Key Responsibilities') that do not appear in the
    reconciled critic files, which use the asymmetry-era structure ('Reviewer
    Asymmetry', 'Core Behavior', etc.). When no sections match, the comparison
    defaults to 100% and 'OK', bypassing the semantic check.

    To guard against body drift, this test performs a full-content comparison
    after frontmatter removal using the same Jaccard similarity measure. The
    threshold of 90% ensures meaningful parity while allowing minor formatting
    differences.
    """
    result = _critic_install_result()
    assert result.status == "OK", (
        f"critic install drift: status={result.status!r}, "
        f"similarity={result.overall_similarity}, "
        f"drifting_sections={result.drifting_sections}"
    )

    claude_body = drift.remove_yaml_frontmatter(
        _CRITIC_CLAUDE.read_text(encoding="utf-8")
    )
    github_body = drift.remove_yaml_frontmatter(
        _CRITIC_GITHUB.read_text(encoding="utf-8")
    )
    body_similarity = drift.calculate_similarity(
        drift.normalize_content(claude_body),
        drift.normalize_content(github_body),
    )
    assert body_similarity >= 90.0, (
        f"critic full-body similarity is {body_similarity}%, expected >= 90%; "
        "the install copies have drifted semantically"
    )


def test_github_critic_carries_asymmetry_framing() -> None:
    """The deployed GitHub critic copy must carry the reviewer-asymmetry framing.

    The threshold of 5 guards against partial erosion: the reconciled file has 7
    occurrences (section header, multiple inline references), so requiring at least
    5 ensures the core framing cannot be mostly removed without CI failure.
    """
    text = _CRITIC_GITHUB.read_text(encoding="utf-8")
    hits = text.lower().count("asymmetry")
    assert hits >= 5, (
        f".github/agents/critic.agent.md has {hits} 'asymmetry' hits; "
        "expected >= 5 to guard the reviewer-asymmetry framing from the canonical template"
    )
