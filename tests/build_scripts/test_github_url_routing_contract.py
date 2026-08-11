# taste-lint: ignore file-size
# Reason: comprehensive routing contract test suite; splitting scatters helpers.
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

import re
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
        marker in frontmatter.lower() for marker in ("web_fetch", "webfetch", "websearch")
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


def _try_fence_close(ln: str, fence_char: str, fence_len: int) -> bool:
    """Return True if *ln* is a valid CommonMark fence closer for the given opener."""
    close_match = re.match(r"^(\s*)((`{3,})|(~{3,}))\s*$", ln)
    if not close_match:
        return False
    close_ch = close_match.group(3)[0] if close_match.group(3) else "~"
    close_len = len(close_match.group(3) or close_match.group(4))
    return close_ch == fence_char and close_len >= fence_len


def _try_fence_open(stripped_ln: str) -> tuple[str, int] | None:
    """If *stripped_ln* starts a CommonMark fence, return (char, length)."""
    open_match = re.match(r"^((`{3,})|(~{3,}))", stripped_ln)
    if not open_match:
        return None
    ch = open_match.group(2)[0] if open_match.group(2) else "~"
    length = len(open_match.group(2) or open_match.group(3))
    return ch, length


_BLOCKQUOTE_MARKER = re.compile(r"^ {0,3}>[ \t]?")


def _strip_blockquote_markers(line: str) -> str:
    """Strip CommonMark blockquote markers while preserving inner indentation.

    Each marker is ``>`` plus at most one following space, so a blockquoted
    indented code block (``>     code``) keeps the four spaces that mark it as
    code. :func:`_strip_blockquote` eats all whitespace after the marker and
    must not be used for code-context detection.
    """
    previous = None
    while previous != line:
        previous = line
        line = _BLOCKQUOTE_MARKER.sub("", line, count=1)
    return line


def _compute_operative_lines(lines: list[str]) -> list[bool]:
    """Determine which lines are in operative (non-code, non-comment) context.

    CommonMark-compliant: tracks fence opener type/length, requires matching
    closer. Handles multi-line HTML comments and 4-space indented code.
    Blockquote markers are normalized away first, so a fence or indented code
    block inside a blockquote hides its content the same as an unquoted one.
    """
    in_html_comment = False
    fence_char: str | None = None
    fence_len: int = 0
    operative = [True] * len(lines)
    for idx, ln in enumerate(lines):
        content = _strip_blockquote_markers(ln)
        stripped_ln = content.strip()
        # HTML comment handling (may span multiple lines)
        if in_html_comment:
            operative[idx] = False
            if "-->" in ln:
                in_html_comment = False
            continue
        if "<!--" in ln:
            if "-->" not in ln[ln.index("<!--") + 4 :]:
                in_html_comment = True
                operative[idx] = False
            continue
        # Fenced code blocks
        if fence_char is not None:
            if _try_fence_close(content, fence_char, fence_len):
                fence_char = None
                fence_len = 0
            operative[idx] = False
            continue
        opener = _try_fence_open(stripped_ln)
        if opener:
            fence_char, fence_len = opener
            operative[idx] = False
            continue
        # 4-space/tab indented code block
        if re.match(r"^(?:    |\t)", content):
            operative[idx] = False
    return operative


def _strip_blockquote(line: str) -> str:
    """Strip blockquote prefix (> ) from a line if present.

    Table-row detection only. Use :func:`_strip_blockquote_markers` for any
    code-context decision: this helper discards the indentation that
    distinguishes a blockquoted code block from blockquoted prose.
    """
    if line.strip().startswith(">"):
        return re.sub(r"^(\s*>\s*)+", "", line)
    return line


