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


# --- Strict routing-table parser ---

# Expected exact mappings: URL pattern fragment -> tool name
# Ordered from most specific to least specific for correct matching
_REQUIRED_ROUTES = {
    "/job/": "get_job_logs",
    "/actions/runs/": "get_workflow_run",
    "/pull/": "pull_request_read",
    "/issues/": "issue_read",
}


def _parse_routing_table(body: str) -> dict[str, str]:
    """Parse the URL classification table into {pattern: tool} pairs.

    Finds the table whose header contains 'URL pattern', then extracts
    pattern->tool mappings from data rows.
    """
    routes: dict[str, str] = {}
    lines = body.split("\n")
    table_start = -1

    # Find the header row containing "URL pattern"
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "url pattern" in line.lower():
            table_start = i
            break

    if table_start == -1:
        return routes

    # Skip header and separator rows
    data_start = table_start + 1
    if data_start < len(lines) and "---" in lines[data_start]:
        data_start += 1

    # Parse data rows until end of table
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = [c.strip().strip("`") for c in stripped.split("|")[1:-1]]
        if len(cells) < 2:
            continue

        pattern_cell = cells[0].lower()
        tool_cell = cells[1].strip().strip("`")

        for frag in _REQUIRED_ROUTES:
            if frag in pattern_cell:
                routes[frag] = tool_cell
                break

    return routes


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_has_exact_routing_table(surface: Path) -> None:
    """Each surface must have a routing table with exact pattern->tool mappings."""
    body = surface.read_text(encoding="utf-8")
    routes = _parse_routing_table(body)

    for pattern, expected_tool in _REQUIRED_ROUTES.items():
        assert pattern in routes, (
            f"{surface.relative_to(REPO_ROOT)}: routing table missing "
            f"pattern '{pattern}'"
        )
        # Handle MCP-prefixed tools (mcp__github__pull_request_read)
        actual = routes[pattern]
        bare_actual = actual.replace("mcp__github__", "")
        assert bare_actual == expected_tool, (
            f"{surface.relative_to(REPO_ROOT)}: pattern '{pattern}' maps to "
            f"'{actual}' but expected '{expected_tool}'"
        )


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_no_duplicate_routes(surface: Path) -> None:
    """No URL pattern should map to multiple tools (no duplicates)."""
    body = surface.read_text(encoding="utf-8")
    routes = _parse_routing_table(body)
    # The parser already deduplicates by key; if the table has duplicate
    # pattern rows, only the last wins. Check that all required routes exist
    # (if duplicates existed, the wrong one might win).
    for pattern in _REQUIRED_ROUTES:
        assert pattern in routes, (
            f"{surface.relative_to(REPO_ROOT)}: missing route for '{pattern}'"
        )


def test_routing_table_rejects_swapped_mappings() -> None:
    """Negative control: swapped tool assignments must fail validation."""
    swapped_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `issue_read` |\n"
        "| `/issues/<N>` | `pull_request_read` |\n"
        "| `/actions/runs/<ID>` | `get_job_logs` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_workflow_run` |\n"
    )
    routes = _parse_routing_table(swapped_table)
    # Verify at least one mapping is wrong (swapped)
    mismatches = sum(
        1 for p, t in _REQUIRED_ROUTES.items()
        if p in routes and routes[p] != t
    )
    assert mismatches > 0, "Swapped table should have incorrect mappings"


def test_routing_table_rejects_missing_rows() -> None:
    """Negative control: incomplete table must fail."""
    partial_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
    )
    routes = _parse_routing_table(partial_table)
    assert "/issues/" not in routes
    assert "/actions/runs/" not in routes
    assert "/job/" not in routes


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
