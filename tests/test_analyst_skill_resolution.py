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
    return text[max(0, section_start) : section_end if section_end != -1 else len(text)].lower()


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
    blocked_line = section[line_start : section.find("\n", blocked_pos)]
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
    "pull_request_read",
    "issue_read",
    "list_workflow_runs",
    "get_workflow_run",
    "get_job_logs",
    "get_file_contents",
    "list_commits",
)

# Word-boundary regex matching any declared tool name, with optional mcp__github__ prefix.
# Prevents substring matches like "not_pull_request_read".
_TOOL_RE = re.compile(
    r"(?<![a-zA-Z0-9_])(?:mcp__github__)?("
    + "|".join(re.escape(t) for t in _TOOL_NAMES)
    + r")(?![a-zA-Z0-9_])",
)

_NEGATIONS = re.compile(
    r"\b("
    r"do\s+not|don[\u2019']?t|never|"
    r"cannot|can[\u2019']?t|"
    r"must\s+not|mustn[\u2019']?t|"
    r"should\s+not|shouldn[\u2019']?t|"
    r"shall\s+not|shan[\u2019']?t|"
    r"will\s+not|won[\u2019']?t|"
    r"would\s+not|wouldn[\u2019']?t|"
    r"could\s+not|couldn[\u2019']?t|"
    r"may\s+not|might\s+not|"
    r"forbidden|deprecated|was\s+deprecated|is\s+not|prohibited"
    r")\b",
    re.IGNORECASE,
)

# Agent attribution: if a named agent other than "analyst" is the subject,
# the directive is not addressed to the analyst.
_OTHER_AGENT = re.compile(
    r"\b(orchestrator|reviewer|qa|security|implementer|release[- ]agent|"
    r"critic|architect)\b(?!\s+tool)",
    re.IGNORECASE,
)

_NON_DIRECTIVE = re.compile(
    r"(example:|e\.g\.|for example|"
    r"see\s+\w+\s+docs|endpoint\s+was)",
    re.IGNORECASE,
)


def _is_skippable_line(
    raw_line: str, stripped: str, in_fence: bool, *, after_list: bool = False
) -> bool:
    """Return True if line is structural markup, inside a fenced block,
    or inside a 4-space/tab indented code block."""
    if in_fence:
        return True
    # Markdown indented code block: 4+ spaces or tab at start of raw line.
    # Per CommonMark, NOT a code block after a list item (continuation).
    if (raw_line.startswith("    ") or raw_line.startswith("\t")) and not after_list:
        return True
    return (
        not stripped
        or stripped.startswith("|")
        or stripped.startswith(">")
        or stripped.startswith("#")
    )


def _is_markdown_list_item(stripped: str) -> bool:
    """Recognize all CommonMark list markers: -, *, + (unordered); N. or N) (ordered)."""
    if stripped.startswith(("- ", "* ", "+ ")):
        return True
    return bool(re.match(r"\d+[.)][\s]", stripped))


def _append_logical_line(logical_lines: list[str], stripped: str) -> None:
    if _is_markdown_list_item(stripped):
        logical_lines.append(stripped)
    elif logical_lines and logical_lines[-1] != "":
        logical_lines[-1] += " " + stripped
    else:
        logical_lines.append(stripped)


def _line_has_tool_reference(line: str) -> bool:
    """Return True if line references a declared tool or 'declared tools'.

    Tool names inside ASCII or Unicode quoted strings are NOT counted.
    Bare backtick-wrapped tool names with imperative verbs in prose ARE valid.
    """
    # Strip all quote forms: ASCII double/single + Unicode curly quotes
    stripped = re.sub(r'["\u201c\u201d][^"\u201c\u201d]*["\u201c\u201d]', "", line)
    stripped = re.sub(r"['\u2018\u2019][^'\u2018\u2019]*['\u2018\u2019]", "", stripped)
    if _TOOL_RE.search(stripped):
        return True
    return "retrieve" in stripped.lower() and "declared" in stripped.lower()