def _parse_routing_table(body: str) -> tuple[dict[str, list[str]], list[str]]:
    """Parse ALL URL classification tables in the document.

    Returns (multimap, all_patterns) where multimap is {pattern: [tool, ...]}
    and all_patterns is every normalized pattern found (including alternatives).
    Preserves EVERY data row and every alternative to enable strict validation.
    Parses all tables (not just first) so duplicates across tables are caught.
    Skips tables inside fenced code blocks (``` or ~~~), 4-space/tab indented
    code blocks, and HTML comments (<!-- ... -->).
    """
    routes: dict[str, list[str]] = {}
    all_patterns: list[str] = []
    lines = body.split("\n")

    operative = _compute_operative_lines(lines)

    i = 0
    while i < len(lines):
        line = lines[i]
        # Strip blockquote prefix for table detection (nested blockquotes
        # with visible table rows are operative).
        effective_line = _strip_blockquote(line)
        if (
            operative[i]
            and effective_line.strip().startswith("|")
            and "url pattern" in effective_line.lower()
        ):
            # Found a table header - REQUIRE delimiter row (---|---) next
            data_start = i + 1
            if data_start < len(lines):
                delim_line = _strip_blockquote(lines[data_start]).strip()
                if re.match(r"\|[\s:]*-{3,}", delim_line):
                    data_start += 1
                else:
                    # No valid delimiter row → not a real table
                    i += 1
                    continue
            else:
                i += 1
                continue
            # Parse data rows
            for j in range(data_start, len(lines)):
                # A code fence, indented block, or HTML comment ends the table.
                # Markdown stops the table there, so rows after the
                # interruption belong to a separate block and must not
                # complete this one.
                if not operative[j]:
                    i = j
                    break
                raw_row = lines[j]
                # Strip blockquote prefix
                row_content = _strip_blockquote(raw_row)
                stripped = row_content.strip()
                if not stripped.startswith("|"):
                    i = j
                    break
                # Filter inline HTML comments from row content
                stripped = re.sub(r"<!--.*?-->", "", stripped)
                cells = [c.strip().replace("`", "") for c in stripped.split("|")[1:-1]]
                if len(cells) < 2:
                    all_patterns.append("<malformed>")
                    continue

                raw_pattern = cells[0]
                tool_cell = cells[1].strip().strip("`")

                # Parse ALL alternatives separated by " or "
                alternatives = [a.strip().strip("`").lower() for a in raw_pattern.split(" or ")]

                # Store EVERY alternative -> tool mapping (not just first)
                for alt in alternatives:
                    routes.setdefault(alt, []).append(tool_cell)

                # Record all alternatives for validation
                all_patterns.extend(alternatives)
            else:
                i = len(lines)
        else:
            i += 1

    return routes, all_patterns


# Allowed non-URL alternatives and known non-canonical path rows
# Each maps to its expected tool binding.
_ALLOWED_NON_PATH_ALTS: dict[str, str] = {
    "pr #n": "pull_request_read",
    "issue #n": "issue_read",
    "ci overview": "list_workflow_runs",
}
_ALLOWED_EXTRA_PATHS: dict[str, str] = {
    "/actions (list)": "list_workflow_runs",
    "/actions": "list_workflow_runs",
}


