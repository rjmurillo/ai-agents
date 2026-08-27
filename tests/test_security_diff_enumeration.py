# taste-lint: ignore file-size -- every helper here is asserted twice, once against
# the six shipped surfaces and once against defective fixtures in the control
# classes below. Splitting production assertions from their controls would put the
# two halves of that pairing in different files, which is the exact structure that
# let the previous version green-light a grant Claude Code cannot parse.
"""Structural guards for the security agent's review-scope tool contract.

Issue #4781: the agent could not enumerate a changeset because no surface
granted it git or a pinned-diff retrieval path, so it returned a blocked verdict
it could not justify.

The first repair declared permission-rule strings such as ``Bash(git diff:*)``
in the subagent ``tools`` allowlist. Claude Code does not accept that syntax:
the official contract (https://code.claude.com/docs/en/sub-agents, "Supported
frontmatter fields" and "Available tools") documents ``tools`` as bare tool
names plus the MCP patterns ``mcp__<server>`` and ``mcp__<server>__*``, with
``tools: Read, Grep, Glob, Bash`` as its worked example. A parenthesised entry
is not a grant at all, so that repair left the agent with no Bash and no Write,
making the reported symptom permanent instead of fixing it. The earlier version
of this module asserted those literal strings were present, so it green-lit the
broken grant and would have blocked the correct fix.

What replaces it: bare names, which are unscoped, with the read-only-git and
report-path limits stated as prompt obligations on every surface. The documented
enforcement mechanism is a subagent-scoped ``PreToolUse`` hook, which ADR-097
and ``.claude/rules/tool-use-hook-bar.md`` gate behind an ADR review. Until that
review lands, no surface may present the limits as a toolset property.

Each production assertion runs through a helper the negative-control classes
below also call on defective fixtures, so a helper that stops detecting is
caught by its own control rather than passing silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_CANONICAL = REPO_ROOT / "src" / "claude" / "security.md"
CLAUDE_RUNTIME = REPO_ROOT / ".claude" / "agents" / "security.md"
SHARED_TEMPLATE = REPO_ROOT / "templates" / "agents" / "security.shared.md"
COPILOT_RUNTIME = REPO_ROOT / ".github" / "agents" / "security.agent.md"
COPILOT_GENERATED = REPO_ROOT / "src" / "copilot-cli" / "agents" / "security.agent.md"
VSCODE_GENERATED = REPO_ROOT / "src" / "vs-code-agents" / "security.agent.md"

CLAUDE_SURFACES = (CLAUDE_CANONICAL, CLAUDE_RUNTIME)
PLATFORM_SURFACES = (COPILOT_RUNTIME, COPILOT_GENERATED, VSCODE_GENERATED)
ALL_SECURITY_SURFACES = (
    CLAUDE_CANONICAL,
    CLAUDE_RUNTIME,
    SHARED_TEMPLATE,
    COPILOT_RUNTIME,
    COPILOT_GENERATED,
    VSCODE_GENERATED,
)

# Bare tool names the enumeration protocol needs on a Claude surface. Bash is
# what issue #4781 was missing; Write and Edit carry the review report.
REQUIRED_CLAUDE_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Bash",
    "Write",
    "Edit",
)

# Claude-side pinned-diff retrieval, used when local git is unavailable.
REQUIRED_PINNED_DIFF_CLAUDE = (
    "mcp__github__pull_request_read",
    "mcp__github__get_commit",
    "mcp__github__get_file_contents",
)

# Platform-side equivalents. Copilot and VS Code have no shell, so a pinned SHA
# or PR diff is their only enumeration path.
REQUIRED_PINNED_DIFF_PLATFORM = (
    "github/pull_request_read",
    "github/get_commit",
    "github/get_file_contents",
    "github/list_commits",
)

# A bare tool name: CamelCase letters and digits, no punctuation of any kind.
BARE_TOOL_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")

# The documented MCP forms: a whole server, or one tool on a server.
MCP_TOOL_NAME = re.compile(r"^mcp__[a-z0-9_]+(__(\*|[a-z0-9_]+))?$")

# GitHub MCP tools that mutate remote state.
MUTATING_GITHUB_TOOLS = (
    "mcp__github__create_or_update_file",
    "mcp__github__push_files",
    "mcp__github__delete_file",
    "mcp__github__merge_pull_request",
    "mcp__github__create_branch",
    "mcp__github__create_pull_request",
)

# Markers every surface must carry, whatever tools its harness grants.
PROSE_MARKERS = (
    "### Review Scope Enumeration (required)",
    "skipping any whose tools this harness does not grant",
    "A caller-supplied diff artifact",
    "Record the pinned scope in the verdict",
    "MUST NOT while enumerating",
)

# Shell-specific markers. Copilot and VS Code grant no shell tool, so the
# concrete git commands are gated behind a capability clause rather than
# mandated on every surface (issue #4781 review, finding 5).
SHELL_PROSE_MARKERS = (
    "If a shell tool is granted (Claude surfaces only):",
    "git status --porcelain",
    "On a harness with no shell",
)

# A read-only subcommand allowlist does not make a command read-only: `git diff`,
# `git log`, and `git show` all accept `--output=<path>`. Measured on this branch,
# `git diff HEAD~1 --output=<tmp>` wrote 3127 bytes and `git log -1 --output=<tmp>`
# wrote 1186 bytes. Nothing enforces the limit, so the prose must name the hole.
OUTPUT_HAZARD_MARKERS = (
    "No `--output` or `-o` on `git diff`",
    "No shell redirection into",
)

# Prompt obligations on every surface: the Claude allowlist grants bare
# Bash/Write, and `$toolset:editor` grants unscoped `edit` on Copilot and VS Code.
OBLIGATION_MARKERS = (
    "obligations this prompt places on you, not properties of",
    "No harness scopes them for you",
    "hold the line yourself",
)

# Wording that would claim an enforcement no surface currently has.
OVERCLAIM_PHRASES = (
    "Mutating git is never granted",
    "a guard that denies",
    "PreToolUse guard",
)

BLOCKED_SENTENCE = (
    "Return `[BLOCKED] Cannot evaluate: review scope not enumerable` only when all"
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


def find_unparseable_tool_entries(tools: list[str]) -> list[str]:
    """Return entries Claude Code's ``tools`` allowlist cannot read as a tool name.

    Only two shapes are accepted: a bare CamelCase tool name, and an MCP
    server-level or single-tool pattern. Anything carrying a parenthesised
    specifier, a colon, a glob, or a path is permission-rule syntax that the
    subagent loader does not parse, so declaring it silently grants nothing.
    """
    offenders: list[str] = []
    for tool in tools:
        stripped = tool.strip()
        if BARE_TOOL_NAME.fullmatch(stripped):
            continue
        if MCP_TOOL_NAME.fullmatch(stripped):
            continue
        offenders.append(tool)
    return offenders


def find_mutating_github_grants(tools: list[str]) -> list[str]:
    """Return declared GitHub tools that mutate remote state."""
    normalized = {tool.strip().casefold() for tool in tools}
    return [name for name in MUTATING_GITHUB_TOOLS if name.casefold() in normalized]


def find_missing_tools(tools: list[str], required: tuple[str, ...]) -> list[str]:
    """Return the required tool names absent from *tools*."""
    normalized = {tool.strip().casefold() for tool in tools}
    return [name for name in required if name.casefold() not in normalized]


def find_missing_prose(text: str, markers: tuple[str, ...]) -> list[str]:
    """Return the markers absent from *text*."""
    return [marker for marker in markers if marker not in text]


def find_enforcement_overclaims(text: str) -> list[str]:
    """Return phrases asserting an enforcement no surface currently provides.

    The bare `tools` allowlist and `$toolset:editor` are both unscoped, so a
    sentence promising the harness will refuse a mutating call is false on every
    surface. That mismatch between promised and enforced scope is what issue
    #4781's review named, and it reads as reassuring rather than as a defect.
    """
    return [phrase for phrase in OVERCLAIM_PHRASES if phrase in text]


def blocked_is_conditional(text: str) -> str | None:
    """Return None when the scope BLOCKED verdict is bound to retrieval failure."""
    if "[BLOCKED] Cannot evaluate: review scope not enumerable" not in text:
        return "scope-enumeration BLOCKED verdict is absent"
    if BLOCKED_SENTENCE not in text:
        return "scope-enumeration BLOCKED verdict is not conditional on retrieval failure"
    if "BLOCKED is never the first move" not in text:
        return "prose does not forbid BLOCKED as the first move"
    return None


# --- Production tests ---


@pytest.mark.parametrize("path", CLAUDE_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_claude_surface_declares_explicit_tools(path: Path) -> None:
    """An absent `tools` key is the defect: the agent inherits whatever the host gives."""
    tools = _tool_list(_frontmatter(path), "tools", path)

    assert len(tools) == len(set(tools)), f"{path.relative_to(REPO_ROOT)}: duplicate tool entries"


@pytest.mark.parametrize("path", CLAUDE_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_claude_surface_uses_only_parseable_tool_names(path: Path) -> None:
    """A parenthesised specifier grants nothing, so it is worse than omitting the key."""
    tools = _tool_list(_frontmatter(path), "tools", path)

    offenders = find_unparseable_tool_entries(tools)
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: `tools` entries Claude Code cannot parse "
        f"as tool names {offenders}; the allowlist takes bare names only"
    )


@pytest.mark.parametrize("path", CLAUDE_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_claude_surface_grants_the_tools_the_protocol_needs(path: Path) -> None:
    """Issue #4781's symptom returns if Bash is absent, however it is spelled."""
    tools = _tool_list(_frontmatter(path), "tools", path)

    missing = find_missing_tools(tools, REQUIRED_CLAUDE_TOOLS)
    assert not missing, f"{path.relative_to(REPO_ROOT)}: missing tool grants {missing}"


