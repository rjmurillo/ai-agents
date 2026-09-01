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

import os
import re
import subprocess
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

# Bare tool names the enumeration protocol needs on a Claude surface. Reading
# the pinned snapshot and writing the report are the whole job.
REQUIRED_CLAUDE_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Write",
)

# Tool grants no security surface may declare. `Bash` is the CWE-78 carrier the
# PR #5356 review flagged: a settings-file deny rule matches command text
# case-sensitively while git config keys are case-insensitive, so
# `git -c Diff.External=<cmd>` reaches the same handler as the denied
# `diff.external`. Enumerating casings is not a control and a session-wide deny
# on the mutating subcommands breaks every other agent (the #5013 shape), so the
# absent grant is the only enforcement available. `Edit` goes with it: the
# deliverables are new report files, which `Write` creates, so `Edit` bought a
# source-mutation vector and no capability.
FORBIDDEN_CLAUDE_TOOLS = (
    "Bash",
    "Edit",
)

# Claude-side pinned-diff retrieval. With no shell on any surface this is the
# enumeration path, not a fallback.
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

# GitHub MCP tools that are confirmed read-only. Any GitHub tool granted to the
# security agent MUST appear here. A tool absent from this list is treated as
# potentially mutating, which is the fail-closed direction: refusing a read
# costs one investigation, granting a write costs a compromised review.
READONLY_GITHUB_TOOLS = frozenset({
    "mcp__github__get_commit",
    "mcp__github__get_file_contents",
    "mcp__github__issue_read",
    "mcp__github__list_commits",
    "mcp__github__pull_request_read",
    "mcp__github__search_code",
    "mcp__github__search_issues",
    "mcp__github__search_repositories",
    "mcp__github__search_users",
    "mcp__github__get_issue",
    "mcp__github__list_issues",
    "mcp__github__list_pull_requests",
    "mcp__github__get_pull_request",
    "mcp__github__get_pull_request_diff",
    "mcp__github__get_pull_request_files",
    "mcp__github__get_pull_request_reviews",
    "mcp__github__get_pull_request_comments",
    "mcp__github__list_branches",
    "mcp__github__list_tags",
    # Platform (Copilot/VS Code) `$toolset:github-research` grants read-only
    # alert and PR-search tools the Claude surfaces have no equivalent call
    # for. Read-only per the GitHub API (list/get, never create or dismiss),
    # so they belong on this allowlist rather than tripping the platform
    # remote-mutation check below as false-positive offenders.
    "mcp__github__list_code_scanning_alerts",
    "mcp__github__get_code_scanning_alert",
    "mcp__github__list_secret_scanning_alerts",
    "mcp__github__list_dependabot_alerts",
    "mcp__github__search_pull_requests",
})

# Markers every surface must carry, whatever tools its harness grants.
PROSE_MARKERS = (
    "### Review Scope Enumeration (required)",
    "skipping any whose tools this",
    "A caller-supplied diff artifact",
    "Record the pinned scope in the verdict",
    "MUST NOT while enumerating",
)

# No surface grants a shell any more, so the prose must say so plainly rather
# than gate a local-git path on a capability nobody has. A surface that still
# describes running git locally is describing a tool the agent cannot call.
NO_SHELL_PROSE_MARKERS = (
    "No surface grants this agent a shell",
    "never through a local command",
    "Do not delegate the review itself",
)

# Wording that would put a local git command back in the protocol. These are
# the exact strings the pre-fix prose carried; if any returns, the agent is
# being told to run something it has no tool for.
REVIVED_SHELL_PROSE = (
    "If a shell tool is granted (Claude surfaces only):",
    "git status --porcelain",
    "**Local read-only git.**",
)

# Finding 3 of the PR #5356 review: `git diff` omits staged changes and no
# ordinary diff form carries untracked files, so a staged-only or new-file
# change could take a verdict without its content ever being read. The snapshot
# must be complete and the file count must come from that same snapshot.
SNAPSHOT_COMPLETENESS_MARKERS = (
    "`git diff HEAD` rather than a bare `git diff`",
    "which omits staged changes",
    "every untracked file the",
    "Derive the changed-file count from the same snapshot",
)

