"""Structural guards for the security agent's review-scope tool contract.

Issue #4781: the security agent could not enumerate a changeset because no
surface granted it git or a pinned-diff retrieval path. It returned a blocked
verdict it could not justify. These tests pin the repaired contract:

* the Claude surfaces declare an explicit ``tools`` allowlist,
* that allowlist grants non-mutating git only, never a bare ``Bash``,
* write access is scoped to the agent's own report paths,
* every surface declares a pinned-diff retrieval path (SHA or PR),
* every surface carries the scope-enumeration protocol and makes ``[BLOCKED]``
  conditional on all three retrieval paths failing.

Each production assertion runs through a helper that the negative-control class
below also calls on defective fixtures, so a helper that stops detecting is
caught by its own control rather than passing silently.
"""

from __future__ import annotations

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

# Read-only git the review needs to enumerate and pin a changeset.
REQUIRED_GIT_READS = (
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git show:*)",
    "Bash(git log:*)",
    "Bash(git rev-parse:*)",
)

# Claude-side pinned-diff retrieval, used when local git is unavailable.
REQUIRED_PINNED_DIFF_CLAUDE = (
    "mcp__github__pull_request_read",
    "mcp__github__get_commit",
    "mcp__github__get_file_contents",
)

# Platform-side equivalents. Copilot and VS Code have no scoped shell, so a
# pinned SHA or PR diff is their only enumeration path.
REQUIRED_PINNED_DIFF_PLATFORM = (
    "github/pull_request_read",
    "github/get_commit",
    "github/get_file_contents",
    "github/list_commits",
)

# Any git subcommand that writes to the repository, the index, or a remote.
MUTATING_GIT_SUBCOMMANDS = (
    "add",
    "am",
    "apply",
    "branch",
    "checkout",
    "cherry-pick",
    "clean",
    "clone",
    "commit",
    "fetch",
    "init",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "reset",
    "restore",
    "revert",
    "rm",
    "stash",
    "submodule",
    "switch",
    "tag",
    "worktree",
)

# Write-capable tools that must never appear unscoped in a security allowlist.
WRITE_TOOL_NAMES = ("write", "edit", "notebookedit", "multiedit")

# GitHub MCP tools that mutate remote state.
MUTATING_GITHUB_TOOLS = (
    "mcp__github__create_or_update_file",
    "mcp__github__push_files",
    "mcp__github__delete_file",
    "mcp__github__merge_pull_request",
    "mcp__github__create_branch",
    "mcp__github__create_pull_request",
)

# Paths the security agent is allowed to write, per its own report templates.
ALLOWED_WRITE_ROOTS = (".agents/security/", ".agents/planning/impact-analysis-security-")

