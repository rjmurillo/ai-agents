# taste-lint: ignore file-size
# Reason: this is a comprehensive contract-test suite; splitting would scatter
# related fixtures/helpers across files, harming cohesion. Issue #3779.
"""Structural guards for the analyst tool and delegation contract."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_CANONICAL = REPO_ROOT / "src" / "claude" / "analyst.md"
CLAUDE_RUNTIME = REPO_ROOT / ".claude" / "agents" / "analyst.md"
SHARED_TEMPLATE = REPO_ROOT / "templates" / "agents" / "analyst.shared.md"
COPILOT_RUNTIME = REPO_ROOT / ".github" / "agents" / "analyst.agent.md"
COPILOT_GENERATED = REPO_ROOT / "src" / "copilot-cli" / "agents" / "analyst.agent.md"
VSCODE_GENERATED = REPO_ROOT / "src" / "vs-code-agents" / "analyst.agent.md"
TOOLSETS = REPO_ROOT / "templates" / "toolsets.yaml"
ORCHESTRATOR_CONTRACTS = (
    REPO_ROOT / "src" / "claude" / "orchestrator.md",
    REPO_ROOT / ".claude" / "agents" / "orchestrator.md",
    REPO_ROOT / "templates" / "agents" / "orchestrator.shared.md",
    REPO_ROOT / ".github" / "agents" / "orchestrator.agent.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "orchestrator.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "orchestrator.agent.md",
)

READ_ONLY_SERENA_OPERATIONS = frozenset(
    {
        "find_declaration",
        "find_implementations",
        "find_referencing_symbols",
        "find_symbol",
        "get_diagnostics_for_file",
        "get_symbols_overview",
        "initial_instructions",
        "list_memories",
        "read_memory",
    }
)
CLAUDE_ALLOWED_TOOLS = frozenset(
    {
        "Glob",
        "Grep",
        "Read",
        "mcp__github__issue_read",
        "mcp__github__pull_request_read",
        "mcp__github__get_file_contents",
        "mcp__github__list_commits",
        "mcp__github__list_workflow_runs",
        "mcp__github__get_workflow_run",
        "mcp__github__get_job_logs",
        "mcp__context7__get_library_docs",
        "mcp__context7__resolve_library_id",
        "mcp__deepwiki__read_wiki_contents",
        "mcp__deepwiki__read_wiki_structure",
        *(f"mcp__serena__{operation}" for operation in READ_ONLY_SERENA_OPERATIONS),
    }
)
PLATFORM_ALLOWED_TOOLS = frozenset(
    {
        "cognitionai/deepwiki/*",
        "context7/*",
        "github/issue_read",
        "github/pull_request_read",
        "github/get_file_contents",
        "github/list_commits",
        "github/list_workflow_runs",
        "github/get_workflow_run",
        "github/get_job_logs",
        "read",
        "search",
        *(f"serena/{operation}" for operation in READ_ONLY_SERENA_OPERATIONS),
    }
)
UNSAFE_TOOL_PREFIXES = (
    "$toolset:",
    "agent",
    "bash",
    "cloudmcp-manager",
    "edit",
    "execute",
    "memory",
    "notebookedit",
    "perplexity",
    "shell",
    "skill",
    "task",
    "vscode",
    "web",
    "write",
)
UNSAFE_SERENA_OPERATIONS = frozenset(
    {
        "delete_memory",
        "edit_memory",
        "insert_after_symbol",
        "insert_before_symbol",
        "onboarding",
        "rename_memory",
        "rename_symbol",
        "replace_content",
        "replace_in_files",
        "replace_symbol_body",
        "safe_delete_symbol",
        "write_memory",
    }
)


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) == 3, f"{path} must contain YAML frontmatter"
    parsed = yaml.safe_load(parts[1])
    assert isinstance(parsed, dict), f"{path} frontmatter must be a mapping"
    return parsed


def _tool_list(metadata: dict[str, object], key: str, source: Path) -> list[str]:
    tools = metadata.get(key)
    assert isinstance(tools, list) and tools, f"{source} must declare a non-empty {key}"
    assert all(isinstance(tool, str) for tool in tools), f"{source} {key} must contain strings"
    return tools


def _assert_read_only_tools(tools: list[str], allowed_tools: frozenset[str]) -> None:
    assert tools, "analyst must declare tools explicitly"
    assert len(tools) == len(set(tools)), "analyst tool list contains duplicates"
    assert set(tools) == allowed_tools, (
        f"analyst tool contract mismatch: "
        f"unexpected={sorted(set(tools) - allowed_tools)}, "
        f"missing={sorted(allowed_tools - set(tools))}"
    )
    for tool in tools:
        normalized = tool.casefold()
        base = normalized.split("(", 1)[0]
        assert not base.startswith(UNSAFE_TOOL_PREFIXES), f"analyst grants unsafe tool: {tool}"

        operation = None
        if normalized.startswith("serena/"):
            operation = normalized.removeprefix("serena/")
        elif normalized.startswith("mcp__serena__"):
            operation = normalized.removeprefix("mcp__serena__")
        if operation is not None:
            assert operation not in UNSAFE_SERENA_OPERATIONS
            assert operation in READ_ONLY_SERENA_OPERATIONS, (
                f"analyst grants unreviewed Serena tool: {tool}"
            )


def test_claude_declares_explicit_read_only_tools() -> None:
    canonical_tools = _tool_list(_frontmatter(CLAUDE_CANONICAL), "tools", CLAUDE_CANONICAL)
    runtime_tools = _tool_list(_frontmatter(CLAUDE_RUNTIME), "tools", CLAUDE_RUNTIME)

    _assert_read_only_tools(canonical_tools, CLAUDE_ALLOWED_TOOLS)
    assert not any(tool.startswith("github/") for tool in canonical_tools)
    assert runtime_tools == canonical_tools


@pytest.mark.parametrize("key", ["tools_copilot", "tools_vscode"])
def test_shared_template_declares_platform_read_only_tools(key: str) -> None:
    tools = _tool_list(_frontmatter(SHARED_TEMPLATE), key, SHARED_TEMPLATE)

    _assert_read_only_tools(tools, PLATFORM_ALLOWED_TOOLS)


@pytest.mark.parametrize(
    ("output", "template_key"),
    [
        (COPILOT_RUNTIME, "tools_copilot"),
        (COPILOT_GENERATED, "tools_copilot"),
        (VSCODE_GENERATED, "tools_vscode"),
    ],
)
def test_generated_tool_contract_matches_template(output: Path, template_key: str) -> None:
    template_tools = _tool_list(_frontmatter(SHARED_TEMPLATE), template_key, SHARED_TEMPLATE)
    output_tools = _tool_list(_frontmatter(output), "tools", output)

    assert output_tools == template_tools


def test_prompt_routes_execution_to_an_execution_agent() -> None:
    claude = CLAUDE_CANONICAL.read_text(encoding="utf-8")
    shared = SHARED_TEMPLATE.read_text(encoding="utf-8")

    assert "This agent cannot invoke skills" in claude
    assert "Command routing (required)" in claude
    assert "The orchestrator must run shell commands" in claude
    assert "retrieves GitHub issue, PR, and CI context directly" in claude
    assert "Command routing (required)" in shared
    assert "The orchestrator must run shell commands" in shared
    assert "retrieves GitHub issue, PR, and CI context directly" in shared
    assert "Issue #3918 tracks adding structured read-only tooling" not in claude
    assert "Issue #3918 tracks adding structured read-only tooling" not in shared


def test_orchestrator_supplies_analyst_execution_context() -> None:
    for contract in ORCHESTRATOR_CONTRACTS:
        text = contract.read_text(encoding="utf-8")
        assert "### Analyst evidence handoff" in text, contract
        assert "Put the exact output, repository identity, branch, and head SHA" in text, contract
        # Orchestrator prefetches only shell/build/git/web, not GitHub/CI
        assert "shell/git/build output and unrestricted web evidence" in text, contract
        assert "Do not prefetch GitHub/CI" in text, contract
        # Analyst retrieves GitHub/CI directly
        assert "analyst retrieves structured GitHub and CI data directly" in text, contract
        assert "no shell or unrestricted web access" in text, contract
        assert "retrieve the named" in text, contract
        assert "evidence and re-delegate once" in text, contract


@pytest.mark.parametrize(
    ("tools", "allowed_tools"),
    [
        ([], PLATFORM_ALLOWED_TOOLS),
        (["Read", "Bash"], CLAUDE_ALLOWED_TOOLS),
        (["Read", "Bash(git status:*)"], CLAUDE_ALLOWED_TOOLS),
        (["Read", "Task"], CLAUDE_ALLOWED_TOOLS),
        (["Read", "NotebookEdit"], CLAUDE_ALLOWED_TOOLS),
        (["read", "agent"], PLATFORM_ALLOWED_TOOLS),
        (["read", "cloudmcp-manager/*"], PLATFORM_ALLOWED_TOOLS),
        (["read", "edit"], PLATFORM_ALLOWED_TOOLS),
        (["read", "edit_file"], PLATFORM_ALLOWED_TOOLS),
        (["read", "github/create_or_update_file"], PLATFORM_ALLOWED_TOOLS),
        (["read", "github.vscode-pull-request-github/*"], PLATFORM_ALLOWED_TOOLS),
        (["read", "memory"], PLATFORM_ALLOWED_TOOLS),
        (["read", "perplexity/*"], PLATFORM_ALLOWED_TOOLS),
        (["read", "$toolset:executor"], PLATFORM_ALLOWED_TOOLS),
        (["read", "serena/write_memory"], PLATFORM_ALLOWED_TOOLS),
        (["Read", "mcp__serena__replace_symbol_body"], CLAUDE_ALLOWED_TOOLS),
        (["read", "serena/*"], PLATFORM_ALLOWED_TOOLS),
        (["read", "skill"], PLATFORM_ALLOWED_TOOLS),
        (["read", "web"], PLATFORM_ALLOWED_TOOLS),
    ],
)
def test_read_only_guard_rejects_unsafe_negative_controls(
    tools: list[str], allowed_tools: frozenset[str]
) -> None:
    with pytest.raises(AssertionError):
        _assert_read_only_tools(tools, allowed_tools)


def test_executor_toolset_is_an_unsafe_negative_control() -> None:
    toolsets = yaml.safe_load(TOOLSETS.read_text(encoding="utf-8"))
    assert isinstance(toolsets, dict)
    executor = toolsets["executor"]
    assert isinstance(executor, dict)

    for key in ("tools_copilot", "tools_vscode"):
        tools = executor[key]
        assert isinstance(tools, list)
        with pytest.raises(AssertionError):
            _assert_read_only_tools(tools, PLATFORM_ALLOWED_TOOLS)


def test_reviewed_read_only_allowlists_are_inverted_controls() -> None:
    _assert_read_only_tools(list(CLAUDE_ALLOWED_TOOLS), CLAUDE_ALLOWED_TOOLS)
    _assert_read_only_tools(list(PLATFORM_ALLOWED_TOOLS), PLATFORM_ALLOWED_TOOLS)


# --- PR Retrieval Before BLOCKED Regression Tests ---

ALL_ANALYST_SURFACES = (
    REPO_ROOT / ".claude" / "agents" / "analyst.md",
    REPO_ROOT / "src" / "claude" / "analyst.md",
    REPO_ROOT / ".github" / "agents" / "analyst.agent.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "analyst.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "analyst.agent.md",
    REPO_ROOT / "templates" / "agents" / "analyst.shared.md",
)


@pytest.mark.parametrize("path", ALL_ANALYST_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_pull_request_read_declared(path: Path) -> None:
    """pull_request_read must be in every analyst surface."""
    assert "pull_request_read" in path.read_text(), (
        f"{path.relative_to(REPO_ROOT)}: pull_request_read not declared"
    )

# --- Section-aware validation helpers (shared by production tests and negative controls) ---


def _extract_blocked_section(text: str) -> str:
    """Extract the heading-delimited section containing [BLOCKED]."""
    idx = text.find("[BLOCKED]")
    if idx == -1:
        raise ValueError("No [BLOCKED] found in text")
    section_start = text.rfind("\n#", 0, idx)
    section_end = text.find("\n#", idx)
    return text[max(0, section_start):section_end if section_end != -1 else len(text)].lower()


def _check_blocked_conditional(section: str) -> str | None:
    """Return None if BLOCKED is properly conditional, else an error message.

    The conditional language must be bound directly to the [BLOCKED] clause:
    on the same line, or within the immediately preceding sentence (same
    paragraph, no blank line between).
    """
    conditional_words = ("only when", "only if", "only after")
    blocked_pos = section.find("[blocked]")
    if blocked_pos == -1:
        return "No [blocked] in section"

    # Get the line containing [blocked]
    line_start = section.rfind("\n", 0, blocked_pos) + 1
    blocked_line = section[line_start:section.find("\n", blocked_pos)]
    if any(w in blocked_line for w in conditional_words):
        return None

    # Check the preceding non-empty line (sentence may wrap)
    prev_end = line_start - 1
    if prev_end > 0:
        prev_start = section.rfind("\n", 0, prev_end) + 1
        prev_line = section[prev_start:prev_end]
        # Only accept if no blank line separates them
        if prev_line.strip() and any(w in prev_line for w in conditional_words):
            return None

    return "BLOCKED clause lacks conditional language (only when/if/after)"


_TOOL_NAMES = (
    "pull_request_read", "issue_read", "list_workflow_runs",
    "get_workflow_run", "get_job_logs",
)

_IMPERATIVES = re.compile(
    r"\b(call|use|invoke|attempt|retrieve\s+.*?(?:via|using|with))\b",
    re.IGNORECASE,
)

_NEGATIONS = re.compile(
    r"\b(do\s+not|don'?t|never|cannot|must\s+not|forbidden|"
    r"deprecated|was\s+deprecated|is\s+not|prohibited)\b",
    re.IGNORECASE,
)

_NON_DIRECTIVE = re.compile(
    r"(orchestrator|qa\s+agent|security\s+agent|implementer|"
    r"example:|e\.g\.|for example|"
    r"see\s+\w+\s+docs|endpoint\s+was)",
    re.IGNORECASE,
)


def _is_skippable_line(stripped: str, in_fence: bool) -> bool:
    """Return True if line is structural markup or inside a fenced block."""
    if in_fence:
        return True
    return (
        not stripped
        or stripped.startswith("|")
        or stripped.startswith(">")
        or stripped.startswith("#")
    )


def _line_has_tool_reference(line: str) -> bool:
    """Return True if line references a declared tool or 'declared tools'.

    Tool names inside double-quoted, single-quoted strings, or inline-code
    spans are NOT counted (they are examples).
    Bare backtick-wrapped tool names with imperative verbs in prose ARE valid.
    """
    # Strip quoted strings and inline-code spans (examples)
    stripped = re.sub(r'"[^"]*"', "", line)
    stripped = re.sub(r"'[^']*'", "", stripped)
    if any(t in stripped for t in _TOOL_NAMES):
        return True
    return "retrieve" in stripped.lower() and "declared" in stripped.lower()


def _is_affirmative_directive(line: str) -> bool:
    """Return True if line is an affirmative directive (not negated/example).

    Rejects if the imperative verb is inside an inline-code span (the entire
    directive is an example). Tool names in backticks with the verb in prose
    are normal markdown formatting and are accepted.
    """
    if _NON_DIRECTIVE.search(line):
        return False
    if _NEGATIONS.search(line):
        return False

    # Check if imperative verb exists in prose (outside inline-code spans)
    prose = re.sub(r"`[^`]*`", "", line)
    if _IMPERATIVES.search(prose):
        return True
    if "retrieval via declared tools" in prose.lower():
        return True
    return False


def _check_retrieval_precedes_blocked(section: str) -> str | None:
    """Return None if an affirmative retrieval directive precedes BLOCKED.

    Strict contract parser. Accepts ONLY lines where:
    1. The analyst is the actor (not orchestrator/other)
    2. An affirmative imperative verb directs tool usage
    3. The tool is a declared routing tool
    4. The line is NOT inside fenced-code blocks, inline-code, quotes, or tables
    5. No negation/deprecation/prohibition modifies the verb

    Rejects: quoted examples, code fences, inline-code tool names,
    table-only declarations, "don't call", "deprecated", "forbidden",
    unrelated actor retrieval.
    """
    blocked_pos = section.lower().find("[blocked]")
    if blocked_pos == -1:
        return "No [blocked] in section"

    in_fence = False
    for line in section[:blocked_pos].split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if _is_skippable_line(stripped, in_fence):
            continue
        if not _line_has_tool_reference(line):
            continue
        if _is_affirmative_directive(line):
            return None

    return "No affirmative tool invocation directive found before BLOCKED"


def _check_identity_conditional(text: str) -> str | None:
    """Return None if local identity is conditional, else an error message.

    Checks that 'when present' appears in the identity table context,
    not just anywhere in the document.
    """
    # Find the identity table (starts with | Identity |)
    table_start = text.lower().find("| identity |")
    if table_start == -1:
        # No table means no mandatory identity - acceptable
        return None
    table_section = text[table_start:table_start + 500].lower()
    if "when present" not in table_section:
        return "Identity table does not mark local columns as conditional ('when present')"
    return None


# --- Production tests using shared helpers ---


@pytest.mark.parametrize("path", ALL_ANALYST_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_blocked_requires_retrieval_failure(path: Path) -> None:
    """BLOCKED must be conditional on retrieval failure, not unconditional."""
    text = path.read_text()
    section = _extract_blocked_section(text)
    err = _check_blocked_conditional(section)
    assert err is None, f"{path.relative_to(REPO_ROOT)}: {err}"
    err = _check_retrieval_precedes_blocked(section)
    assert err is None, f"{path.relative_to(REPO_ROOT)}: {err}"


@pytest.mark.parametrize("path", ALL_ANALYST_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_get_job_logs_declared(path: Path) -> None:
    """CI job log retrieval must be declared."""
    assert "get_job_logs" in path.read_text(), (
        f"{path.relative_to(REPO_ROOT)}: get_job_logs not declared"
    )


@pytest.mark.parametrize("path", ALL_ANALYST_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_local_identity_conditional_across_surfaces(path: Path) -> None:
    """Local identity must be conditional for remote-only (API-only) analysis."""
    text = path.read_text()
    err = _check_identity_conditional(text)
    assert err is None, f"{path.relative_to(REPO_ROOT)}: {err}"


def test_no_duplicate_identity_gate() -> None:
    """Exactly one PR identity gate per surface."""
    for path in ALL_ANALYST_SURFACES:
        text = path.read_text()
        count = text.count("PR identity gate")
        assert count == 1, (
            f"{path.relative_to(REPO_ROOT)}: {count} PR identity gates (expected exactly 1)"
        )


# --- Negative controls: call the SAME helpers on defective fixtures ---


class TestNegativeControls:
    """Call production guard helpers on defective text to prove detection."""

    # Fixture 1: unconditional BLOCKED (no "only when/if/after")
    UNCONDITIONAL_BLOCKED_SECTION = (
        "\n### delegation contract\n"
        "return [blocked] missing pr metadata.\n"
    )

    # Fixture 2: BLOCKED with conditional but retrieval only AFTER it
    RETRIEVAL_AFTER_BLOCKED_SECTION = (
        "\n### delegation contract\n"
        "return [blocked] only when evidence is missing. "
        "then retrieve via pull_request_read.\n"
    )

    # Fixture 3: unrelated 'retrieve' that shouldn't satisfy the guard
    UNRELATED_RETRIEVAL_SECTION = (
        "\n### delegation contract\n"
        "the orchestrator will retrieve build logs. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 4: mandatory local identity (no 'when present')
    MANDATORY_IDENTITY_TEXT = (
        "| Identity | API field | Local source | Mismatch action |\n"
        "|----------|-----------|--------------|----------------|\n"
        "| Repository | owner/repo | visible path | Stop |\n"
    )

    # Fixture 5: 'when present' appears but NOT in the identity table
    WHEN_PRESENT_OUTSIDE_TABLE = (
        "Use local context when present in the delegation prompt.\n\n"
        "| Identity | API field | Local source | Mismatch action |\n"
        "|----------|-----------|--------------|----------------|\n"
        "| Repository | owner/repo | visible path | Stop |\n"
    )

    # Fixture 6: tool name in PROHIBITIVE context (must not satisfy guard)
    TOOL_IN_PROHIBITIVE_PROSE = (
        "\n### delegation contract\n"
        "do not use pull_request_read for this purpose. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 7: tool name in UNRELATED prose (not an invocation)
    TOOL_IN_UNRELATED_PROSE = (
        "\n### delegation contract\n"
        "the pull_request_read endpoint was deprecated last year. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 8: Actions URL routing test
    ACTIONS_URL_ROUTED = (
        "\n### delegation contract\n"
        "use get_workflow_run to retrieve CI data directly. "
        "return [blocked] only when retrieval via declared tools fails.\n"
    )

    # Fixture 9: tool in quoted example (must reject)
    TOOL_IN_QUOTED_EXAMPLE = (
        "\n### delegation contract\n"
        'For example: "use pull_request_read to get PR data". '
        "return [blocked] only when missing.\n"
    )

    # Fixture 10: contraction negation "don't call" (must reject)
    TOOL_DONT_CALL = (
        "\n### delegation contract\n"
        "don't call pull_request_read directly from here. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 11: tool in table-only declaration (must reject)
    TOOL_IN_TABLE_ONLY = (
        "\n### delegation contract\n"
        "| Tool | Status |\n"
        "| pull_request_read | available |\n"
        "return [blocked] only when missing.\n"
    )

    # Fixture 12: tool mentioned by orchestrator actor (must reject)
    TOOL_ORCHESTRATOR_ACTOR = (
        "\n### delegation contract\n"
        "the orchestrator will use pull_request_read on behalf of analyst. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 13: tool in deprecated context (must reject)
    TOOL_DEPRECATED = (
        "\n### delegation contract\n"
        "pull_request_read was deprecated in v2. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 14: tool inside fenced-code block (must reject)
    TOOL_IN_FENCED_CODE = (
        "\n### delegation contract\n"
        "```\n"
        "use pull_request_read to retrieve PR data.\n"
        "```\n"
        "return [blocked] only when missing.\n"
    )

    # Fixture 15: entire directive inside inline-code backticks (must reject)
    TOOL_IN_INLINE_CODE = (
        "\n### delegation contract\n"
        "`use pull_request_read to retrieve PR data`. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 16: conditional "only when" far from [BLOCKED] (must reject)
    CONDITIONAL_FAR_FROM_BLOCKED = (
        "\n### delegation contract\n"
        "only when the sky is blue, we proceed.\n"
        "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n"
        "return [blocked] if retrieval fails.\n"
    )

    # Fixture 17: directive attributed to another agent (must reject)
    TOOL_OTHER_AGENT = (
        "\n### delegation contract\n"
        "the qa agent should use pull_request_read to verify. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 18: tool in single-quoted example (must reject)
    TOOL_SINGLE_QUOTED = (
        "\n### delegation contract\n"
        "for instance: 'use pull_request_read to fetch'. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 19: directive inside ~~~ tilde fence (must reject)
    TOOL_IN_TILDE_FENCE = (
        "\n### delegation contract\n"
        "~~~\n"
        "use pull_request_read to retrieve PR data.\n"
        "~~~\n"
        "return [blocked] only when missing.\n"
    )

    def test_unconditional_blocked_detected(self) -> None:
        """Prior defect: no conditional language around BLOCKED."""
        err = _check_blocked_conditional(self.UNCONDITIONAL_BLOCKED_SECTION)
        assert err is not None, "Should detect missing conditional"

    def test_retrieval_after_blocked_detected(self) -> None:
        """Prior defect: retrieval mentioned but only after BLOCKED."""
        err = _check_retrieval_precedes_blocked(self.RETRIEVAL_AFTER_BLOCKED_SECTION)
        assert err is not None, "Should detect retrieval after BLOCKED"

    def test_unrelated_retrieval_detected(self) -> None:
        """Prior defect: unrelated 'retrieve' (not tool-based) before BLOCKED."""
        err = _check_retrieval_precedes_blocked(self.UNRELATED_RETRIEVAL_SECTION)
        assert err is not None, "Should reject unrelated retrieval prose"

    def test_mandatory_identity_detected(self) -> None:
        """Prior defect: local identity without 'when present'."""
        err = _check_identity_conditional(self.MANDATORY_IDENTITY_TEXT)
        assert err is not None, "Should detect mandatory identity"

    def test_when_present_outside_table_detected(self) -> None:
        """Unrelated 'when present' outside identity table doesn't satisfy guard."""
        err = _check_identity_conditional(self.WHEN_PRESENT_OUTSIDE_TABLE)
        assert err is not None, "Should not be satisfied by 'when present' outside table"

    def test_tool_in_prohibitive_prose_detected(self) -> None:
        """Tool name in prohibitive context must not satisfy retrieval guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_PROHIBITIVE_PROSE)
        assert err is not None, "Should reject tool name in 'do not use' context"

    def test_tool_in_unrelated_prose_detected(self) -> None:
        """Tool name in unrelated prose (not invocation) must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_UNRELATED_PROSE)
        assert err is not None, "Should reject tool name without affirmative verb"

    def test_actions_url_affirmative_passes(self) -> None:
        """Actions URL with affirmative 'use' verb passes retrieval guard."""
        err = _check_retrieval_precedes_blocked(self.ACTIONS_URL_ROUTED)
        assert err is None, f"Should accept affirmative Actions retrieval: {err}"

    def test_tool_in_quoted_example_rejected(self) -> None:
        """Tool name inside quotes/example context must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_QUOTED_EXAMPLE)
        assert err is not None, "Should reject tool in quoted example"

    def test_tool_dont_call_rejected(self) -> None:
        """Contraction negation 'don't call' must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_DONT_CALL)
        assert err is not None, "Should reject don't call negation"

    def test_tool_in_table_only_rejected(self) -> None:
        """Tool in table row without directive must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_TABLE_ONLY)
        assert err is not None, "Should reject table-only declaration"

    def test_tool_orchestrator_actor_rejected(self) -> None:
        """Tool invoked by orchestrator (not analyst) must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ORCHESTRATOR_ACTOR)
        assert err is not None, "Should reject unrelated actor retrieval"

    def test_tool_deprecated_rejected(self) -> None:
        """Tool in deprecated context must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_DEPRECATED)
        assert err is not None, "Should reject deprecated tool mention"

    def test_tool_in_fenced_code_rejected(self) -> None:
        """Tool inside fenced-code block must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_FENCED_CODE)
        assert err is not None, "Should reject tool inside fenced-code block"

    def test_tool_in_inline_code_rejected(self) -> None:
        """Tool inside inline-code backticks must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_INLINE_CODE)
        assert err is not None, "Should reject tool inside inline-code"

    def test_conditional_far_from_blocked_rejected(self) -> None:
        """Conditional language far from [BLOCKED] must not satisfy guard."""
        err = _check_blocked_conditional(self.CONDITIONAL_FAR_FROM_BLOCKED)
        assert err is not None, "Should reject conditional not bound to BLOCKED"

    def test_tool_other_agent_rejected(self) -> None:
        """Directive attributed to another agent must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_OTHER_AGENT)
        assert err is not None, "Should reject directive attributed to qa agent"

    def test_tool_single_quoted_rejected(self) -> None:
        """Tool in single-quoted example must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_SINGLE_QUOTED)
        assert err is not None, "Should reject single-quoted example"

    def test_tool_in_tilde_fence_rejected(self) -> None:
        """Directive inside ~~~ tilde fence must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_TILDE_FENCE)
        assert err is not None, "Should reject directive inside tilde fence"