def _validate_routing_table(
    routes: dict[str, list[str]],
    all_patterns: list[str],
    surface_label: str,
    *,
    mcp_prefixed: bool = False,
) -> list[str]:
    """Shared strict validator for routing table correctness.

    Checks:
    - Every canonical pattern has exactly one row with correct tool
    - No duplicate rows for same pattern
    - No noncanonical path-like patterns (rejects /commits/<SHA>, /foo, etc.)
    - No malformed rows (single-cell)
    - All alternatives must be either canonical or explicitly allowed
    """
    errors: list[str] = []

    # Check canonical patterns
    for pattern, bare_tool in _CANONICAL_PATTERNS.items():
        expected = (_MCP_PREFIX + bare_tool) if mcp_prefixed else bare_tool
        tools = routes.get(pattern)
        if not tools:
            errors.append(f"{surface_label}: routing table missing pattern '{pattern}'")
            continue
        if len(tools) > 1:
            errors.append(f"{surface_label}: duplicate rows for '{pattern}': {tools}")
            continue
        if tools[0] != expected:
            errors.append(
                f"{surface_label}: pattern '{pattern}' maps to '{tools[0]}', expected '{expected}'"
            )

    # Reject malformed rows
    if "<malformed>" in all_patterns:
        errors.append(f"{surface_label}: malformed single-cell row in table")

    # Reject noncanonical alternatives and validate tool bindings
    for alt in all_patterns:
        if alt == "<malformed>":
            continue
        if alt in _CANONICAL_PATTERNS:
            continue
        if alt in _ALLOWED_NON_PATH_ALTS:
            # Validate tool binding
            expected_tool = _ALLOWED_NON_PATH_ALTS[alt]
            actual_tools = routes.get(alt, [])
            if not actual_tools:
                # Alt is secondary in an " or " split - check parent row
                continue
            pfx = (_MCP_PREFIX + expected_tool) if mcp_prefixed else expected_tool
            if len(actual_tools) > 1:
                errors.append(
                    f"{surface_label}: duplicate associations for alias '{alt}': {actual_tools}"
                )
            elif actual_tools and actual_tools[0] != pfx:
                errors.append(
                    f"{surface_label}: non-path alias '{alt}' maps to "
                    f"'{actual_tools[0]}', expected '{pfx}'"
                )
            continue
        if alt in _ALLOWED_EXTRA_PATHS:
            expected_tool = _ALLOWED_EXTRA_PATHS[alt]
            actual_tools = routes.get(alt, [])
            if actual_tools:
                pfx = (_MCP_PREFIX + expected_tool) if mcp_prefixed else expected_tool
                if len(actual_tools) > 1:
                    errors.append(
                        f"{surface_label}: duplicate associations"
                        f" for extra path '{alt}': {actual_tools}"
                    )
                elif actual_tools[0] != pfx:
                    errors.append(
                        f"{surface_label}: extra path '{alt}' maps to "
                        f"'{actual_tools[0]}', expected '{pfx}'"
                    )
            continue
        # Non-path text (no leading /) that is NOT in the allowlist → reject
        if not alt.startswith("/"):
            errors.append(f"{surface_label}: unrecognized non-path alternative '{alt}' in table")
            continue
        # Path-like but not canonical → reject
        errors.append(f"{surface_label}: noncanonical path pattern '{alt}' in table")

    return errors


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_has_exact_routing_table(surface: Path) -> None:
    """Each surface must have a routing table with exact pattern->tool mappings."""
    body = surface.read_text(encoding="utf-8")
    routes, all_pats = _parse_routing_table(body)
    label = str(surface.relative_to(REPO_ROOT))
    mcp = _is_claude_surface(surface)
    errors = _validate_routing_table(routes, all_pats, label, mcp_prefixed=mcp)
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_no_duplicate_routes(surface: Path) -> None:
    """No URL pattern should map to multiple tools (no duplicates)."""
    body = surface.read_text(encoding="utf-8")
    routes, _ = _parse_routing_table(body)
    label = str(surface.relative_to(REPO_ROOT))
    for pattern, tools in routes.items():
        assert len(tools) == 1, f"{label}: duplicate rows for '{pattern}': {tools}"


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
    routes, all_pats = _parse_routing_table(swapped_table)
    errors = _validate_routing_table(routes, all_pats, "swapped-fixture")
    assert errors, "Swapped table must fail validation"


def test_routing_table_rejects_missing_rows() -> None:
    """Negative control: incomplete table must fail."""
    partial_table = "| URL pattern | Tool |\n|---|---|\n| `/pull/<N>` | `pull_request_read` |\n"
    routes, all_pats = _parse_routing_table(partial_table)
    errors = _validate_routing_table(routes, all_pats, "partial-fixture")
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
    routes, all_pats = _parse_routing_table(dup_table)
    errors = _validate_routing_table(routes, all_pats, "dup-fixture")
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
    routes, all_pats = _parse_routing_table(suffix_table)
    errors = _validate_routing_table(routes, all_pats, "suffix-fixture")
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
    routes, all_pats = _parse_routing_table(noncanon_table)
    errors = _validate_routing_table(routes, all_pats, "noncanon-fixture")
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
    routes, all_pats = _parse_routing_table(mcp_table)
    errors = _validate_routing_table(routes, all_pats, "mcp-fixture", mcp_prefixed=True)
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
    routes, all_pats = _parse_routing_table(mcp_table)
    errors = _validate_routing_table(routes, all_pats, "mcp-bare-fixture", mcp_prefixed=False)
    assert errors, "MCP-prefixed tools must fail when bare expected"