@pytest.mark.parametrize("path", CLAUDE_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_claude_surface_grants_no_remote_mutation(path: Path) -> None:
    tools = _tool_list(_frontmatter(path), "tools", path)

    offenders = find_mutating_github_grants(tools)
    assert not offenders, f"{path.relative_to(REPO_ROOT)}: remote-mutating grants {offenders}"


@pytest.mark.parametrize("path", CLAUDE_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_claude_surface_can_bind_to_a_sha(path: Path) -> None:
    tools = _tool_list(_frontmatter(path), "tools", path)

    missing = find_missing_tools(tools, REQUIRED_PINNED_DIFF_CLAUDE)
    assert not missing, f"{path.relative_to(REPO_ROOT)}: missing pinned-diff grants {missing}"


@pytest.mark.parametrize("path", PLATFORM_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_platform_surface_can_bind_to_a_sha(path: Path) -> None:
    """Copilot and VS Code have no shell; a pinned SHA or PR is their only path."""
    tools = _tool_list(_frontmatter(path), "tools", path)

    missing = find_missing_tools(tools, REQUIRED_PINNED_DIFF_PLATFORM)
    assert not missing, f"{path.relative_to(REPO_ROOT)}: missing pinned-diff grants {missing}"


@pytest.mark.parametrize(
    "key",
    ["tools_copilot", "tools_vscode"],
)
def test_shared_template_declares_platform_pinned_diff_tools(key: str) -> None:
    tools = _tool_list(_frontmatter(SHARED_TEMPLATE), key, SHARED_TEMPLATE)

    # $toolset:github-research expands to the pull-request and commit readers.
    assert "$toolset:github-research" in tools, f"{key} must include the research toolset"
    assert "github/get_commit" in tools, f"{key} must be able to pin a single commit"


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_carries_the_enumeration_protocol(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    missing = find_missing_prose(text, PROSE_MARKERS)
    assert not missing, f"{path.relative_to(REPO_ROOT)}: missing prose markers {missing}"


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_gates_the_shell_path_on_capability(path: Path) -> None:
    """Copilot and VS Code grant no shell, so step 1 must be conditional everywhere.

    The body is one text copied to six surfaces, so the capability clause has to
    travel with it. Mandating the bare `git status --porcelain` line on a
    shell-less surface is what made the protocol unfollowable there.
    """
    text = path.read_text(encoding="utf-8")

    missing = find_missing_prose(text, SHELL_PROSE_MARKERS)
    assert not missing, (
        f"{path.relative_to(REPO_ROOT)}: shell path is not capability-gated {missing}"
    )


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_names_the_git_output_write_hazard(path: Path) -> None:
    """A read-only subcommand list is not a read-only command list."""
    text = path.read_text(encoding="utf-8")

    missing = find_missing_prose(text, OUTPUT_HAZARD_MARKERS)
    assert not missing, f"{path.relative_to(REPO_ROOT)}: --output hazard unstated {missing}"


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_states_the_limits_as_obligations(path: Path) -> None:
    """Bare `Bash`/`Write` and `$toolset:editor` are unscoped on every surface."""
    text = path.read_text(encoding="utf-8")

    missing = find_missing_prose(text, OBLIGATION_MARKERS)
    assert not missing, (
        f"{path.relative_to(REPO_ROOT)}: limits are not framed as obligations {missing}"
    )


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_surface_claims_an_enforcement_it_lacks(path: Path) -> None:
    """The promised-but-unenforced mismatch is the defect issue #4781's review named."""
    text = path.read_text(encoding="utf-8")

    overclaims = find_enforcement_overclaims(text)
    assert not overclaims, (
        f"{path.relative_to(REPO_ROOT)}: claims an enforcement no surface provides "
        f"{overclaims}; state the limit as an obligation, or ship the guard and "
        f"clear ADR-097 first"
    )


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_makes_scope_blocked_conditional(path: Path) -> None:
    err = blocked_is_conditional(path.read_text(encoding="utf-8"))

    assert err is None, f"{path.relative_to(REPO_ROOT)}: {err}"


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_forbids_mutating_git_in_prose(path: Path) -> None:
    """Nothing scopes the shell grant, so the prohibition has to be prose."""
    text = path.read_text(encoding="utf-8")

    for subcommand in ("commit", "push", "checkout", "reset", "stash", "clean"):
        assert f"`{subcommand}`" in text, (
            f"{path.relative_to(REPO_ROOT)}: prose does not forbid `git {subcommand}`"
        )


def test_claude_pair_stays_byte_identical() -> None:
    """The canonical and runtime Claude copies are hand-maintained in lockstep."""
    assert CLAUDE_CANONICAL.read_bytes() == CLAUDE_RUNTIME.read_bytes()


# --- Negative controls: the same helpers, run on defective input ---


class TestToolNameControls:
    """Prove find_unparseable_tool_entries rejects every non-tool-name shape."""

    @pytest.mark.parametrize(
        "tools",
        [
            pytest.param(["Read", "Bash(git status:*)"], id="permission-rule-bash"),
            pytest.param(["Read", "Bash(git diff:*)"], id="permission-rule-diff"),
            pytest.param(["Read", "Bash(git diff --output=x:*)"], id="permission-rule-output"),
            pytest.param(["Read", "Bash(git -C /other push:*)"], id="permission-rule-redirect"),
            pytest.param(["Read", "Write(.agents/security/**)"], id="permission-rule-write"),
            pytest.param(
                ["Read", "Edit(.agents/planning/impact-analysis-security-*.md)"],
                id="permission-rule-edit",
            ),
            pytest.param(["Read", "Bash(git status"], id="unterminated-specifier"),
            pytest.param(["Read", "bash"], id="lowercase-bare-name"),
            pytest.param(["Read", "Agent(worker)"], id="agent-spawn-specifier"),
            pytest.param(["Read", "mcp__github__*__extra"], id="malformed-mcp-pattern"),
            pytest.param(["Read", ".claude/skills/x.py"], id="path-not-a-tool"),
            pytest.param(["Read", "Bash, Write"], id="comma-joined-entry"),
        ],
    )
    def test_unparseable_entry_detected(self, tools: list[str]) -> None:
        assert find_unparseable_tool_entries(tools), f"should reject {tools}"

    @pytest.mark.parametrize(
        "tools",
        [
            pytest.param(list(REQUIRED_CLAUDE_TOOLS), id="the-shipped-bare-names"),
            pytest.param(["Read", "WebSearch", "TodoWrite"], id="multiword-camel-case"),
            pytest.param(["mcp__github", "mcp__serena__read_memory"], id="mcp-forms"),
            pytest.param(["mcp__github__*"], id="mcp-server-wildcard"),
        ],
    )
    def test_parseable_entry_accepted(self, tools: list[str]) -> None:
        """Inverted control: a correct allowlist must produce no offender."""
        assert find_unparseable_tool_entries(tools) == []


class TestOverclaimControls:
    """Prove find_enforcement_overclaims catches the ways prose can promise too much."""

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param(
                "- **Read-only git**: `git diff`. Mutating git is never granted.\n",
                id="never-granted-claim",
            ),
            pytest.param(
                "A PreToolUse guard on the `Bash` matcher denies anything else.\n",
                id="guard-registration-claim",
            ),
            pytest.param(
                "Some harnesses back them with a guard that denies the call.\n",
                id="hedged-guard-claim",
            ),
        ],
    )
    def test_overclaim_detected(self, text: str) -> None:
        assert find_enforcement_overclaims(text), f"should flag {text!r}"

    def test_obligation_wording_accepted(self) -> None:
        """Inverted control: the shipped wording must not read as an overclaim."""
        honest = (
            "These limits are obligations this prompt places on you, not properties "
            "of the toolset you were handed. No harness scopes them for you.\n"
        )

        assert find_enforcement_overclaims(honest) == []


class TestRemoteMutationControls:
    def test_mutating_github_tool_detected(self) -> None:
        assert find_mutating_github_grants(["Read", "mcp__github__push_files"])

    def test_read_only_github_tools_accepted(self) -> None:
        assert find_mutating_github_grants(list(REQUIRED_PINNED_DIFF_CLAUDE)) == []


class TestMissingToolControls:
    def test_missing_required_tool_detected(self) -> None:
        assert find_missing_tools(["Read"], REQUIRED_CLAUDE_TOOLS) == [
            name for name in REQUIRED_CLAUDE_TOOLS if name != "Read"
        ]

    def test_permission_rule_spelling_reads_as_absent(self) -> None:
        """The exact defect: `Bash(git diff:*)` is present as text and absent as a grant."""
        assert find_missing_tools(["Read", "Bash(git diff:*)"], ("Bash",)) == ["Bash"]

    def test_present_required_tools_accepted(self) -> None:
        assert find_missing_tools(list(REQUIRED_CLAUDE_TOOLS), REQUIRED_CLAUDE_TOOLS) == []

    def test_case_difference_still_matches(self) -> None:
        """Edge: frontmatter casing drift must not read as an absent grant."""
        assert find_missing_tools(["MCP__GITHUB__GET_COMMIT"], ("mcp__github__get_commit",)) == []


class TestProseControls:
    UNCONDITIONAL_BLOCKED = (
        "Return `[BLOCKED] Cannot evaluate: review scope not enumerable` when the "
        "caller does not supply a diff.\n"
    )
    NO_BLOCKED_AT_ALL = "Enumerate the changeset before you assess it.\n"
    BLOCKED_FIRST_MOVE = (
        "Return `[BLOCKED] Cannot evaluate: review scope not enumerable` only when all\n"
        "three paths fail.\n"
    )

    def test_missing_prose_marker_detected(self) -> None:
        assert find_missing_prose("nothing here", PROSE_MARKERS) == list(PROSE_MARKERS)

    def test_present_prose_markers_accepted(self) -> None:
        assert find_missing_prose(" ".join(PROSE_MARKERS), PROSE_MARKERS) == []

    def test_ungated_shell_prose_detected(self) -> None:
        """Edge: naming the git commands without the capability clause is the defect."""
        ungated = "1. **Local read-only git.** Run `git status --porcelain` for the diff.\n"

        assert find_missing_prose(ungated, SHELL_PROSE_MARKERS)

    def test_gated_shell_prose_accepted(self) -> None:
        assert find_missing_prose(" ".join(SHELL_PROSE_MARKERS), SHELL_PROSE_MARKERS) == []

    def test_subcommand_allowlist_without_output_hazard_detected(self) -> None:
        """Edge: forbidding mutating subcommands leaves `git diff --output` open."""
        partial = (
            "**MUST NOT while enumerating.** No mutating git: `commit`, `push`, "
            "`checkout`, `reset`, `stash`, `clean`.\n"
        )

        assert find_missing_prose(partial, OUTPUT_HAZARD_MARKERS)

    def test_output_hazard_prose_accepted(self) -> None:
        assert find_missing_prose(" ".join(OUTPUT_HAZARD_MARKERS), OUTPUT_HAZARD_MARKERS) == []

    def test_absent_blocked_verdict_detected(self) -> None:
        assert blocked_is_conditional(self.NO_BLOCKED_AT_ALL) is not None

    def test_unconditional_blocked_detected(self) -> None:
        assert blocked_is_conditional(self.UNCONDITIONAL_BLOCKED) is not None

    def test_blocked_without_first_move_clause_detected(self) -> None:
        """Edge: conditional wording alone still permits BLOCKED as the opening move."""
        assert blocked_is_conditional(self.BLOCKED_FIRST_MOVE) is not None

    def test_shipped_prose_accepted(self) -> None:
        assert blocked_is_conditional(CLAUDE_CANONICAL.read_text(encoding="utf-8")) is None
