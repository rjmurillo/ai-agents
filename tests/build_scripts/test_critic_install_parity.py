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

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "build" / "scripts" / "detect_agent_drift.py"

_spec = importlib.util.spec_from_file_location("detect_agent_drift", _SCRIPT)
assert _spec is not None and _spec.loader is not None
drift = importlib.util.module_from_spec(_spec)
sys.modules["detect_agent_drift"] = drift
_spec.loader.exec_module(drift)

_TEMPLATES = REPO_ROOT / "templates" / "agents"
_CLAUDE_INSTALL = REPO_ROOT / ".claude" / "agents"
_GITHUB_INSTALL = REPO_ROOT / ".github" / "agents"
_CRITIC_GITHUB = _GITHUB_INSTALL / "critic.agent.md"


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
    """`.claude/agents/critic.md` and `.github/agents/critic.agent.md` must not drift."""
    result = _critic_install_result()
    assert result.status == "OK", (
        f"critic install drift: status={result.status!r}, "
        f"similarity={result.overall_similarity}, "
        f"drifting_sections={result.drifting_sections}"
    )


def test_github_critic_carries_asymmetry_framing() -> None:
    """The deployed GitHub critic copy must carry the reviewer-asymmetry framing."""
    text = _CRITIC_GITHUB.read_text(encoding="utf-8")
    hits = text.lower().count("asymmetry")
    assert hits >= 2, (
        f".github/agents/critic.agent.md has {hits} 'asymmetry' hits; "
        "expected the reviewer-asymmetry framing from the canonical template"
    )