PROSE_MARKERS = (
    "### Review Scope Enumeration (required)",
    "git status --porcelain",
    "A caller-supplied diff artifact",
    "Record the pinned scope in the verdict",
    "MUST NOT while enumerating",
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


def _bash_argument(tool: str) -> str | None:
    """Return the argument inside ``Bash(...)``, or None when not a Bash grant.

    A bare ``Bash`` (no parentheses) returns the empty string, which callers
    treat as unscoped.
    """
    stripped = tool.strip()
    if stripped.casefold() == "bash":
        return ""
    if not stripped.casefold().startswith("bash("):
        return None
    if not stripped.endswith(")"):
        return ""
    return stripped[len("Bash(") : -1]


def find_unsafe_shell_grants(tools: list[str]) -> list[str]:
    """Return every shell grant that is unscoped or reaches a mutating command.

    A grant is safe only when it is ``Bash(git <read-subcommand>:...)``. Bare
    ``Bash``, a bare ``Bash(git:*)`` wildcard, and any non-git command all reach
    ``git commit`` or ``git push`` and are reported.
    """
    offenders: list[str] = []
    for tool in tools:
        argument = _bash_argument(tool)
        if argument is None:
            continue
        body = argument.split(":", 1)[0].strip()
        words = body.split()
        if len(words) < 2 or words[0] != "git":
            offenders.append(tool)
            continue
        if words[1].casefold() in MUTATING_GIT_SUBCOMMANDS:
            offenders.append(tool)
    return offenders


def find_unscoped_write_grants(tools: list[str]) -> list[str]:
    """Return write grants that are unscoped or point outside the report paths."""
    offenders: list[str] = []
    for tool in tools:
        stripped = tool.strip()
        base = stripped.split("(", 1)[0].casefold()
        if base not in WRITE_TOOL_NAMES:
            continue
        if "(" not in stripped or not stripped.endswith(")"):
            offenders.append(tool)
            continue
        target = stripped[len(base) + 1 : -1]
        if not target.startswith(ALLOWED_WRITE_ROOTS):
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
def test_claude_surface_grants_read_only_git(path: Path) -> None:
    tools = _tool_list(_frontmatter(path), "tools", path)

    missing = find_missing_tools(tools, REQUIRED_GIT_READS)
    assert not missing, f"{path.relative_to(REPO_ROOT)}: missing git read grants {missing}"


@pytest.mark.parametrize("path", CLAUDE_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_claude_surface_grants_no_mutating_shell(path: Path) -> None:
    tools = _tool_list(_frontmatter(path), "tools", path)

    offenders = find_unsafe_shell_grants(tools)
    assert not offenders, f"{path.relative_to(REPO_ROOT)}: unsafe shell grants {offenders}"


@pytest.mark.parametrize("path", CLAUDE_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_claude_surface_scopes_write_to_report_paths(path: Path) -> None:
    tools = _tool_list(_frontmatter(path), "tools", path)

    offenders = find_unscoped_write_grants(tools)
    assert not offenders, f"{path.relative_to(REPO_ROOT)}: unscoped write grants {offenders}"


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
    """Copilot and VS Code have no scoped shell; a pinned SHA or PR is their only path."""
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
def test_every_surface_makes_scope_blocked_conditional(path: Path) -> None:
    err = blocked_is_conditional(path.read_text(encoding="utf-8"))

    assert err is None, f"{path.relative_to(REPO_ROOT)}: {err}"


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_forbids_mutating_git_in_prose(path: Path) -> None:
    """The platform surfaces cannot scope shell, so the prohibition must be prose."""
    text = path.read_text(encoding="utf-8")

    for subcommand in ("commit", "push", "checkout", "reset", "stash", "clean"):
        assert f"`{subcommand}`" in text, (
            f"{path.relative_to(REPO_ROOT)}: prose does not forbid `git {subcommand}`"
        )


def test_claude_pair_stays_byte_identical() -> None:
    """The canonical and runtime Claude copies are hand-maintained in lockstep."""
    assert CLAUDE_CANONICAL.read_bytes() == CLAUDE_RUNTIME.read_bytes()


# --- Negative controls: the same helpers, run on defective input ---


class TestShellGrantControls:
    """Prove find_unsafe_shell_grants detects each way the grant can go wrong."""

    @pytest.mark.parametrize(
        "tools",
        [
            pytest.param(["Read", "Bash"], id="bare-bash"),
            pytest.param(["Read", "Bash(git:*)"], id="git-wildcard"),
            pytest.param(["Read", "Bash(git commit:*)"], id="git-commit"),
            pytest.param(["Read", "Bash(git push:*)"], id="git-push"),
            pytest.param(["Read", "Bash(git checkout:*)"], id="git-checkout"),
            pytest.param(["Read", "Bash(git reset:*)"], id="git-reset"),
            pytest.param(["Read", "Bash(git clean:*)"], id="git-clean"),
            pytest.param(["Read", "Bash(git worktree:*)"], id="git-worktree"),
            pytest.param(["Read", "Bash(gh pr merge:*)"], id="non-git-command"),
            pytest.param(["Read", "Bash(rm -rf:*)"], id="destructive-shell"),
            pytest.param(["Read", "Bash(uv run python:*)"], id="arbitrary-interpreter"),
            pytest.param(["Read", "bash"], id="lowercase-bare-bash"),
            pytest.param(["Read", "Bash(git status"], id="unterminated-grant"),
        ],
    )
    def test_unsafe_shell_grant_detected(self, tools: list[str]) -> None:
        assert find_unsafe_shell_grants(tools), f"should reject {tools}"

    @pytest.mark.parametrize(
        "tools",
        [
            pytest.param(list(REQUIRED_GIT_READS), id="the-shipped-allowlist"),
            pytest.param(["Read", "Bash(git ls-files:*)"], id="git-ls-files"),
            pytest.param(["Read", "Bash(git blame:*)"], id="git-blame"),
            pytest.param(["Read", "Grep", "mcp__github__get_commit"], id="no-shell-at-all"),
        ],
    )
    def test_safe_shell_grant_accepted(self, tools: list[str]) -> None:
        """Inverted control: a correct allowlist must produce no offender."""
        assert find_unsafe_shell_grants(tools) == []


class TestWriteGrantControls:
    """Prove find_unscoped_write_grants detects unscoped and out-of-scope writes."""

    @pytest.mark.parametrize(
        "tools",
        [
            pytest.param(["Read", "Write"], id="bare-write"),
            pytest.param(["Read", "Edit"], id="bare-edit"),
            pytest.param(["Read", "NotebookEdit"], id="bare-notebook-edit"),
            pytest.param(["Read", "Write(src/**)"], id="source-tree-write"),
            pytest.param(["Read", "Edit(.github/workflows/**)"], id="workflow-write"),
            pytest.param(["Read", "Write(.agents/**)"], id="too-wide-agents-write"),
            pytest.param(["Read", "Write(.agents/security/**"], id="unterminated-write"),
        ],
    )
    def test_unscoped_write_detected(self, tools: list[str]) -> None:
        assert find_unscoped_write_grants(tools), f"should reject {tools}"

    @pytest.mark.parametrize(
        "tools",
        [
            pytest.param(["Read", "Write(.agents/security/**)"], id="report-path"),
            pytest.param(
                ["Read", "Edit(.agents/planning/impact-analysis-security-foo.md)"],
                id="impact-analysis-path",
            ),
            pytest.param(["Read", "Grep", "Glob"], id="no-write-at-all"),
        ],
    )
    def test_scoped_write_accepted(self, tools: list[str]) -> None:
        assert find_unscoped_write_grants(tools) == []


class TestRemoteMutationControls:
    def test_mutating_github_tool_detected(self) -> None:
        assert find_mutating_github_grants(["Read", "mcp__github__push_files"])

    def test_read_only_github_tools_accepted(self) -> None:
        assert find_mutating_github_grants(list(REQUIRED_PINNED_DIFF_CLAUDE)) == []


class TestMissingToolControls:
    def test_missing_required_tool_detected(self) -> None:
        assert find_missing_tools(["Read"], REQUIRED_GIT_READS) == list(REQUIRED_GIT_READS)

    def test_present_required_tools_accepted(self) -> None:
        assert find_missing_tools(list(REQUIRED_GIT_READS), REQUIRED_GIT_READS) == []

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

    def test_absent_blocked_verdict_detected(self) -> None:
        assert blocked_is_conditional(self.NO_BLOCKED_AT_ALL) is not None

    def test_unconditional_blocked_detected(self) -> None:
        assert blocked_is_conditional(self.UNCONDITIONAL_BLOCKED) is not None

    def test_blocked_without_first_move_clause_detected(self) -> None:
        """Edge: conditional wording alone still permits BLOCKED as the opening move."""
        assert blocked_is_conditional(self.BLOCKED_FIRST_MOVE) is not None

    def test_shipped_prose_accepted(self) -> None:
        assert blocked_is_conditional(CLAUDE_CANONICAL.read_text(encoding="utf-8")) is None