# Finding 1 of the same review. The prose must record why a denylist cannot be
# the control, so nobody re-adds the shell and re-derives the deny rules.
CASE_SENSITIVITY_MARKERS = (
    "matches command text case-sensitively",
    "git config keys",
    "`Diff.External`",
)

# Finding 6 of the same review. The PowerShell validation block runs
# `dotnet test`, lefthook, and `git diff --cached`; with no shell the agent must
# request that run rather than attempt it.
VALIDATION_REQUEST_MARKERS = (
    "CI Environment Security Testing (request, do not run)",
    "**You cannot run them.**",
    "Ask the caller or",
)

# A read-only subcommand allowlist does not make a command read-only: `git diff`,
# `git log`, `git show`, and `git blame` all accept `--output=<path>`. Measured on
# this branch against git 2.43.0, all four wrote their target and exited 0, and
# `git -c diff.external=<cmd> diff` executed `<cmd>`. Removing the shell grant is
# what closes those, so the prose must name the hazard the absent grant addresses
# rather than leave a future reader to re-add `Bash` believing it was harmless.
OUTPUT_HAZARD_MARKERS = (
    "the `--output` and `-o`",
    "write a file wherever you point it",
    "config injection such as",
)

# Prompt obligations on every surface: `Write` on Claude and `$toolset:editor`
# on Copilot and VS Code are both unscoped, so the report-path limit is prose.
# The shell limit is no longer in this class; it is enforced by absence.
OBLIGATION_MARKERS = (
    "obligations this prompt places on you, not properties of",
    "No harness scopes the rest for you",
    "hold the line yourself",
)

# Wording that would claim an enforcement no surface currently has.
OVERCLAIM_PHRASES = (
    "Mutating git is never granted",
    "a guard that denies",
    "PreToolUse guard",
)

