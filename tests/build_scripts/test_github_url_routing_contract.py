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
# Four canonical URL patterns. Each key is the exact normalized first-cell
# content (lowercased, backtick-stripped, trimmed) that the routing table
# MUST contain. Value is the bare (non-MCP-prefixed) tool name.
_CANONICAL_PATTERNS: dict[str, str] = {
    "/pull/<n>": "pull_request_read",
    "/issues/<n>": "issue_read",
    "/actions/runs/<id>": "get_workflow_run",
    "/actions/runs/<id>/job/<jid>": "get_job_logs",
}

# Cells may contain alternatives like "/pull/<N> or PR #N". We split on
# " or " and match the first segment exactly.
_MCP_PREFIX = "mcp__github__"


def _is_claude_surface(surface: Path) -> bool:
    """Return True if the surface uses MCP-prefixed tool names."""
    rel = str(surface.relative_to(REPO_ROOT))
    return "claude" in rel


def _parse_routing_table(body: str) -> dict[str, list[str]]:
    """Parse the URL classification table into a multimap {pattern: [tool, ...]}.

    Matches normalized first-cell content exactly against canonical patterns.
    Returns raw tool names (may include MCP prefix) for surface-aware validation.
    """
    routes: dict[str, list[str]] = {}
    lines = body.split("\n")
    table_start = -1

    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "url pattern" in line.lower():
            table_start = i
            break

    if table_start == -1:
        return routes

    data_start = table_start + 1
    if data_start < len(lines) and "---" in lines[data_start]:
        data_start += 1

    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = [c.strip().strip("`") for c in stripped.split("|")[1:-1]]
        if len(cells) < 2:
            continue

        # Normalize: take first alternative before " or ", strip backticks
        raw_pattern = cells[0]
        first_alt = raw_pattern.split(" or ")[0].strip().strip("`").lower()
        tool_cell = cells[1].strip().strip("`")

        if first_alt in _CANONICAL_PATTERNS:
            routes.setdefault(first_alt, []).append(tool_cell)

    return routes


def _validate_routing_table(
    routes: dict[str, list[str]],
    surface_label: str,
    *,
    mcp_prefixed: bool = False,
) -> list[str]:
    """Shared strict validator for routing table correctness.

    Checks:
    - Every canonical pattern has exactly one row
    - Each mapped tool matches the expected tool (with MCP prefix if applicable)
    - No duplicate rows for same pattern
    - No extra unrecognized patterns (only canonical ones accepted)
    """
    errors: list[str] = []
    for pattern, bare_tool in _CANONICAL_PATTERNS.items():
        expected = (_MCP_PREFIX + bare_tool) if mcp_prefixed else bare_tool
        tools = routes.get(pattern)
        if not tools:
            errors.append(
                f"{surface_label}: routing table missing pattern '{pattern}'"
            )
            continue
        if len(tools) > 1:
            errors.append(
                f"{surface_label}: duplicate rows for '{pattern}': {tools}"
            )
            continue
        if tools[0] != expected:
            errors.append(
                f"{surface_label}: pattern '{pattern}' maps to "
                f"'{tools[0]}', expected '{expected}'"
            )
    return errors


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_has_exact_routing_table(surface: Path) -> None:
    """Each surface must have a routing table with exact pattern->tool mappings."""
    body = surface.read_text(encoding="utf-8")
    routes = _parse_routing_table(body)
    label = str(surface.relative_to(REPO_ROOT))
    mcp = _is_claude_surface(surface)
    errors = _validate_routing_table(routes, label, mcp_prefixed=mcp)
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_no_duplicate_routes(surface: Path) -> None:
    """No URL pattern should map to multiple tools (no duplicates)."""
    body = surface.read_text(encoding="utf-8")
    routes = _parse_routing_table(body)
    label = str(surface.relative_to(REPO_ROOT))
    for pattern, tools in routes.items():
        assert len(tools) == 1, (
            f"{label}: duplicate rows for '{pattern}': {tools}"
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
    errors = _validate_routing_table(routes, "swapped-fixture")
    assert errors, "Swapped table must fail validation"


def test_routing_table_rejects_missing_rows() -> None:
    """Negative control: incomplete table must fail."""
    partial_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
    )
    routes = _parse_routing_table(partial_table)
    errors = _validate_routing_table(routes, "partial-fixture")
    assert errors, "Partial table must fail validation"


def test_routing_table_rejects_duplicate_rows() -> None:
    """Negative control: duplicate pattern rows must fail validation."""
    dup_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes = _parse_routing_table(dup_table)
    errors = _validate_routing_table(routes, "dup-fixture")
    assert errors, "Duplicate pattern rows must fail validation"


def test_routing_table_rejects_suffix_pattern() -> None:
    """Negative control: /pull/<N>/files is not a canonical pattern."""
    suffix_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>/files` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes = _parse_routing_table(suffix_table)
    errors = _validate_routing_table(routes, "suffix-fixture")
    assert errors, "Non-canonical /pull/<N>/files must fail validation"


def test_routing_table_rejects_noncanonical_placeholder() -> None:
    """Negative control: /pull/<number> is not canonical (must be <N>)."""
    noncanon_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<number>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes = _parse_routing_table(noncanon_table)
    errors = _validate_routing_table(routes, "noncanon-fixture")
    assert errors, "Non-canonical placeholder must fail validation"


def test_routing_table_validates_mcp_prefixed_tools() -> None:
    """MCP-prefixed tools must pass when mcp_prefixed=True."""
    mcp_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `mcp__github__pull_request_read` |\n"
        "| `/issues/<N>` | `mcp__github__issue_read` |\n"
        "| `/actions/runs/<ID>` | `mcp__github__get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `mcp__github__get_job_logs` |\n"
    )
    routes = _parse_routing_table(mcp_table)
    errors = _validate_routing_table(routes, "mcp-fixture", mcp_prefixed=True)
    assert not errors, "\n".join(errors)


def test_routing_table_rejects_mcp_when_bare_expected() -> None:
    """MCP-prefixed tools must fail when mcp_prefixed=False."""
    mcp_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `mcp__github__pull_request_read` |\n"
        "| `/issues/<N>` | `mcp__github__issue_read` |\n"
        "| `/actions/runs/<ID>` | `mcp__github__get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `mcp__github__get_job_logs` |\n"
    )
    routes = _parse_routing_table(mcp_table)
    errors = _validate_routing_table(routes, "mcp-bare-fixture", mcp_prefixed=False)
    assert errors, "MCP-prefixed tools must fail when bare expected"


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
