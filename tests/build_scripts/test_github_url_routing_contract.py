"""Contract tests: analyst agent prompts must route GitHub URLs through
github-url-intercept, never web_fetch (issue #4032).

The context-mode external hook intercepts web_fetch calls to GitHub URLs and
redirects agents to context-mode_ctx_* tools that are not in the subagent
toolset. This causes research subagents to stall with zero findings after
wasting 431+ seconds.

Fix: every analyst agent surface must contain explicit GitHub URL routing
guidance that names github-url-intercept as the required path and forbids
web_fetch for GitHub URLs.

Surfaces checked:
  - templates/agents/analyst.shared.md (canonical source)
  - .claude/agents/analyst.md (Claude Code install copy)
  - src/claude/analyst.md (Claude vendor copy)
  - src/copilot-cli/agents/analyst.agent.md (generated Copilot CLI copy)
  - src/vs-code-agents/analyst.agent.md (generated VS Code copy)

Negative control: a template body without the routing guidance fails the
check. This ensures the test cannot silently pass if the guidance is removed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Required phrases that signal correct GitHub URL routing guidance.
_ROUTING_MARKER = "github-url-intercept"
_NO_WEBFETCH_FOR_GITHUB = "Never call `web_fetch` on GitHub URLs"

# All surfaces that MUST carry the routing contract.
_SURFACES = [
    REPO_ROOT / "templates" / "agents" / "analyst.shared.md",
    REPO_ROOT / ".claude" / "agents" / "analyst.md",
    REPO_ROOT / ".github" / "agents" / "analyst.agent.md",
    REPO_ROOT / "src" / "claude" / "analyst.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "analyst.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "analyst.agent.md",
]


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_contains_github_url_routing(surface: Path) -> None:
    """Each agent surface must reference github-url-intercept for GitHub URLs."""
    assert surface.is_file(), f"surface missing: {surface}"
    body = surface.read_text(encoding="utf-8")
    assert _ROUTING_MARKER in body, (
        f"{surface.relative_to(REPO_ROOT)} missing '{_ROUTING_MARKER}'. "
        "The analyst agent must route GitHub URLs through github-url-intercept "
        "to prevent context-mode hook interception (issue #4032)."
    )


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_forbids_webfetch_for_github_urls(surface: Path) -> None:
    """Each agent surface must explicitly forbid web_fetch for GitHub URLs."""
    assert surface.is_file(), f"surface missing: {surface}"
    body = surface.read_text(encoding="utf-8")
    assert _NO_WEBFETCH_FOR_GITHUB in body, (
        f"{surface.relative_to(REPO_ROOT)} missing explicit ban on web_fetch for GitHub URLs. "
        "Without this, agents may call web_fetch on github.com URLs and trigger the "
        "context-mode reroute deadlock (issue #4032)."
    )


def test_template_without_routing_guidance_fails_check() -> None:
    """Negative control: a template body missing the routing marker fails.

    If this test itself fails, the detection logic is broken and the positive
    tests above cannot be trusted.
    """
    body_without_guidance = """\
## Tools

**Read/Grep/Glob**: code analysis (read-only)
**WebSearch/WebFetch**: research best practices, docs, patterns
**Bash**: git commands, `gh issue`, `gh api` (via github skill scripts)
**github skill**: unified GitHub operations
"""
    assert _ROUTING_MARKER not in body_without_guidance, (
        "Negative control broken: the incomplete template unexpectedly contains "
        f"'{_ROUTING_MARKER}'. Update the negative control body."
    )
    assert _NO_WEBFETCH_FOR_GITHUB not in body_without_guidance, (
        "Negative control broken: the incomplete template unexpectedly contains "
        f"'{_NO_WEBFETCH_FOR_GITHUB}'. Update the negative control body."
    )


def test_canonical_template_webfetch_note_restricts_to_non_github() -> None:
    """The template's WebSearch/WebFetch line must scope to non-GitHub URLs."""
    template = REPO_ROOT / "templates" / "agents" / "analyst.shared.md"
    assert template.is_file()
    body = template.read_text(encoding="utf-8")
    assert "non-GitHub URLs only" in body, (
        "templates/agents/analyst.shared.md: the WebSearch/WebFetch tool line must "
        "include '(non-GitHub URLs only)' to clearly scope what web_fetch is for."
    )
