"""Contract tests: analyst agent prompts must route GitHub URLs through
declared read-only tools, not web_fetch or external skills (issue #4032).

The analyst has structured GitHub read tools (pull_request_read, issue_read,
list_workflow_runs, etc.) and uses them directly. It has no web access and
must not attempt HTTP fetches of GitHub URLs.

Surfaces checked:
  - templates/agents/analyst.shared.md (canonical source)
  - .claude/agents/analyst.md (Claude Code install copy)
  - src/claude/analyst.md (Claude vendor copy)
  - src/copilot-cli/agents/analyst.agent.md (generated Copilot CLI copy)
  - src/vs-code-agents/analyst.agent.md (generated VS Code copy)
  - .github/agents/analyst.agent.md (GitHub Copilot copy)

Negative control: a template body without the routing guidance fails the
check. This ensures the test cannot silently pass if the guidance is removed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Required phrases that signal correct GitHub URL routing guidance.
_ROUTING_MARKER = "pull_request_read"
_NO_WEB_ACCESS = "no web access"

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
    """Each agent surface must reference pull_request_read for GitHub URLs."""
    assert surface.is_file(), f"surface missing: {surface}"
    body = surface.read_text(encoding="utf-8")
    assert _ROUTING_MARKER in body, (
        f"{surface.relative_to(REPO_ROOT)} missing '{_ROUTING_MARKER}'. "
        "The analyst agent must use declared GitHub read tools for URL routing."
    )


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_forbids_web_access_for_github_urls(surface: Path) -> None:
    """Each agent surface must state the analyst has no web access."""
    assert surface.is_file(), f"surface missing: {surface}"
    body = surface.read_text(encoding="utf-8").lower()
    assert _NO_WEB_ACCESS in body, (
        f"{surface.relative_to(REPO_ROOT)} missing '{_NO_WEB_ACCESS}'. "
        "Without this, agents may attempt web_fetch on github.com URLs."
    )


def test_template_without_routing_guidance_fails_check() -> None:
    """Negative control: a template body missing the routing marker fails."""
    body_without_guidance = """\
## Tools

**Read/Grep/Glob**: code analysis (read-only)
**WebSearch/WebFetch**: research best practices, docs, patterns
**Bash**: git commands, `gh issue`, `gh api` (via github skill scripts)
"""
    assert _ROUTING_MARKER not in body_without_guidance, (
        "Negative control broken: the incomplete template unexpectedly contains "
        f"'{_ROUTING_MARKER}'. Update the negative control body."
    )
    assert _NO_WEB_ACCESS not in body_without_guidance.lower(), (
        "Negative control broken: the incomplete template unexpectedly contains "
        f"'{_NO_WEB_ACCESS}'. Update the negative control body."
    )


def test_canonical_template_webfetch_note_restricts_to_non_github() -> None:
    """When no web tool is in frontmatter, assert prose states no web access.

    If web_fetch IS present, require '(non-GitHub URLs only)' annotation.
    """
    template = REPO_ROOT / "templates" / "agents" / "analyst.shared.md"
    assert template.is_file()
    body = template.read_text(encoding="utf-8")
    parts = body.split("---", 2)
    frontmatter = parts[1] if len(parts) >= 3 else ""
    has_webfetch_tool = any(
        marker in frontmatter.lower()
        for marker in ("web_fetch", "webfetch", "websearch")
    )
    if not has_webfetch_tool:
        assert "analyst has no web access" in body, (
            "templates/agents/analyst.shared.md: when no web tool is in the "
            "frontmatter, the prose must state 'analyst has no web access'."
        )
        return
    assert "non-GitHub URLs only" in body, (
        "templates/agents/analyst.shared.md: the WebSearch/WebFetch tool line must "
        "include '(non-GitHub URLs only)' to clearly scope what web_fetch is for."
    )


# --- Actions URL routing controls ---


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_routes_actions_urls(surface: Path) -> None:
    """Each surface must map Actions URLs to get_workflow_run or get_job_logs."""
    body = surface.read_text(encoding="utf-8")
    assert "get_workflow_run" in body, (
        f"{surface.relative_to(REPO_ROOT)}: must declare get_workflow_run "
        f"for /actions/runs/<ID> URLs"
    )
    assert "get_job_logs" in body, (
        f"{surface.relative_to(REPO_ROOT)}: must declare get_job_logs "
        f"for job log retrieval"
    )


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_has_url_classification_table(surface: Path) -> None:
    """Each surface must have a URL-to-tool classification table."""
    body = surface.read_text(encoding="utf-8")
    # Check for the routing table with at least PR and Actions entries
    assert "/pull/" in body and "/actions/" in body, (
        f"{surface.relative_to(REPO_ROOT)}: must include URL classification "
        f"table with /pull/ and /actions/ patterns"
    )


def test_actions_url_without_routing_fails() -> None:
    """Negative control: text with GitHub tools but no Actions mapping fails."""
    body = "Use pull_request_read for PRs. The analyst has no web access."
    assert "get_workflow_run" not in body
    assert "/actions/" not in body


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_uses_singular_job_path(surface: Path) -> None:
    """GitHub uses /job/<ID> (singular). Surfaces must not use /jobs/."""
    body = surface.read_text(encoding="utf-8")
    assert "/job/" in body, (
        f"{surface.relative_to(REPO_ROOT)}: must use singular /job/<JID> path"
    )
    assert "/jobs/" not in body, (
        f"{surface.relative_to(REPO_ROOT)}: uses /jobs/ but GitHub URLs use "
        f"singular /job/<JID>"
    )