@pytest.mark.parametrize("surface", _SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_analyst_surface_uses_singular_job_path(surface: Path) -> None:
    """GitHub uses /job/<ID> (singular). Surfaces must not use /jobs/."""
    body = surface.read_text(encoding="utf-8")
    assert "/job/" in body, f"{surface.relative_to(REPO_ROOT)}: must use singular /job/<JID> path"
    assert "/jobs/" not in body, (
        f"{surface.relative_to(REPO_ROOT)}: uses /jobs/ but GitHub URLs use singular /job/<JID>"
    )


def test_routing_table_rejects_api_prefix() -> None:
    """Negative control: /api/pull/<N> is not canonical."""
    api_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/api/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes, all_pats = _parse_routing_table(api_table)
    errors = _validate_routing_table(routes, all_pats, "api-prefix-fixture")
    assert errors, "Non-canonical /api/pull/<N> must fail validation"


def test_routing_table_rejects_pull_latest() -> None:
    """Negative control: /pull/latest is not canonical."""
    latest_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/latest` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes, all_pats = _parse_routing_table(latest_table)
    errors = _validate_routing_table(routes, all_pats, "pull-latest-fixture")
    assert errors, "Non-canonical /pull/latest must fail validation"


def test_routing_table_rejects_extra_conflicting_row() -> None:
    """Negative control: extra row conflicting with canonical path rejected."""
    extra_table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/pull/<N>/files` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes, all_pats = _parse_routing_table(extra_table)
    errors = _validate_routing_table(routes, all_pats, "extra-row-fixture")
    assert errors, "Extra conflicting row must fail validation"


def test_routing_table_rejects_commits_sha() -> None:
    """Negative control: /commits/<SHA> is not a canonical route."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        "| `/commits/<SHA>` | `get_commit` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "commits-fixture")
    assert errors, "Non-canonical /commits/<SHA> must fail validation"


def test_routing_table_rejects_arbitrary_path() -> None:
    """Negative control: /foo is not a canonical route."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        "| `/foo` | `bar` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "foo-fixture")
    assert errors, "Non-canonical /foo must fail validation"


def test_routing_table_rejects_malformed_row() -> None:
    """Negative control: single-cell row must fail."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        "| malformed row |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "malformed-fixture")
    assert errors, "Malformed single-cell row must fail validation"


def test_routing_table_rejects_mixed_alternative() -> None:
    """Negative control: /pull/<N> or /pull/latest mixes canonical with noncanonical."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` or `/pull/latest` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "mixed-alt-fixture")
    assert errors, "Mixed canonical/noncanonical alternative must fail"


def test_routing_table_rejects_non_path_alternative() -> None:
    """Non-path alternative not in allowlist must be rejected."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` or run shell commands | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "non-path-alt")
    assert any("unrecognized non-path" in e for e in errors), f"Expected rejection: {errors}"


def test_routing_table_rejects_duplicate_across_tables() -> None:
    """Duplicate canonical pattern across two tables must be caught."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        "\nExtra:\n"
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `some_other_tool` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "dup-table")
    assert any("duplicate" in e for e in errors), f"Expected duplicate detection: {errors}"


def test_routing_table_rejects_wrong_extra_path_tool() -> None:
    """Extra path /actions (list) with wrong tool must be rejected."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        "| `/actions (list)` | `pull_request_read` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "wrong-extra")
    assert any("extra path" in e and "expected" in e for e in errors), (
        f"Expected binding error: {errors}"
    )


def test_routing_table_rejects_bare_alias_wrong_tool() -> None:
    """Bare non-path alias PR #N with arbitrary tool must be rejected."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        "| PR #N | `some_arbitrary_tool` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "wrong-alias")
    assert any("non-path alias" in e and "expected" in e for e in errors), (
        f"Expected binding error: {errors}"
    )


def test_routing_table_rejects_crossed_alternatives() -> None:
    """Crossed alias like '/pull/<N> or issue #N' must be rejected."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` or `issue #N` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "crossed")
    # "issue #n" maps to pull_request_read but should map to issue_read
    assert any("issue #n" in e.lower() and "expected" in e for e in errors), (
        f"Expected binding error for crossed alias: {errors}"
    )


def test_routing_table_rejects_duplicate_across_rows() -> None:
    """Second row with same /pull/<N> pattern must be caught as duplicate."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "dup-rows")
    assert any("duplicate" in e for e in errors), f"Expected duplicate error: {errors}"