BLOCKED_SENTENCE = (
    "Return `[BLOCKED] Cannot evaluate: review scope not enumerable` only when all\npaths fail."
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


_MCP_GITHUB_PREFIX = "mcp__github__"
_PLATFORM_GITHUB_PREFIX = "github/"


def find_mutating_github_grants(tools: list[str]) -> list[str]:
    """Return declared GitHub tools that are NOT on the read-only allowlist.

    Fail-closed: any GitHub MCP tool not explicitly allowlisted is treated as
    potentially mutating. This catches tools like update_pull_request,
    add_issue_comment, run_workflow, and rerun_failed_jobs that an incomplete
    blacklist would miss.

    Normalizes both naming forms this repository's surfaces use for the same
    GitHub tool: Claude's MCP form ``mcp__github__<name>`` and the platform
    ``$toolset:github-research`` form ``github/<name>`` (Copilot, VS Code).
    Checking only the ``mcp__github__`` prefix left every platform grant
    unexamined, since none of them ever match it: a mutating platform entry
    such as ``github/push_files`` would pass this guard while this test
    stayed green (issue #5356 review).

    A bare whole-server grant, ``mcp__github`` with no ``__<tool>`` suffix,
    is also flagged unconditionally: ``MCP_TOOL_NAME`` and the parseability
    tests accept that form, and it grants every tool the server exposes,
    mutators included, so it is never something a per-tool allowlist can
    cover (issue #5356 review).
    """
    readonly_lower = {name.casefold() for name in READONLY_GITHUB_TOOLS}
    offenders = []
    for tool in tools:
        stripped = tool.strip()
        lowered = stripped.casefold()
        if lowered == "mcp__github":
            offenders.append(stripped)
            continue
        if lowered.startswith(_MCP_GITHUB_PREFIX):
            canonical = lowered
        elif lowered.startswith(_PLATFORM_GITHUB_PREFIX):
            canonical = _MCP_GITHUB_PREFIX + lowered[len(_PLATFORM_GITHUB_PREFIX) :]
        else:
            continue
        if canonical not in readonly_lower:
            offenders.append(stripped)
    return offenders


def find_missing_tools(tools: list[str], required: tuple[str, ...]) -> list[str]:
    """Return the required tool names absent from *tools*."""
    normalized = {tool.strip().casefold() for tool in tools}
    return [name for name in required if name.casefold() not in normalized]


def find_present_tools(tools: list[str], forbidden: tuple[str, ...]) -> list[str]:
    """Return the forbidden tool names present in *tools*.

    Casefolded on both sides on purpose. Claude Code's own ``tools`` loader is
    the authority on which spelling grants the tool, and this check must not be
    the thing that a `bash` or `BASH` entry slips past. That is the same
    case-blindness bug, one layer up, that the absent grant exists to avoid.
    """
    normalized = {tool.strip().casefold() for tool in tools}
    return [name for name in forbidden if name.casefold() in normalized]


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
    """Reading the pinned snapshot and writing the report are the whole job."""
    tools = _tool_list(_frontmatter(path), "tools", path)

    missing = find_missing_tools(tools, REQUIRED_CLAUDE_TOOLS)
    assert not missing, f"{path.relative_to(REPO_ROOT)}: missing tool grants {missing}"


@pytest.mark.parametrize("path", CLAUDE_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_claude_surface_grants_no_shell_and_no_editor(path: Path) -> None:
    """`Bash` is the CWE-78 carrier the PR #5356 review flagged as Risk 8/10.

    The deny rules in the repository settings file cannot substitute for the
    absent grant: they match command text case-sensitively, and git config keys
    are case-insensitive, so `git -c Diff.External=<cmd>` runs `<cmd>` while no
    lowercase rule matches. Enumerating casings is not a control. Absence is.

    `Edit` rides along because issue #4781's acceptance criterion puts write,
    commit, push, and secret reads out of reach, and `Edit` reached source files
    while adding nothing the report writes need.
    """
    tools = _tool_list(_frontmatter(path), "tools", path)

    present = find_present_tools(tools, FORBIDDEN_CLAUDE_TOOLS)
    assert not present, (
        f"{path.relative_to(REPO_ROOT)}: declares forbidden grants {present}. "
        f"A shell grant reopens `git -c Diff.External=` (case-insensitive to git, "
        f"case-sensitive to the deny matcher) and `git commit`/`git push`."
    )


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


@pytest.mark.parametrize("path", PLATFORM_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_platform_surface_grants_no_remote_mutation(path: Path) -> None:
    """The same fail-closed check `test_claude_surface_grants_no_remote_mutation`
    runs, applied to the `github/<name>` naming platform surfaces use instead of
    Claude's `mcp__github__<name>`.
    """
    tools = _tool_list(_frontmatter(path), "tools", path)

    offenders = find_mutating_github_grants(tools)
    assert not offenders, f"{path.relative_to(REPO_ROOT)}: remote-mutating grants {offenders}"


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
def test_every_surface_states_that_no_shell_is_granted(path: Path) -> None:
    """One body reaches six surfaces, so the no-shell statement must travel with it.

    A surface that still offers a local-git path is describing a tool the agent
    cannot call, which is issue #4781's symptom wearing the opposite costume: the
    agent follows step 1, gets nothing, and blocks on scope.
    """
    text = path.read_text(encoding="utf-8")

    missing = find_missing_prose(text, NO_SHELL_PROSE_MARKERS)
    assert not missing, f"{path.relative_to(REPO_ROOT)}: no-shell contract unstated {missing}"


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_surface_revives_the_local_git_path(path: Path) -> None:
    """The removed local-git step must not come back while no surface has a shell."""
    text = path.read_text(encoding="utf-8")

    revived = [marker for marker in REVIVED_SHELL_PROSE if marker in text]
    assert not revived, (
        f"{path.relative_to(REPO_ROOT)}: local-git enumeration prose is back {revived}; "
        f"no surface grants a shell, so this step cannot be followed"
    )


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_requires_a_complete_snapshot(path: Path) -> None:
    """A staged-only or new-file change must not take a verdict unreviewed.

    `git diff` omits staged changes and no ordinary diff form carries untracked
    files, so an artifact built from either can hide the whole change while the
    verdict reads as covering it.
    """
    text = path.read_text(encoding="utf-8")

    missing = find_missing_prose(text, SNAPSHOT_COMPLETENESS_MARKERS)
    assert not missing, (
        f"{path.relative_to(REPO_ROOT)}: snapshot completeness unstated {missing}"
    )


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_records_why_a_denylist_is_not_the_control(path: Path) -> None:
    """Without this, the next reader re-adds `Bash` and re-derives the deny rules."""
    text = path.read_text(encoding="utf-8")

    missing = find_missing_prose(text, CASE_SENSITIVITY_MARKERS)
    assert not missing, (
        f"{path.relative_to(REPO_ROOT)}: case-sensitivity limit unstated {missing}"
    )


@pytest.mark.parametrize(
    "path", ALL_SECURITY_SURFACES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_every_surface_reframes_the_validation_block_as_a_request(path: Path) -> None:
    """`Run no other command` and a block running `dotnet test` cannot both hold.

    The PowerShell block runs `dotnet test`, a lefthook invocation, and
    `git diff --cached`. With no shell the agent cannot run any of it, so the
    prompt must ask for the run rather than instruct one it cannot perform.
    """
    text = path.read_text(encoding="utf-8")

    missing = find_missing_prose(text, VALIDATION_REQUEST_MARKERS)
    assert not missing, (
        f"{path.relative_to(REPO_ROOT)}: validation block still reads as executable "
        f"{missing}; it contradicts the no-shell contract"
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
def test_every_surface_names_the_mutations_the_absent_shell_closes(path: Path) -> None:
    """Name what the absent grant buys, or the next reader cannot weigh re-adding it.

    These four are issue #4781's acceptance criterion. Before this change they
    were prompt obligations against a bare `Bash` grant; now they are unreachable,
    and the prose has to say which it is so a reviewer can tell a control from a
    promise.
    """
    text = path.read_text(encoding="utf-8")

    for subcommand in ("commit", "push", "checkout", "reset"):
        assert f"`{subcommand}`" in text, (
            f"{path.relative_to(REPO_ROOT)}: prose does not name `git {subcommand}` "
            f"among the mutations the absent shell closes"
        )


def test_claude_pair_stays_byte_identical() -> None:
    """The canonical and runtime Claude copies are hand-maintained in lockstep."""
    assert CLAUDE_CANONICAL.read_bytes() == CLAUDE_RUNTIME.read_bytes()


def test_a_bare_git_diff_really_hides_staged_and_new_files(tmp_path: Path) -> None:
    """Live control for the completeness prose: the hazard is real, not theoretical.

    PR #5356 finding 3 says a staged-only or new-file change can take a security
    verdict without its content ever being read. This builds that exact repository
    and measures it against real git rather than asserting it from memory:

    - a staged edit is invisible to a bare `git diff` and visible to `git diff HEAD`
    - an untracked new file is invisible to BOTH, so no diff form covers it

    If a future git changes either behaviour, this fails and the completeness
    paragraph in the six agent surfaces can be relaxed. Until then it is the
    evidence behind that paragraph.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig-absent"),
        "GIT_CONFIG_SYSTEM": str(tmp_path / "gitconfig-absent"),
        "GIT_TERMINAL_PROMPT": "0",
    }

    def git(*args: str) -> str:
        run = subprocess.run(
            ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=False
        )
        return run.stdout

    if subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=False).returncode != 0:
        pytest.skip("git is unavailable in this environment")
    git("config", "user.email", "control@example.invalid")
    git("config", "user.name", "control")
    (repo / "tracked.txt").write_text("original\n", encoding="utf-8")
    git("add", "tracked.txt")
    git("commit", "-qm", "seed")

    # The two shapes the review named: a staged edit and an untracked new file.
    (repo / "tracked.txt").write_text("STAGED_SECRET_CHANGE\n", encoding="utf-8")
    git("add", "tracked.txt")
    (repo / "new_file.txt").write_text("UNTRACKED_SECRET_CHANGE\n", encoding="utf-8")

    bare_diff = git("diff")
    head_diff = git("diff", "HEAD")
    untracked = git("ls-files", "--others", "--exclude-standard")

    assert "STAGED_SECRET_CHANGE" not in bare_diff, (
        "control failed: a bare `git diff` showed a staged change, so the "
        "completeness prose is warning about a hazard that does not exist"
    )
    assert "STAGED_SECRET_CHANGE" in head_diff, (
        "control failed: `git diff HEAD` did not show the staged change, so it "
        "is not the remedy the prose names"
    )
    assert "UNTRACKED_SECRET_CHANGE" not in bare_diff
    assert "UNTRACKED_SECRET_CHANGE" not in head_diff, (
        "control failed: `git diff HEAD` showed untracked content, so the prose "
        "requirement to add untracked file content separately is unnecessary"
    )
    assert "new_file.txt" in untracked, (
        "control failed: the new file was not untracked, so this test did not "
        "build the changeset shape it claims to measure"
    )


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

    def test_bare_whole_server_grant_detected(self) -> None:
        """`mcp__github` with no `__<tool>` suffix grants every server tool,
        mutators included, so a per-tool allowlist can never clear it."""
        assert find_mutating_github_grants(["Read", "mcp__github"]) == ["mcp__github"]

    def test_mutating_platform_github_tool_detected(self) -> None:
        """The naming form platform surfaces use, not just Claude's MCP form."""
        assert find_mutating_github_grants(["read", "github/push_files"])

    def test_read_only_platform_github_tools_accepted(self) -> None:
        assert find_mutating_github_grants(list(REQUIRED_PINNED_DIFF_PLATFORM)) == []


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

    def test_missing_no_shell_statement_detected(self) -> None:
        """Edge: a surface that says nothing about the shell fails the pin."""
        silent = "Work these paths in order and stop at the first pinned scope.\n"

        assert find_missing_prose(silent, NO_SHELL_PROSE_MARKERS)

    def test_no_shell_statement_accepted(self) -> None:
        joined = " ".join(NO_SHELL_PROSE_MARKERS)

        assert find_missing_prose(joined, NO_SHELL_PROSE_MARKERS) == []

    def test_revived_local_git_step_detected(self) -> None:
        """Edge: re-adding the local-git step is the regression this pin catches."""
        revived = "1. **Local read-only git.** Run `git status --porcelain` for the diff.\n"

        assert [marker for marker in REVIVED_SHELL_PROSE if marker in revived]

    def test_shipped_prose_has_no_revived_local_git_step(self) -> None:
        clean = " ".join(NO_SHELL_PROSE_MARKERS)

        assert [marker for marker in REVIVED_SHELL_PROSE if marker in clean] == []

    def test_partial_snapshot_prose_detected(self) -> None:
        """Edge: naming the artifact path without the completeness bar is the defect.

        This is the exact shape of PR #5356's finding 3: an artifact built from a
        bare `git diff` omits staged changes, and no ordinary diff form carries
        untracked files, so a new-file change reads as an empty changeset.
        """
        partial = "2. **A caller-supplied diff artifact.** Read the diff file named.\n"

        assert find_missing_prose(partial, SNAPSHOT_COMPLETENESS_MARKERS)

    def test_complete_snapshot_prose_accepted(self) -> None:
        joined = " ".join(SNAPSHOT_COMPLETENESS_MARKERS)

        assert find_missing_prose(joined, SNAPSHOT_COMPLETENESS_MARKERS) == []

    def test_denylist_claim_without_case_limit_detected(self) -> None:
        """Edge: naming the deny rules without their case limit is the overclaim."""
        partial = "The deny rules block `--output`, `--exec-path`, and `diff.external`.\n"

        assert find_missing_prose(partial, CASE_SENSITIVITY_MARKERS)

    def test_case_limit_prose_accepted(self) -> None:
        joined = " ".join(CASE_SENSITIVITY_MARKERS)

        assert find_missing_prose(joined, CASE_SENSITIVITY_MARKERS) == []

    def test_executable_validation_block_detected(self) -> None:
        """Edge: the pre-fix heading reads as an instruction to run the block."""
        executable = "3. **CI Environment Security Testing**\n\nReproduce CI locally:\n"

        assert find_missing_prose(executable, VALIDATION_REQUEST_MARKERS)

    def test_validation_request_prose_accepted(self) -> None:
        joined = " ".join(VALIDATION_REQUEST_MARKERS)

        assert find_missing_prose(joined, VALIDATION_REQUEST_MARKERS) == []

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