def _is_affirmative_directive(line: str) -> bool:
    """Return True if line is an affirmative directive with analyst as subject
    and a declared tool reference in the SAME clause.

    Splits on clause boundaries (semicolon, period-space) and requires
    analyst+verb+tool to co-occur in a single clause. This rejects
    mixed-actor clauses like "compliance-bot uses tool; analyst retrieves
    cache" where analyst and tool are in different clauses.

    Accepts:
    - "The analyst retrieves PR data using pull_request_read"

    Rejects:
    - Mixed clauses: "bot uses pull_request_read; analyst retrieves cache"
    - Bare imperatives: "use pull_request_read to retrieve"
    - Passive: "pull_request_read is used by the analyst"
    - Negated: "the analyst should not call pull_request_read"
    """
    if _NON_DIRECTIVE.search(line):
        return False
    if _NEGATIONS.search(line):
        return False
    if _OTHER_AGENT.search(line):
        return False

    # Equal-length masking: replace quoted/code spans with spaces so offsets
    # are preserved between the masked string and the original.
    def _mask(m: re.Match[str]) -> str:
        return " " * len(m.group(0))

    # quote_masked: only quotes stripped (preserves backtick tool refs for search)
    quote_masked = re.sub(r'["\u201c\u201d][^"\u201c\u201d]*["\u201c\u201d]', _mask, line)
    quote_masked = re.sub(r"['\u2018\u2019][^'\u2018\u2019]*['\u2018\u2019]", _mask, quote_masked)
    # fully masked: code spans AND quotes stripped (for analyst+verb detection)
    masked = re.sub(r"`[^`]*`", _mask, quote_masked)
    lower = masked.lower()

    # Reject passive voice
    if re.search(r"\b(is|are|be)\s+(used|called|invoked|retrieved)", lower):
        return False

    # Split into clauses on semicolons, sentence boundaries, and slashes
    # (used as alternatives/separators in prose).
    # Use fully masked text to find analyst+verb (not inside code/quotes).
    # Use quote_masked (quotes hidden, backticks preserved) for tool search
    # so backtick-formatted tools like `mcp__github__pull_request_read` are
    # found but quoted examples like "pull_request_read" are rejected.
    clause_split = r"[;.](?:\s|$)|\s/\s"
    clauses = re.split(clause_split, lower)
    tool_lower = quote_masked.lower()
    tool_clauses = re.split(clause_split, tool_lower)

    # Subordinating conjunctions: boundaries for tool search scope
    subord = r"\b(while|but|although|whereas|however|when|where|if)\b"

    # Pattern: comma or conjunction introducing a new subject+verb signals
    # a clause boundary. Requires the new subject to be followed by a verb,
    # distinguishing "analyst retrieves data, bot reads tool" from
    # "analyst retrieves PR, issue, and CI context".
    # Comma/and/or introducing a bot or agent subject signals a clause
    # boundary. The verb is intentionally open-ended so new actor clauses fail
    # closed instead of depending on a verb allowlist.
    new_subject_boundary = re.compile(
        r"(?:"
        r"(?:,\s*|;\s*|\band\b\s+|\bor\b\s+)"
        r"(?:the\s+)?(?!analyst\b)"
        r"(?:"
        r"[a-z][\w-]*(?:-(?:bot|agent)|bot|agent|reviewer)"  # suffixed
        r"|"
        r"[a-z][\w]*\s+(?:[a-z]*(?:es|[^aeiou]s|ed|ing|ies)"
        r"|will|can|may|shall|would|could|might|must"
        r"|has|have|had|does|did|is|are|was|were)\b"
        r")"
        r"|"
        r":\s*[a-z][\w-]*\s+[a-z]"  # colon clause
        r"|"
        r"\(\s*[a-z]"  # parenthetical
        r")"
    )
    tool_subject_boundary = re.compile(
        r"(?:,\s*|\band\b\s+|\bor\b\s+)\s*(?:mcp__github__)?(?:"
        + "|".join(re.escape(tool) for tool in _TOOL_NAMES)
        + r")\s+[a-z][\w-]*\b"
    )

    for i, clause in enumerate(clauses):
        # Require analyst as grammatical subject in MASKED text (not preceded
        # by hyphen, rejects "non-analyst", must be true word boundary).
        # Masking ensures analyst+verb inside code spans is not accepted.
        verb_match = re.search(
            r"(?<![-])\banalyst\b\s+"
            r"(?:(?:directly|then|also|always)\s+)?"
            r"(?:(?:should|will|can|shall|would|could|might|must|may)\s+)?"
            r"([a-z]{2,}(?:es|[^aeiou]s|ies)|[a-z]{3,})\b"
            r"(?:\s+(?:up|into|at|for|on)\b)?",
            clause,
        )
        if not verb_match:
            continue
        # Reject analyst+verb inside subordinate/relative/parenthetical context.
        # Leading subordinate conjunction before analyst makes it a dependent clause.
        pre = clause[: verb_match.start()].strip()
        _leading_subord = re.match(
            r"^(when|if|where|while|although|unless|before|after|until)\b",
            pre,
            re.IGNORECASE,
        )
        if _leading_subord:
            continue
        # Relative pronoun (that/which/who) preceding analyst = relative clause.
        if re.search(r"\S+\s+(?:that|which|who|whom)\b", pre):
            continue
        # Analyst inside parenthetical = not main-clause subject.
        _open_parens = pre.count("(") - pre.count(")")
        if _open_parens > 0:
            continue
        # Tool must appear AFTER the analyst+verb as its direct argument,
        # not in a subordinate clause or after a new subject boundary.
        # Use MASKED text for boundary detection (same offsets as verb_match).
        after_verb = clause[verb_match.end() :]
        main_frag = re.split(subord, after_verb)[0]
        boundaries = [
            match
            for match in (
                new_subject_boundary.search(main_frag),
                tool_subject_boundary.search(main_frag),
            )
            if match is not None
        ]
        boundary = min(boundaries, key=lambda match: match.start()) if boundaries else None
        frag_end = verb_match.end() + (boundary.start() if boundary else len(main_frag))

        # Search for tool in quote-masked text at the same offset range.
        # Backtick-formatted tool names are visible; quoted ones are masked.
        tool_clause = tool_clauses[i] if i < len(tool_clauses) else ""
        tool_frag = tool_clause[verb_match.end() : frag_end]

        tool_match = _TOOL_RE.search(tool_frag)
        if tool_match:
            return True

        # Also search for tool BEFORE the analyst+verb in the same clause
        # (handles "Using pull_request_read, the analyst retrieves context")
        # Use fully-masked text so backtick code spans are excluded.
        pre_tool_frag = clause[: verb_match.start()]
        if _TOOL_RE.search(pre_tool_frag):
            return True

        # Also accept "declared tool" phrasing in masked fragment
        masked_frag = main_frag[: boundary.start()] if boundary else main_frag
        if "declared" in masked_frag and "tool" in masked_frag:
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

    # Join continuation lines into logical paragraphs for clause analysis
    in_fence = False
    logical_lines: list[str] = []
    for line in section[:blocked_pos].split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        _after_list = bool(
            logical_lines and logical_lines[-1] and _is_markdown_list_item(logical_lines[-1])
        )
        if _is_skippable_line(line, stripped, in_fence, after_list=_after_list):
            # End current paragraph
            if logical_lines and logical_lines[-1] != "":
                logical_lines.append("")
            continue
        _append_logical_line(logical_lines, stripped)

    for paragraph in logical_lines:
        if not paragraph:
            continue
        if not _line_has_tool_reference(paragraph):
            continue
        if _is_affirmative_directive(paragraph):
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
    table_section = text[table_start : table_start + 500].lower()
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
        "\n### delegation contract\nreturn [blocked] missing pr metadata.\n"
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
        "the analyst uses get_workflow_run to retrieve CI data directly. "
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

    # Fixture 20: directive attributed to reviewer (must reject)
    TOOL_REVIEWER_AGENT = (
        "\n### delegation contract\n"
        "the reviewer will call pull_request_read for context. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 21: directive attributed to release-agent (must reject)
    TOOL_RELEASE_AGENT = (
        "\n### delegation contract\n"
        "release-agent should invoke pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 22: tool in Unicode curly-quoted example (must reject)
    TOOL_SMART_QUOTED = (
        "\n### delegation contract\n"
        "\u201cuse pull_request_read to retrieve data\u201d. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 23: bare imperative without analyst actor (must reject)
    TOOL_BARE_IMPERATIVE = (
        "\n### delegation contract\n"
        "use pull_request_read to retrieve PR data. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 24: passive voice (must reject)
    TOOL_PASSIVE_VOICE = (
        "\n### delegation contract\n"
        "pull_request_read is used by the analyst to retrieve PR data. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 25: compliance-bot agent (must reject)
    TOOL_COMPLIANCE_BOT = (
        "\n### delegation contract\n"
        "the compliance-bot uses pull_request_read to check. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 26: analyst should not (negated analyst directive)
    TOOL_ANALYST_NEGATED = (
        "\n### delegation contract\n"
        "the analyst should not call pull_request_read directly. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 27: coordinator instructs analyst (analyst as object)
    TOOL_ANALYST_AS_OBJECT = (
        "\n### delegation contract\n"
        "the coordinator instructs analyst to call pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 28: analyst may not (negated modal)
    TOOL_ANALYST_MAY_NOT = (
        "\n### delegation contract\n"
        "the analyst may not invoke pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 29: analyst will not (negated modal)
    TOOL_ANALYST_WILL_NOT = (
        "\n### delegation contract\n"
        "the analyst will not call pull_request_read directly. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 30: shouldn't contraction (must reject)
    TOOL_ANALYST_SHOULDNT = (
        "\n### delegation contract\n"
        "the analyst shouldn't call pull_request_read directly. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 31: mustn't contraction (must reject)
    TOOL_ANALYST_MUSTNT = (
        "\n### delegation contract\n"
        "the analyst mustn't invoke pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 32: won't contraction (must reject)
    TOOL_ANALYST_WONT = (
        "\n### delegation contract\n"
        "the analyst won't use pull_request_read here. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 33: could not (must reject)
    TOOL_ANALYST_COULD_NOT = (
        "\n### delegation contract\n"
        "the analyst could not call pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 34: might not (must reject)
    TOOL_ANALYST_MIGHT_NOT = (
        "\n### delegation contract\n"
        "the analyst might not use pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 35: directive in 4-space indented code block (must reject)
    TOOL_IN_INDENTED_CODE = (
        "\n### delegation contract\n"
        "    the analyst retrieves PR data using pull_request_read.\n"
        "return [blocked] only when missing.\n"
    )

    # Fixture 36: directive in tab-indented code block (must reject)
    TOOL_IN_TAB_INDENTED = (
        "\n### delegation contract\n"
        "\tthe analyst retrieves PR data using pull_request_read.\n"
        "return [blocked] only when missing.\n"
    )

    # Fixture 37: mixed-actor clause (must reject)
    TOOL_MIXED_ACTOR = (
        "\n### delegation contract\n"
        "compliance-bot uses pull_request_read; analyst retrieves cache. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 38: analyst+verb but tool in different clause (must reject)
    TOOL_SPLIT_CLAUSE = (
        "\n### delegation contract\n"
        "pull_request_read is available. The analyst retrieves context. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 39: tool before analyst verb, not after (must reject)
    TOOL_BEFORE_VERB = (
        "\n### delegation contract\n"
        "the analyst retrieves cache while pull_request_read is available. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 40: substring tool name (must reject)
    TOOL_SUBSTRING_NAME = (
        "\n### delegation contract\n"
        "the analyst retrieves PR data using not_pull_request_read. "
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

    def test_tool_reviewer_agent_rejected(self) -> None:
        """Directive attributed to reviewer must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_REVIEWER_AGENT)
        assert err is not None, "Should reject reviewer-attributed directive"

    def test_tool_release_agent_rejected(self) -> None:
        """Directive attributed to release-agent must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_RELEASE_AGENT)
        assert err is not None, "Should reject release-agent directive"

    def test_tool_smart_quoted_rejected(self) -> None:
        """Tool in Unicode curly-quoted example must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_SMART_QUOTED)
        assert err is not None, "Should reject smart-quoted example"

    def test_tool_bare_imperative_rejected(self) -> None:
        """Bare imperative without analyst actor must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_BARE_IMPERATIVE)
        assert err is not None, "Should reject actorless bare imperative"

    def test_tool_passive_voice_rejected(self) -> None:
        """Passive voice must not satisfy guard even with analyst mentioned."""
        err = _check_retrieval_precedes_blocked(self.TOOL_PASSIVE_VOICE)
        assert err is not None, "Should reject passive voice"

    def test_tool_compliance_bot_rejected(self) -> None:
        """Directive attributed to compliance-bot must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_COMPLIANCE_BOT)
        assert err is not None, "Should reject compliance-bot directive"

    def test_tool_analyst_negated_rejected(self) -> None:
        """'analyst should not' must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_NEGATED)
        assert err is not None, "Should reject negated analyst directive"

    def test_tool_analyst_as_object_rejected(self) -> None:
        """Analyst as object of another agent's verb must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_AS_OBJECT)
        assert err is not None, "Should reject analyst-as-object"

    def test_tool_analyst_may_not_rejected(self) -> None:
        """'analyst may not' must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_MAY_NOT)
        assert err is not None, "Should reject 'may not' negation"

    def test_tool_analyst_will_not_rejected(self) -> None:
        """'analyst will not' must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_WILL_NOT)
        assert err is not None, "Should reject 'will not' negation"

    def test_tool_analyst_shouldnt_rejected(self) -> None:
        """'analyst shouldn't' contraction must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_SHOULDNT)
        assert err is not None, "Should reject shouldn't contraction"

    def test_tool_analyst_mustnt_rejected(self) -> None:
        """'analyst mustn't' contraction must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_MUSTNT)
        assert err is not None, "Should reject mustn't contraction"

    def test_tool_analyst_wont_rejected(self) -> None:
        """'analyst won't' contraction must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_WONT)
        assert err is not None, "Should reject won't contraction"

    def test_tool_analyst_could_not_rejected(self) -> None:
        """'analyst could not' must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_COULD_NOT)
        assert err is not None, "Should reject 'could not'"

    def test_tool_analyst_might_not_rejected(self) -> None:
        """'analyst might not' must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ANALYST_MIGHT_NOT)
        assert err is not None, "Should reject 'might not'"

    def test_tool_in_indented_code_rejected(self) -> None:
        """Directive in 4-space indented code block must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_INDENTED_CODE)
        assert err is not None, "Should reject 4-space indented code"

    def test_tool_in_tab_indented_rejected(self) -> None:
        """Directive in tab-indented code block must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_TAB_INDENTED)
        assert err is not None, "Should reject tab-indented code"

    def test_tool_mixed_actor_rejected(self) -> None:
        """Mixed-actor clause: tool in bot clause, analyst in separate clause."""
        err = _check_retrieval_precedes_blocked(self.TOOL_MIXED_ACTOR)
        assert err is not None, "Should reject mixed-actor clauses"

    def test_tool_split_clause_rejected(self) -> None:
        """Tool in one clause, analyst+verb in another clause."""
        err = _check_retrieval_precedes_blocked(self.TOOL_SPLIT_CLAUSE)
        assert err is not None, "Should reject split-clause tool reference"

    def test_tool_before_verb_rejected(self) -> None:
        """Tool in subordinate 'while' clause, not verb argument."""
        err = _check_retrieval_precedes_blocked(self.TOOL_BEFORE_VERB)
        assert err is not None, "Should reject tool in subordinate clause"

    def test_tool_substring_name_rejected(self) -> None:
        """Substring tool name like not_pull_request_read must not match."""
        err = _check_retrieval_precedes_blocked(self.TOOL_SUBSTRING_NAME)
        assert err is not None, "Should reject substring tool name"

    # Fixture 41: subordinate 'when' clause (tool in conditional, not direct arg)
    TOOL_IN_WHEN_CLAUSE = (
        "\n### delegation contract\n"
        "The analyst retrieves cache when pull_request_read is available. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 42: non-analyst as prefixed/hyphenated word
    TOOL_NON_ANALYST_PREFIX = (
        "\n### delegation contract\n"
        "non-analyst retrieves PR data using pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 43: comma-separated mixed actors
    TOOL_COMMA_MIXED_ACTORS = (
        "\n### delegation contract\n"
        "the analyst retrieves data, release-bot calls pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 44: conjunction mixed actors
    TOOL_AND_MIXED_ACTORS = (
        "\n### delegation contract\n"
        "the analyst retrieves data and release-bot calls pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 45: comma mixed actors variant
    TOOL_COMMA_COMPLIANCE_BOT = (
        "\n### delegation contract\n"
        "the analyst retrieves cache, compliance-bot uses pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    def test_tool_in_when_clause_rejected(self) -> None:
        """Tool in subordinate 'when' clause is not a direct argument."""
        err = _check_retrieval_precedes_blocked(self.TOOL_IN_WHEN_CLAUSE)
        assert err is not None, "Should reject tool in subordinate 'when' clause"

    def test_tool_non_analyst_prefix_rejected(self) -> None:
        """Hyphenated 'non-analyst' must not match analyst as actor."""
        err = _check_retrieval_precedes_blocked(self.TOOL_NON_ANALYST_PREFIX)
        assert err is not None, "Should reject non-analyst prefix"

    def test_tool_comma_mixed_actors_rejected(self) -> None:
        """Comma-separated mixed actors must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_COMMA_MIXED_ACTORS)
        assert err is not None, "Should reject comma mixed actors"

    def test_tool_and_mixed_actors_rejected(self) -> None:
        """Conjunction mixed actors must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_AND_MIXED_ACTORS)
        assert err is not None, "Should reject conjunction mixed actors"

    def test_tool_comma_compliance_bot_rejected(self) -> None:
        """Comma mixed actors with compliance-bot must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_COMMA_COMPLIANCE_BOT)
        assert err is not None, "Should reject compliance-bot mixed actor"

    # Fixture 46: masked-span offset misalignment (HIGH 1)
    TOOL_MASKED_SPAN = (
        "\n### delegation contract\n"
        "`xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx pull_request_read`"
        " The analyst retrieves cache. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 47: masked-span with backtick quotes, short masking
    TOOL_MASKED_SPAN_SHORT = (
        "\n### delegation contract\n"
        "`xx pull_request_read` The analyst retrieves cache. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 48: reads verb mixed actor (HIGH 2)
    TOOL_READS_MIXED = (
        "\n### delegation contract\n"
        "the analyst retrieves data, release-bot reads pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 49: fetches verb mixed actor (HIGH 2)
    TOOL_FETCHES_MIXED = (
        "\n### delegation contract\n"
        "the analyst retrieves data, release-bot fetches pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 50: gets verb mixed actor (HIGH 2)
    TOOL_GETS_MIXED = (
        "\n### delegation contract\n"
        "the analyst retrieves cache and release-bot gets pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    # Fixture 51: accesses verb mixed actor (HIGH 2)
    TOOL_ACCESSES_MIXED = (
        "\n### delegation contract\n"
        "the analyst retrieves data, compliance-bot accesses pull_request_read. "
        "return [blocked] only when missing.\n"
    )

    def test_tool_masked_span_rejected(self) -> None:
        """Equal-length masked code span must not leak tool into search."""
        err = _check_retrieval_precedes_blocked(self.TOOL_MASKED_SPAN)
        assert err is not None, "Should reject masked-span tool"

    def test_tool_masked_span_short_rejected(self) -> None:
        """Short masked code span boundary must not leak tool."""
        err = _check_retrieval_precedes_blocked(self.TOOL_MASKED_SPAN_SHORT)
        assert err is not None, "Should reject short masked-span tool"

    def test_tool_reads_mixed_rejected(self) -> None:
        """'reads' verb by other actor must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_READS_MIXED)
        assert err is not None, "Should reject reads mixed actor"

    def test_tool_fetches_mixed_rejected(self) -> None:
        """'fetches' verb by other actor must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_FETCHES_MIXED)
        assert err is not None, "Should reject fetches mixed actor"

    def test_tool_gets_mixed_rejected(self) -> None:
        """'gets' verb by other actor must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_GETS_MIXED)
        assert err is not None, "Should reject gets mixed actor"

    def test_tool_accesses_mixed_rejected(self) -> None:
        """'accesses' verb by other actor must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_ACCESSES_MIXED)
        assert err is not None, "Should reject accesses mixed actor"

    # Fixture 52: tool in ASCII double-quoted example via _is_affirmative_directive
    TOOL_DOUBLE_QUOTED_DIRECTIVE = (
        "\n### delegation contract\n"
        'The analyst retrieves "pull_request_read" cache. '
        "Return [BLOCKED] only when missing.\n"
    )

    # Fixture 53: tool in ASCII single-quoted example via _is_affirmative_directive
    TOOL_SINGLE_QUOTED_DIRECTIVE = (
        "\n### delegation contract\n"
        "The analyst retrieves 'pull_request_read' cache. "
        "Return [BLOCKED] only when missing.\n"
    )

    # Fixture 54: tool in Unicode curly-quoted directive
    TOOL_CURLY_QUOTED_DIRECTIVE = (
        "\n### delegation contract\n"
        "The analyst retrieves \u201cpull_request_read\u201d cache. "
        "Return [BLOCKED] only when missing.\n"
    )

    # Fixture 55: tool in backtick code span (QA mandatory reproducer)
    TOOL_BACKTICK_SPAN_MANDATORY = (
        "\n### delegation contract\n"
        "`" + "x" * 32 + " pull_request_read` The analyst retrieves cache. "
        "Return [BLOCKED] only when missing.\n"
    )

    def test_tool_double_quoted_rejected(self) -> None:
        """Tool in double quotes must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_DOUBLE_QUOTED_DIRECTIVE)
        assert err is not None, "Should reject double-quoted tool"
        assert not _is_affirmative_directive('The analyst retrieves "pull_request_read" cache')

    def test_tool_single_quoted_in_directive_rejected(self) -> None:
        """Tool in single quotes must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_SINGLE_QUOTED_DIRECTIVE)
        assert err is not None, "Should reject single-quoted tool"
        assert not _is_affirmative_directive("The analyst retrieves 'pull_request_read' cache")

    def test_tool_curly_quoted_rejected(self) -> None:
        """Tool in curly quotes must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_CURLY_QUOTED_DIRECTIVE)
        assert err is not None, "Should reject curly-quoted tool"
        assert not _is_affirmative_directive(
            "The analyst retrieves \u201cpull_request_read\u201d cache"
        )

    def test_tool_backtick_span_mandatory_rejected(self) -> None:
        """QA mandatory reproducer: 32-char backtick span must reject."""
        err = _check_retrieval_precedes_blocked(self.TOOL_BACKTICK_SPAN_MANDATORY)
        assert err is not None, "Should reject backtick-span tool"
        line = "`" + "x" * 32 + " pull_request_read` The analyst retrieves cache"
        assert not _is_affirmative_directive(line)

    # Fixture 56: mixed-actor "provides" verb (HIGH 1)
    TOOL_MIXED_PROVIDES = (
        "\n### delegation contract\n"
        "The analyst retrieves cache, compliance-bot provides pull_request_read. "
        "Return [BLOCKED] only when missing.\n"
    )

    # Fixture 57: mixed-actor with a verb not named in the old allowlist
    TOOL_MIXED_OWNS = (
        "\n### delegation contract\n"
        "The analyst retrieves cache, compliance-bot owns pull_request_read. "
        "Return [BLOCKED] only when missing.\n"
    )

    # Fixture 58: mixed-actor "reads" after conjunction (HIGH 1)
    TOOL_MIXED_READS_CONJ = (
        "\n### delegation contract\n"
        "The analyst retrieves cache and the release-bot reads pull_request_read. "
        "Return [BLOCKED] only when missing.\n"
    )

    # Fixture 59: tool as subject "remains" (HIGH 1)
    TOOL_REMAINS_AVAILABLE = (
        "\n### delegation contract\n"
        "The analyst retrieves cache, pull_request_read remains available. "
        "Return [BLOCKED] only when missing.\n"
    )

    # Fixture 60: adjacent list items must not merge (HIGH 2)
    TOOL_LIST_ITEMS_MERGED = (
        "\n### delegation contract\n"
        "- The analyst retrieves cache\n"
        "- compliance-bot calls pull_request_read\n"
        "Return [BLOCKED] only when missing.\n"
    )

    def test_tool_mixed_provides_rejected(self) -> None:
        """'provides' by other actor must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_MIXED_PROVIDES)
        assert err is not None, "Should reject mixed-actor provides"
        assert not _is_affirmative_directive(
            "The analyst retrieves cache, compliance-bot provides pull_request_read"
        )

    def test_tool_mixed_owns_rejected(self) -> None:
        """Any verb by another bot subject must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_MIXED_OWNS)
        assert err is not None, "Should reject mixed-actor owns"
        assert not _is_affirmative_directive(
            "The analyst retrieves cache, compliance-bot owns pull_request_read"
        )

    def test_tool_mixed_reads_conjunction_rejected(self) -> None:
        """'reads' after 'and' by other actor must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_MIXED_READS_CONJ)
        assert err is not None, "Should reject mixed-actor reads conjunction"
        assert not _is_affirmative_directive(
            "The analyst retrieves cache and the release-bot reads pull_request_read"
        )

    def test_tool_remains_available_rejected(self) -> None:
        """Tool as subject with 'remains' must not satisfy guard."""
        err = _check_retrieval_precedes_blocked(self.TOOL_REMAINS_AVAILABLE)
        assert err is not None, "Should reject tool-remains-available"
        assert not _is_affirmative_directive(
            "The analyst retrieves cache, pull_request_read remains available"
        )

    def test_list_items_not_merged(self) -> None:
        """Adjacent list items must stay as separate paragraphs."""
        err = _check_retrieval_precedes_blocked(self.TOOL_LIST_ITEMS_MERGED)
        assert err is not None, "Should reject merged list items"


class TestPositiveMcpPrefix:
    """MCP-prefixed tool names must be accepted in affirmative directives."""

    def test_mcp_prefixed_tool_accepted(self) -> None:
        """Backtick-wrapped mcp__github__pull_request_read is valid."""
        assert _is_affirmative_directive(
            "The analyst retrieves PR data using mcp__github__pull_request_read"
        )

    def test_mcp_prefixed_in_section(self) -> None:
        """Full section with mcp-prefixed tool passes wrapper."""
        section = (
            "\n### delegation contract\n"
            "The analyst retrieves PR data using `mcp__github__pull_request_read`. "
            "Return [BLOCKED] only when missing.\n"
        )
        err = _check_retrieval_precedes_blocked(section)
        assert err is None, f"MCP-prefixed tool should pass: {err}"


class TestPositiveListItems:
    """Positive: analyst directive in a list item should pass."""

    def test_list_item_with_tool_passes(self) -> None:
        """Single list item with analyst+verb+tool passes."""
        section = (
            "\n### delegation contract\n"
            "- The analyst retrieves PR data using pull_request_read\n"
            "Return [BLOCKED] only when missing.\n"
        )
        err = _check_retrieval_precedes_blocked(section)
        assert err is None, f"Single list item should pass: {err}"

    def test_wrapped_continuation_passes(self) -> None:
        """Genuine wrapped line (non-list) continuation still merges."""
        section = (
            "\n### delegation contract\n"
            "The analyst retrieves PR data\n"
            "using pull_request_read for context.\n"
            "Return [BLOCKED] only when missing.\n"
        )
        err = _check_retrieval_precedes_blocked(section)
        assert err is None, f"Wrapped continuation should pass: {err}"


# --- Negative controls: structural boundary bypasses (review round) ---


class TestNegativeStructuralBoundary:
    """Non-suffixed actors, colon, parenthetical must be caught."""

    @pytest.mark.parametrize(
        "line",
        [
            "The analyst retrieves cache: bot calls pull_request_read",
            "The analyst retrieves cache (provided by compliance-bot using pull_request_read)",
            "The analyst retrieves cache, coordinator documents pull_request_read",
            "The analyst retrieves cache, platform advertises pull_request_read",
            "The analyst retrieves cache, system makes pull_request_read available",
            "The analyst retrieves cache; release-bot uses pull_request_read",
            "The analyst retrieves cache, the compliance-bot provides pull_request_read",
            "The analyst retrieves cache and the release-bot reads pull_request_read",
            "The analyst retrieves cache, orchestrator owns pull_request_read",
        ],
        ids=[
            "colon",
            "parenthetical",
            "documents",
            "advertises",
            "makes-available",
            "semicolon",
            "article-provides",
            "conjunction-reads",
            "owns",
        ],
    )
    def test_direct_helper_rejects(self, line: str) -> None:
        assert _is_affirmative_directive(line) is False

    @pytest.mark.parametrize(
        "line",
        [
            "The analyst retrieves cache (provided by compliance-bot using pull_request_read)",
            "The analyst retrieves cache, platform advertises pull_request_read",
            "The analyst retrieves cache: bot calls pull_request_read",
        ],
        ids=["parenthetical-wrap", "advertises-wrap", "colon-wrap"],
    )
    def test_production_wrapper_rejects(self, line: str) -> None:
        section = "\n### delegation contract\n" + line + ". Return [BLOCKED] only when missing.\n"
        assert _check_retrieval_precedes_blocked(section) is not None


# --- Negative controls: CommonMark list markers ---


class TestNegativeAllListMarkers:
    """All CommonMark markers prevent cross-actor merging."""

    @pytest.mark.parametrize(
        "marker",
        ["- ", "* ", "+ ", "1. ", "1) ", "2. ", "10) "],
        ids=["dash", "star", "plus", "1dot", "1paren", "2dot", "10paren"],
    )
    def test_list_marker_cross_bind(self, marker: str) -> None:
        section = (
            "\n### delegation contract\n"
            "- The analyst retrieves cache\n"
            f"{marker}compliance-bot calls pull_request_read\n"
            "Return [BLOCKED] only when missing.\n"
        )
        assert _check_retrieval_precedes_blocked(section) is not None

    def test_positive_wrapped_list_continuation(self) -> None:
        """Indented continuation of a list item is joined correctly."""
        section = (
            "\n### delegation contract\n"
            "- The analyst retrieves PR context\n"
            "  using pull_request_read directly.\n"
            "Return [BLOCKED] only when missing.\n"
        )
        assert _check_retrieval_precedes_blocked(section) is None


# --- Positive: all 7 canonical tools ---


class TestAllCanonicalTools:
    """All 7 tools from analyst.shared.md accepted bare and MCP-prefixed."""

    @pytest.mark.parametrize(
        "tool",
        [
            "pull_request_read",
            "issue_read",
            "list_workflow_runs",
            "get_workflow_run",
            "get_job_logs",
            "get_file_contents",
            "list_commits",
        ],
    )
    def test_bare(self, tool: str) -> None:
        assert _is_affirmative_directive(f"The analyst retrieves context using {tool} directly.")

    @pytest.mark.parametrize(
        "tool",
        [
            "mcp__github__pull_request_read",
            "mcp__github__get_file_contents",
            "mcp__github__list_commits",
        ],
        ids=["pr-mcp", "file-mcp", "commits-mcp"],
    )
    def test_mcp_prefixed(self, tool: str) -> None:
        assert _is_affirmative_directive(f"The analyst retrieves context using `{tool}` directly.")


# --- Negative controls: subordinate/relative/parenthetical context ---


class TestNegativeClauseContext:
    """Analyst+verb in dependent context must be rejected."""

    @pytest.mark.parametrize(
        "line",
        [
            "When the analyst uses pull_request_read, return BLOCKED",
            "If analyst retrieves pull_request_read, log the event",
            "Where the analyst calls pull_request_read, caching applies",
            "While analyst uses pull_request_read, monitor progress",
            "Unless the analyst retrieves pull_request_read first, block",
            "The tool that the analyst uses is pull_request_read",
            "Data which the analyst retrieves via pull_request_read is cached",
            "The process (analyst retrieves pull_request_read) is complex",
            "Check (the analyst uses pull_request_read) before proceeding",
        ],
        ids=[
            "when",
            "if",
            "where",
            "while",
            "unless",
            "that-relative",
            "which-relative",
            "paren-embed",
            "paren-article",
        ],
    )
    def test_direct_helper_rejects(self, line: str) -> None:
        assert _is_affirmative_directive(line) is False

    @pytest.mark.parametrize(
        "line",
        [
            "When the analyst uses pull_request_read, log the event",
            "The tool that the analyst uses is pull_request_read",
            "The process (analyst retrieves pull_request_read) is complex",
        ],
        ids=["when-wrap", "relative-wrap", "paren-wrap"],
    )
    def test_production_wrapper_rejects(self, line: str) -> None:
        section = "\n### delegation contract\n" + line + ".\nReturn [BLOCKED] only when missing.\n"
        assert _check_retrieval_precedes_blocked(section) is not None


class TestPositiveMainClauseControls:
    """Legitimate main-clause analyst directives remain accepted."""

    @pytest.mark.parametrize(
        "line",
        [
            "The analyst retrieves PR data using pull_request_read directly.",
            "The analyst uses pull_request_read to fetch context.",
            "The analyst retrieves data using pull_request_read so that it can proceed.",
            "The analyst calls pull_request_read before returning results.",
        ],
        ids=["using", "to-fetch", "so-that", "before-return"],
    )
    def test_main_clause_accepted(self, line: str) -> None:
        assert _is_affirmative_directive(line) is True


class TestNegativeMixedActorBoundary:
    """Mixed-actor clauses with structural boundaries must be rejected."""

    @pytest.mark.parametrize(
        "line",
        [
            "The analyst retrieves cache, coordinator will expose pull_request_read.",
            "The analyst retrieves cache / coordinator exposes pull_request_read",
            "The analyst retrieves cache: system provides pull_request_read",
            "The analyst retrieves cache, someone provides pull_request_read.",
        ],
        ids=["modal-boundary", "slash-boundary", "colon-boundary", "provides-boundary"],
    )
    def test_direct_helper_rejects(self, line: str) -> None:
        assert _is_affirmative_directive(line) is False


class TestPositiveStructuralVerbs:
    """Analyst with structural verb forms (3rd-person-singular, phrasal) accepted."""

    @pytest.mark.parametrize(
        "line",
        [
            "The analyst fetches PR context using pull_request_read",
            "The analyst consults pull_request_read for data",
            "The analyst looks up pull_request_read",
            "The analyst accesses pull_request_read directly",
            "Using pull_request_read, the analyst retrieves context",
            "Via pull_request_read the analyst accesses PR data",
        ],
        ids=["fetches", "consults", "looks-up", "accesses", "tool-before-actor", "via-tool"],
    )
    def test_accepted(self, line: str) -> None:
        assert _is_affirmative_directive(line) is True


class TestPositiveModalDirectives:
    """Analyst with modal + base verb forms accepted."""

    @pytest.mark.parametrize(
        "line",
        [
            "analyst should read pull_request_read",
            "analyst will call pull_request_read",
            "analyst can query issue_read",
            "The analyst must retrieve pull_request_read before proceeding",
            "The analyst may use get_job_logs for CI context",
            "The analyst shall invoke list_commits",
        ],
        ids=[
            "should-read",
            "will-call",
            "can-query",
            "must-retrieve",
            "may-use",
            "shall-invoke",
        ],
    )
    def test_modal_accepted(self, line: str) -> None:
        assert _is_affirmative_directive(line) is True


class TestNegativeModalCrossedActor:
    """Modal directives attributed to non-analyst must be rejected."""

    @pytest.mark.parametrize(
        "line",
        [
            "coordinator should call pull_request_read",
            "release-bot will invoke pull_request_read",
            "the analyst retrieves data, coordinator can read pull_request_read",
        ],
        ids=["coordinator-should", "bot-will", "mixed-modal"],
    )
    def test_modal_rejected(self, line: str) -> None:
        assert _is_affirmative_directive(line) is False