def test_routing_multi_alternative_positive() -> None:
    """Valid multi-alternative row stores all alternatives."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` or `PR #N` | `pull_request_read` |\n"
        "| `/issues/<N>` or `issue #N` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `CI overview` | `list_workflow_runs` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "multi-alt")
    assert not errors, f"Valid multi-alt table should pass: {errors}"
    # All alternatives stored
    assert "pr #n" in routes
    assert "issue #n" in routes
    assert "ci overview" in routes


def test_routing_conflicting_duplicate_alias() -> None:
    """Same alias mapped correctly then incorrectly must be caught."""
    table = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` or `PR #N` | `pull_request_read` |\n"
        "| `/issues/<N>` or `issue #N` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        "| `PR #N` | `issue_read` |\n"
    )
    routes, all_pats = _parse_routing_table(table)
    errors = _validate_routing_table(routes, all_pats, "conflict-dup")
    assert any("duplicate" in e.lower() for e in errors), f"Expected duplicate: {errors}"


class TestRoutingMarkdownContext:
    """Tables inside non-operative Markdown contexts must be ignored."""

    VALID_TABLE = (
        "| URL pattern | Tool |\n"
        "|---|---|\n"
        "| `/pull/<N>` | `pull_request_read` |\n"
        "| `/issues/<N>` | `issue_read` |\n"
        "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
        "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
    )

    def test_backtick_fence_ignored(self) -> None:
        body = "```\n" + self.VALID_TABLE + "```\n"
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table inside backtick fence should be skipped"

    def test_tilde_fence_ignored(self) -> None:
        body = "~~~\n" + self.VALID_TABLE + "~~~\n"
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table inside tilde fence should be skipped"

    def test_indented_code_ignored(self) -> None:
        body = "".join("    " + ln for ln in self.VALID_TABLE.splitlines(keepends=True))
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table inside indented code should be skipped"

    def test_html_comment_ignored(self) -> None:
        body = "<!--\n" + self.VALID_TABLE + "-->\n"
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table inside HTML comment should be skipped"

    def test_visible_table_accepted(self) -> None:
        body = "## Routing\n\n" + self.VALID_TABLE
        routes, _ = _parse_routing_table(body)
        assert routes, "Visible table should be parsed"
        assert "/pull/<n>" in routes


class TestRoutingFenceBypassRegression:
    """CommonMark fence compliance: four-char, mixed type, short closer."""

    VALID_TABLE = TestRoutingMarkdownContext.VALID_TABLE

    def test_four_char_fence_ignored(self) -> None:
        """````python fence (4 backticks) must hide content."""
        body = "````\n" + self.VALID_TABLE + "````\n"
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table inside 4-char backtick fence should be skipped"

    def test_mixed_fence_types_not_closed(self) -> None:
        """Open with ``` close with ~~~ does NOT close the fence."""
        body = "```\n" + self.VALID_TABLE + "~~~\n"
        routes, _ = _parse_routing_table(body)
        assert not routes, "Tilde closer should not close backtick fence"

    def test_short_closer_not_closed(self) -> None:
        """Open with ```` close with ``` does NOT close (closer too short)."""
        body = "````\n" + self.VALID_TABLE + "```\n"
        routes, _ = _parse_routing_table(body)
        assert not routes, "Short closer should not close longer fence"

    def test_matching_closer_accepted(self) -> None:
        """Open with ```` close with ```` properly closes."""
        body = "````\n| hidden |\n````\n\n" + self.VALID_TABLE
        routes, _ = _parse_routing_table(body)
        assert routes, "Table after properly closed fence should be parsed"

    def test_html_comment_inline_filtered(self) -> None:
        """Inline <!-- comment --> in a data row filters that content."""
        body = (
            "| URL pattern | Tool |\n"
            "|---|---|\n"
            "| `/pull/<N>` <!-- hidden --> | `pull_request_read` |\n"
            "| `/issues/<N>` | `issue_read` |\n"
            "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
            "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        )
        routes, _ = _parse_routing_table(body)
        assert "/pull/<n>" in routes

    def test_missing_delimiter_row_rejected(self) -> None:
        """Table without --- delimiter row is not a valid table."""
        body = "| URL pattern | Tool |\n| `/pull/<N>` | `pull_request_read` |\n"
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table without delimiter row should not be parsed"

    def test_blockquote_table_visible(self) -> None:
        """> prefixed table rows are visible (nested blockquote)."""
        body = (
            "> | URL pattern | Tool |\n"
            "> |---|---|\n"
            "> | `/pull/<N>` | `pull_request_read` |\n"
            "> | `/issues/<N>` | `issue_read` |\n"
            "> | `/actions/runs/<ID>` | `get_workflow_run` |\n"
            "> | `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        )
        routes, _ = _parse_routing_table(body)
        assert routes, "Blockquote table should be parsed as visible"
        assert "/pull/<n>" in routes

    def test_blockquoted_fence_ignored(self) -> None:
        """Table inside a blockquoted fence (> ```) must be skipped."""
        body = (
            "> ```\n"
            + "".join("> " + ln for ln in self.VALID_TABLE.splitlines(keepends=True))
            + "> ```\n"
        )
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table inside blockquoted fence should be skipped"

    def test_blockquoted_tilde_fence_ignored(self) -> None:
        """Table inside a blockquoted tilde fence (> ~~~) must be skipped."""
        body = (
            "> ~~~\n"
            + "".join("> " + ln for ln in self.VALID_TABLE.splitlines(keepends=True))
            + "> ~~~\n"
        )
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table inside blockquoted tilde fence should be skipped"

    def test_nested_blockquoted_fence_ignored(self) -> None:
        """Table inside a doubly quoted fence (> > ```) must be skipped."""
        body = (
            "> > ```\n"
            + "".join("> > " + ln for ln in self.VALID_TABLE.splitlines(keepends=True))
            + "> > ```\n"
        )
        routes, _ = _parse_routing_table(body)
        assert not routes, "Table inside nested blockquoted fence should be skipped"

    def test_blockquoted_indented_code_ignored(self) -> None:
        """Table indented four spaces inside a blockquote must be skipped."""
        body = "".join(">     " + ln for ln in self.VALID_TABLE.splitlines(keepends=True))
        routes, _ = _parse_routing_table(body)
        assert not routes, "Blockquoted indented-code table should be skipped"

    def test_blockquoted_fence_does_not_hide_later_table(self) -> None:
        """A closed blockquoted fence must not suppress a later real table."""
        body = (
            "> ```\n"
            "> | URL pattern | Tool |\n"
            "> |---|---|\n"
            "> | `/pull/<N>` | `evil_tool` |\n"
            "> ```\n\n" + self.VALID_TABLE
        )
        routes, _ = _parse_routing_table(body)
        assert routes.get("/pull/<n>") == ["pull_request_read"]

    def test_fence_interrupting_table_ends_it(self) -> None:
        """Rows after a fence inside a table do not complete that table."""
        body = (
            "| URL pattern | Tool |\n"
            "|---|---|\n"
            "| `/pull/<N>` | `pull_request_read` |\n"
            "```\n"
            "some code\n"
            "```\n"
            "| `/issues/<N>` | `issue_read` |\n"
            "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
            "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        )
        routes, _ = _parse_routing_table(body)
        assert routes == {"/pull/<n>": ["pull_request_read"]}

    def test_html_comment_interrupting_table_ends_it(self) -> None:
        """Rows after a multi-line HTML comment do not complete that table."""
        body = (
            "| URL pattern | Tool |\n"
            "|---|---|\n"
            "| `/pull/<N>` | `pull_request_read` |\n"
            "<!-- hidden\n"
            "still hidden -->\n"
            "| `/issues/<N>` | `issue_read` |\n"
            "| `/actions/runs/<ID>` | `get_workflow_run` |\n"
            "| `/actions/runs/<ID>/job/<JID>` | `get_job_logs` |\n"
        )
        routes, _ = _parse_routing_table(body)
        assert routes == {"/pull/<n>": ["pull_request_read"]}

    def test_table_after_interruption_parses_on_its_own_header(self) -> None:
        """A complete table following an interrupted one is still parsed."""
        body = (
            "| URL pattern | Tool |\n"
            "|---|---|\n"
            "| `/pull/<N>` | `evil_tool` |\n"
            "```\n"
            "code\n"
            "```\n\n" + self.VALID_TABLE
        )
        routes, _ = _parse_routing_table(body)
        assert routes["/pull/<n>"] == ["evil_tool", "pull_request_read"]
        assert "/actions/runs/<id>/job/<jid>" in routes

    def test_decoy_in_fence_no_contamination(self) -> None:
        """Hidden decoy table inside fence must not pollute later parse."""
        body = (
            "```\n"
            "| URL pattern | Tool |\n"
            "|---|---|\n"
            "| `/pull/<N>` | `evil_tool` |\n"
            "```\n\n" + self.VALID_TABLE
        )
        routes, _ = _parse_routing_table(body)
        assert routes.get("/pull/<n>") == ["pull_request_read"]
