"""Analyst agent must enforce PR identity gate and GitHub URL routing.

Two related defects corrected by issue #4221 and #4229:

- #4221: the research subagent substituted local branch content for a
  requested PR, reported findings as if they came from the PR, and the
  output was indistinguishable from a real review. The identity gate
  requirement stops this: the agent must reconcile API identity against
  local checkout before reporting, and stop on any mismatch.

- #4229: web_fetch on GitHub URLs is blocked by a pre-tool hook that
  redirects to context-mode tools that are not in the subagent's manifest.
  The routing rule must forbid web_fetch on GitHub URLs and name the
  supported alternative. If no supported path exists, the agent must stop
  with [BLOCKED], not fall back to priors.

These are structural tests against the agent definition file. They are not
behavioral tests (the agent is not invoked). The property being asserted is
that the instruction text is present and specific enough to close each defect:
a weaker instruction regresses the defect, so the tests measure the presence
of the specific guard language.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYST_AGENT_PATHS = (
    REPO_ROOT / "templates" / "agents" / "analyst.shared.md",
    REPO_ROOT / ".claude" / "agents" / "analyst.md",
    REPO_ROOT / ".github" / "agents" / "analyst.agent.md",
    REPO_ROOT / "src" / "claude" / "analyst.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "analyst.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "analyst.agent.md",
)
ANALYST_AGENT = REPO_ROOT / ".claude" / "agents" / "analyst.md"


def _analyst_text(path: Path = ANALYST_AGENT) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _agent_label(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


class TestGitHubURLRoutingRule:
    """The analyst agent must use declared GitHub tools, not web_fetch (#4229)."""

    def test_no_web_access_stated(self) -> None:
        text = _analyst_text()
        assert re.search(
            r"no\s+web\s+access", text, re.IGNORECASE
        ), (
            "analyst.md must state the analyst has 'no web access' "
            "(issue #4229: web_fetch is not available for GitHub URLs)"
        )

    def test_github_read_tools_declared(self) -> None:
        text = _analyst_text()
        assert "pull_request_read" in text, (
            "analyst.md must declare pull_request_read as the mechanism "
            "for retrieving GitHub PR data (issue #4229)"
        )

    def test_direct_retrieval_documented(self) -> None:
        text = _analyst_text()
        assert re.search(
            r"retrieve.*directly|directly.*retrieve|declared.*read\s+tools",
            text,
            re.IGNORECASE,
        ), (
            "analyst.md must document that GitHub data is retrieved directly "
            "via declared read tools (issue #4229)"
        )

    def test_blocked_fallback_for_github_urls(self) -> None:
        text = _analyst_text()
        assert "BLOCKED" in text, (
            "analyst.md must specify [BLOCKED] as the response when GitHub "
            "API is unreachable (issues #4221, #4229)"
        )


class TestPRIdentityGate:
    """The analyst agent must reconcile API identity before reporting PR findings (#4221)."""

    @pytest.mark.parametrize("agent_path", ANALYST_AGENT_PATHS)
    def test_identity_gate_section_present(self, agent_path: Path) -> None:
        text = _analyst_text(agent_path)
        label = _agent_label(agent_path)
        assert re.search(r"identity\s+gate", text, re.IGNORECASE), (
            f"{label} must contain a PR identity gate section "
            "(issue #4221: "
            "the agent reported findings attributed to the wrong PR)"
        )

    @pytest.mark.parametrize("agent_path", ANALYST_AGENT_PATHS)
    def test_head_sha_reconciliation_required(self, agent_path: Path) -> None:
        text = _analyst_text(agent_path)
        label = _agent_label(agent_path)
        assert "head_sha" in text or "headRefOid" in text, (
            f"{label} must name the head SHA field that must be reconciled "
            "against the local checkout (issue #4221)"
        )

    @pytest.mark.parametrize("agent_path", ANALYST_AGENT_PATHS)
    def test_mismatch_stops_report(self, agent_path: Path) -> None:
        text = _analyst_text(agent_path)
        label = _agent_label(agent_path)
        # The instruction must say to stop on mismatch, not continue.
        assert re.search(r"[Ss]top\b.*(mismatch|differ|diverge)", text) or re.search(
            r"(mismatch|differ|diverge).*(stop|error|blocked)", text, re.IGNORECASE
        ), (
            f"{label} must instruct the agent to stop on identity mismatch "
            "rather than mixing evidence from different work items (issue #4221)"
        )

    @pytest.mark.parametrize("agent_path", ANALYST_AGENT_PATHS)
    def test_no_substitution_instruction(self, agent_path: Path) -> None:
        text = _analyst_text(agent_path)
        label = _agent_label(agent_path)
        # The fix instruction must explicitly prohibit substituting local content.
        assert re.search(
            r"[Dd]o not substitute\s+local", text
        ), (
            f"{label} must explicitly forbid substituting local checkout "
            "content for the requested PR (issue #4221)"
        )

    @pytest.mark.parametrize("agent_path", ANALYST_AGENT_PATHS)
    def test_merge_commit_reconciliation_required(self, agent_path: Path) -> None:
        text = _analyst_text(agent_path)
        label = _agent_label(agent_path)
        assert "merge" in text.lower() and (
            "mergeCommit" in text or "merge_commit" in text or "mergeCommit.oid" in text
        ), (
            f"{label} must require reconciling a claimed merge commit "
            "against the API's merge commit field (issue #4221: the agent "
            "cited a merge commit that belonged to a different PR)"
        )
