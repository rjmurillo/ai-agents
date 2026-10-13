#!/usr/bin/env python3
# taste-lint: ignore file-size -- always-on unit tests and opt-in e2e smokes must
# coexist in one file (same plugin contract, one source of truth per issue #3148).
"""End-to-end plugin and agent-contract smoke for the shipped CLIs.

PR #2735 was green on unit tests, schema checks, and generated-file checks, yet a
broken skill front-matter field (``argument-hint must be a string``) could still
reach a customer because nothing loaded the plugin in the real CLI and asserted
the skills loaded. These tests close that gap: they launch the REAL CLIs, load
the shipped plugin directory, and assert the plugin loads.

  - Copilot (REQ-047 D25): the GATE spends no model quota. ``copilot --plugin-dir
    <repo>/src/copilot-cli skill list --json`` runs from a neutral cwd under an
    isolated ``COPILOT_HOME``, must return 0 with no ``argument-hint`` loader
    warning (issue #2736), and must list every ``EXPECTED_SKILLS`` name from a
    ``source: plugin`` record whose path is under ``src/copilot-cli``. It never
    skips on quota. The prompt-based checks (the fired-hook probe of issue #3148,
    its negative control, and the agent runtime probes) are best-effort: a spent
    quota skips with ``QUOTA_SKIP:`` (D26), which the Copilot and Claude CI legs
    allow through ``assert_smoke_ran.py --allow-skip-marker``. Auth, rate limit,
    and transport blocks fail in CI. The shared probe lives
    in ``tests/e2e/copilot_hook_probe.py``.
  - Claude: ``claude --plugin-dir <repo>/.claude plugin list`` and
    ``plugin details project-toolkit`` with ``cwd`` set to a neutral directory.
    Assert returncode 0, the manifest name appears, and the expected lifecycle
    skills are present in the details output.
  - Codex (REQ-047): ``codex plugin marketplace add <repo>`` and ``codex plugin add
    project-toolkit@ai-agents`` install the shipped plugin into an isolated
    ``CODEX_HOME``, ``codex plugin list --json`` shows it installed and enabled,
    and ``codex debug prompt-input`` lists every ``EXPECTED_SKILLS`` name as
    ``project-toolkit:<name>``. No model call and no credential: the commands
    read the repository and the isolated home only.
  - Grok Build (ADR-115 Decision 9): ``grok plugin marketplace add <repo>`` and
    ``grok plugin install project-toolkit@<marketplace> --trust`` install the
    shipped plugin into a scratch ``GROK_HOME``; ``plugin details`` and ``plugin
    validate`` must report the expected components and a valid manifest, and an
    installed skill script must run with both plugin-root variables unset (a copy
    without ``lib/`` is the negative control). No login, no model call.
  - Analyst contract (issue #3918): load the project analyst in each real CLI
    and assert its exact reviewed read-only tool set. Each probe also loads an
    execution agent that must expose shell and edit tools, so the test cannot
    pass when the CLI stops reporting tool availability.
  - Model id contract (issue #5333, ADR-080): an isolated ``--plugin-dir`` agent
    pinned to the Copilot opus-tier id from ``templates/platforms/copilot-cli.yaml``
    must run without the CLI's "specifies model ... which is not available"
    warning. A bogus id in the same harness must print that warning (the negative
    control). The CLI exits 0 and falls back to ``auto`` on a bad id, so the
    warning, not the exit code, is the signal.

Startup probe (issue #6000): before the first test that needs a CLI, one
``<cli> --version`` runs with a 10s timeout. "Needs a CLI" means the test
carries a ``copilot``, ``claude``, ``codex``, or ``grok`` marker. A CLI that hangs there
(a wrapper shim that blocks with no TTY) reports an error at setup of the first
test that uses it, naming the resolved executable path, and the dependent tests
skip. A hung CLI costs about 10s, not one full timeout per test.

Why version-agnostic (issue #3148): earlier the smoke keyed the benign path on a
per-version allowlist (``_COPILOT_BENIGN_NO_ENUM_VERSIONS``) plus a "zero
source: plugin records" check. That needed a manual bump every Copilot CLI
release and flaked on machines with globally installed plugins (surfaced under
``source: plugin`` with ``pluginName: null``). The fired-hook signal removes both
problems: a hook fires or it does not, on every version.

This is the plugin-LOAD smoke. The plugin-HOOK anchoring smoke lives in
``tests/e2e/test_cli_hook_e2e.py``. Both run in the same PR workflow
(``.github/workflows/plugin-cli-smoke.yml``) under ``RUN_CLI_E2E=1``; each has its own
JUnit report so a silent skip of either is a red run.

Why opt-in: these spawn real CLIs that need authentication and spend model
credits, which bare CI does not have. They run wherever the CLIs are installed
and ``RUN_CLI_E2E=1`` is set (local dev, the CLI smoke job with secrets); elsewhere
they SKIP with a loud reason so a skipped run never reads as a passed run. The
fast, always-on guards are the unit checks at the bottom of this file: they pin
the expected-skills set against the shipped plugin trees, and pin the fired-hook
detector's positive and negative controls, with no CLI.

Run locally:
    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_plugin_load_smoke.py -v -m "not copilot"

Copilot cases run only in CI, behind the agent-copilot environment.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, Protocol, TypeVar

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py), so
# add it for the sibling copilot_hook_probe import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_original_sys_path = sys.path.copy()
try:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cli_exec import resolve_executable
    from redact_secrets import redact
finally:
    sys.path[:] = _original_sys_path

# Fired-hook probe: ONE source of truth shared with test_cli_hook_e2e.py (#3148).
from copilot_hook_probe import (  # noqa: E402
    PROBE_EVENT,
    copilot_command,
    manifest,
    probe_name,
    run_copilot_plugin_dir,
    write_marker_probe_plugin,
)
from smoke_skip_policy import (  # noqa: E402
    QUOTA_SKIP_MARKER,
    skip_or_fail_on_claude_block,
    skip_or_fail_on_copilot_block,
)


def _skip_on_copilot_block(result: subprocess.CompletedProcess[str]) -> None:
    """Apply the D26 block policy to a Copilot run.

    Spent quota skips with QUOTA_SKIP:, which plugin-cli-smoke.yml allows through
    ``assert_smoke_ran.py --allow-skip-marker``. Auth, rate limit, and transport
    blocks fail in CI and skip unmarked locally, so the gate stays red on them
    (issues #4504, #4483, #3275).
    """
    skip_or_fail_on_copilot_block(result)


_RUN = os.environ.get("RUN_CLI_E2E") == "1"

# The lifecycle skills PR #2735 verified by hand. They ship in BOTH plugin trees
# (src/copilot-cli/skills/<name>/ and .claude/commands/<name>.md), so the same
# set is the load contract for both CLIs. The always-on unit checks below pin
# this set against the on-disk trees so a rename fails without a real CLI.
EXPECTED_SKILLS = frozenset({"build", "plan", "ship", "test", "review", "spec", "sync"})

# The five frontmatter-less documents issue #5493 removed from `.claude/agents/`.
# Stems, because the loader names an agent by its file stem.
NON_AGENT_DOCUMENT_STEMS = frozenset(
    {
        "AGENTS",
        "CLAUDE",
        "dependency-risk-scoring",
        "powershell-security-checklist",
        "threat-model-template",
    }
)

_COPILOT_PLUGIN_DIR = REPO_ROOT / "src" / "copilot-cli"
# ADR-109 B6: project-toolkit's marketplace source moved from `./.claude` to
# `./src/claude`. Load the plugin from the marketplace-listed source, not the
# binplaced dogfood copy at `.claude/`, so this smoke proves what a fresh
# install actually resolves.
_CLAUDE_PLUGIN_DIR = REPO_ROOT / "src" / "claude"
_CLAUDE_MANIFEST = _CLAUDE_PLUGIN_DIR / ".claude-plugin" / "plugin.json"
_CLAUDE_ANALYST_TOOLS = frozenset(
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
        "mcp__serena__find_declaration",
        "mcp__serena__find_implementations",
        "mcp__serena__find_referencing_symbols",
        "mcp__serena__find_symbol",
        "mcp__serena__get_diagnostics_for_file",
        "mcp__serena__get_symbols_overview",
        "mcp__serena__initial_instructions",
        "mcp__serena__list_memories",
        "mcp__serena__read_memory",
    }
)
# The reviewed security-agent grant (issue #4781, PR #5356). `Bash` and `Edit`
# are deliberately absent: the agent enumerates a review from a pinned GitHub
# diff or a caller-supplied artifact, never from a local command. That absence
# is the enforcement for the acceptance criterion "commit, push, and
# branch-mutation capabilities remain unavailable", because a settings-file deny
# rule cannot substitute for it (it matches command text case-sensitively while
# git config keys are case-insensitive, so `git -c Diff.External=` slips it).
_CLAUDE_SECURITY_TOOLS = frozenset(
    {
        "Read",
        "Grep",
        "Glob",
        "WebSearch",
        "WebFetch",
        "TodoWrite",
        "Write",
        "mcp__github__pull_request_read",
        "mcp__github__get_commit",
        "mcp__github__list_commits",
        "mcp__github__get_file_contents",
        "mcp__github__search_code",
        "mcp__github__issue_read",
        "mcp__serena__list_memories",
        "mcp__serena__read_memory",
        "mcp__serena__write_memory",
        "mcp__serena__edit_memory",
    }
)
_CLAUDE_SECURITY_FORBIDDEN_TOOLS = frozenset({"Bash", "Edit"})
_SECURITY_AGENT_FILE = REPO_ROOT / ".claude" / "agents" / "security.md"

_COPILOT_ANALYST_TOOLS = frozenset(
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
        "serena/find_declaration",
        "serena/find_implementations",
        "serena/find_referencing_symbols",
        "serena/find_symbol",
        "serena/get_diagnostics_for_file",
        "serena/get_symbols_overview",
        "serena/initial_instructions",
        "serena/list_memories",
        "serena/read_memory",
    }
)

# The skill-loader warning class issue #2736 must catch before merge. Copilot
# CLI emits this on stderr when a skill's front matter has a non-string
# argument-hint; the schema check passes but the real loader rejects it.
_ARGUMENT_HINT_WARNING = "argument-hint"

# A healthy run takes under 10s; a spent Copilot quota retried for 72s before
# exiting (issue #6181). The ceiling also bounds an all-hang push: every smoke
# test stops at its first CLI timeout, and that sum must stay under the
# pre-push cap, CLI_E2E_TIMEOUT_SECONDS in git_hook_policy.py.
_CLI_TIMEOUT_SECONDS = 120
_VERSION_TIMEOUT_SECONDS = 60
# One `--version` per CLI per session tells a hung launcher from a slow model
# call. A healthy CLI answers in under 1s; a shim that blocks with no TTY never
# does. Without the probe every test waited out its full timeout (issue #6000).
_STARTUP_PROBE_TIMEOUT_SECONDS = 10
_PROBED_CLIS = ("copilot", "claude", "codex", "grok")
# `copilot skill list --json` reads local plugin files and makes no model call;
# it returns in about half a second, so a hang is a defect, not latency.
_SKILL_LIST_TIMEOUT_SECONDS = 30
# pyproject sets a global --timeout of 120s, which shares one budget across
# every subprocess in a test. It killed two-run tests before their CLI output
# reached the block classifier (issue #6181). Each real-CLI test declares its
# own budget: the sum of its subprocess timeouts plus this margin.
_PYTEST_MARGIN_SECONDS = 30


def _cli_budget(*subprocess_timeouts: int) -> pytest.MarkDecorator:
    """pytest-timeout marker that outlasts every subprocess timeout in a test."""
    return pytest.mark.timeout(sum(subprocess_timeouts) + _PYTEST_MARGIN_SECONDS)


_PLUGIN_ROOT_ENV_KEYS = {"CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "COPILOT_PLUGIN_ROOT"}

F = TypeVar("F", bound=Callable[..., object])


def _requires_cli(cli: str) -> Callable[[F], F]:
    """Skip without RUN_CLI_E2E=1 and the CLI, and tag the test with its CLI.

    The ``claude``, ``copilot``, and ``codex`` markers let the CLI smoke select
    one provider's tests per matrix leg (``-m "smoke and claude"``), so each leg
    needs only its own credential (the codex leg needs none).
    """
    skip = pytest.mark.skipif(
        not (_RUN and shutil.which(cli)),
        reason=f"needs RUN_CLI_E2E=1 and the {cli} CLI on PATH (real auth + credits)",
    )
    tag = getattr(pytest.mark, cli)

    def decorate(test: F) -> F:
        return tag(skip(test))

    return decorate


requires_copilot = _requires_cli("copilot")
requires_claude = _requires_cli("claude")
requires_codex = _requires_cli("codex")
requires_grok = _requires_cli("grok")


def _clean_env() -> dict[str, str]:
    """Env for the CLI subprocess with inherited plugin-root vars stripped.

    A parent Claude session or the pre-push hook may export these; strip them so
    the CLI under test resolves the plugin from ``--plugin-dir``, not from an
    inherited root that points at a different tree.
    """
    env = os.environ.copy()
    for key in list(env):
        if key.upper() in _PLUGIN_ROOT_ENV_KEYS:
            env.pop(key, None)
    return env


def _run_cli(
    args: list[str],
    *,
    timeout: int,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=_clean_env(),
    )


class _MarkerSource(Protocol):
    def get_closest_marker(self, name: str) -> object | None: ...


def _probe_cli_startup(cli: str) -> str | None:
    """Run ``<cli> --version`` once and return a hang message, or None if it answers.

    Only a timeout counts as a hang. A non-zero exit or a missing binary is left
    to the tests, which classify those with their own policy.
    """
    resolved = shutil.which(cli)
    if resolved is None:
        return None
    try:
        flags = ["--no-auto-update"] if cli == "copilot" else []
        _run_cli([resolved, *flags, "--version"], timeout=_STARTUP_PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return (
            f"{cli} CLI did not answer `--version` within {_STARTUP_PROBE_TIMEOUT_SECONDS}s. "
            f"Resolved executable: {resolved}. A wrapper or shim that blocks at startup "
            f"(for example one that loads secrets with no TTY) hangs every dependent test."
        )
    return None


def _gate_on_startup_probe(cli: str, results: dict[str, str | None]) -> None:
    """Fail once when ``cli`` hangs at startup, then skip its dependent tests.

    ``results`` caches the probe per CLI for the whole session, so a hung CLI
    costs one probe timeout instead of one full timeout per test (issue #6000).
    """
    if cli in results:
        if results[cli] is not None:
            pytest.skip(f"{cli} CLI hung at startup; reported by the first test that used it")
        return
    hang = _probe_cli_startup(cli)
    results[cli] = hang
    if hang is not None:
        pytest.fail(hang, pytrace=False)


def _probe_clis_marked_on(node: _MarkerSource, results: dict[str, str | None]) -> None:
    """Gate every probed CLI whose marker the test carries."""
    for cli in _PROBED_CLIS:
        if node.get_closest_marker(cli) is not None:
            _gate_on_startup_probe(cli, results)


@pytest.fixture(scope="session")
def _cli_startup_probe_results() -> dict[str, str | None]:
    return {}


@pytest.fixture(autouse=True)
def _cli_startup_probe(
    request: pytest.FixtureRequest, _cli_startup_probe_results: dict[str, str | None]
) -> None:
    """Probe each CLI before the first real-CLI test that needs it."""
    if _RUN:
        _probe_clis_marked_on(request.node, _cli_startup_probe_results)


def _json_events(run: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in run.stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(f"CLI emitted non-JSON event: {exc}. line={line[-600:]!r}")
        assert isinstance(event, dict), f"CLI event must be an object: {event!r}"
        events.append(event)
    return events


def _skip_on_claude_block(run: subprocess.CompletedProcess[str], subject: str) -> None:
    """Apply the D26 block policy to a Claude run (marker for spent credit only)."""
    skip_or_fail_on_claude_block(run, subject)


def _decode_partial(output: bytes | str | None) -> str:
    """Decode partial output; subprocess.run hands it back as bytes on POSIX."""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


def _redacted_tail(text: str) -> str:
    """Redact before slicing, so a token cut at the boundary is still caught."""
    return repr(redact(text).text[-600:])


def _skip_or_fail_timeout(
    subject: str,
    exc: subprocess.TimeoutExpired,
    skip_on_block: Callable[[subprocess.CompletedProcess[str]], None],
) -> NoReturn:
    """Skip when the partial output names a block; otherwise fail the timeout.

    A spent quota or rate limit can keep the CLI retrying past its budget.
    The marker it printed before the kill is still a classified block. A
    timeout with no marker is a real hang and must stay red (issue #6181).
    """
    partial = subprocess.CompletedProcess(
        exc.cmd,
        -9,
        stdout=_decode_partial(exc.stdout),
        stderr=_decode_partial(exc.stderr),
    )
    skip_on_block(partial)
    raise AssertionError(
        f"{subject} exceeded {exc.timeout}s with no block marker. "
        f"stdout={_redacted_tail(partial.stdout)} stderr={_redacted_tail(partial.stderr)}"
    ) from exc


def _fail_on_zero_token_timeout(subject: str, exc: subprocess.TimeoutExpired) -> NoReturn:
    """Fail a zero-token check that timed out, whatever the partial output says.

    The zero-token checks (`plugin list` / `plugin details`) make no model call,
    so a quota or credit marker cannot explain a hang. They never skip (D26).
    """
    partial_out = _decode_partial(exc.stdout)
    partial_err = _decode_partial(exc.stderr)
    raise AssertionError(
        f"{subject} exceeded {exc.timeout}s; a zero-token check never skips on a block. "
        f"stdout={_redacted_tail(partial_out)} stderr={_redacted_tail(partial_err)}"
    ) from exc


def _skip_or_fail_copilot_timeout(subject: str, exc: subprocess.TimeoutExpired) -> NoReturn:
    _skip_or_fail_timeout(subject, exc, _skip_on_copilot_block)


def _skip_or_fail_claude_timeout(subject: str, exc: subprocess.TimeoutExpired) -> NoReturn:
    _skip_or_fail_timeout(subject, exc, lambda run: _skip_on_claude_block(run, subject))


def _claude_init_tools(agent: str) -> set[str]:
    try:
        run = _run_cli(
            [
                resolve_executable("claude"),
                "-p",
                "--agent",
                agent,
                "--setting-sources",
                "project",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--allowedTools",
                "Bash",
                "--permission-mode",
                "dontAsk",
                "--output-format",
                "stream-json",
                "--verbose",
                "Reply exactly READY.",
            ],
            cwd=REPO_ROOT,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        _skip_or_fail_claude_timeout(f"claude agent probe for {agent}", exc)
    if run.returncode != 0:
        _skip_on_claude_block(run, f"agent {agent!r}")
        raise AssertionError(
            f"claude agent probe failed for {agent} (rc={run.returncode}). "
            f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
        )
    init_events = [
        event
        for event in _json_events(run)
        if event.get("type") == "system" and event.get("subtype") == "init"
    ]
    assert len(init_events) == 1, f"expected one Claude init event, got {init_events!r}"
    tools = init_events[0].get("tools")
    assert isinstance(tools, list) and all(isinstance(tool, str) for tool in tools)
    return set(tools)


# Issue #5443: declaring `mcp__github__*` in an agent's `tools:` only filters
# tools a connected `github` MCP server provides. No Claude Code built-in
# supplies that server, so a bare install resolves none of them and the agent
# silently drops the names. The live probe below needs a server named exactly
# `github` (the `mcp__github__` prefix is derived from the server name).
_GITHUB_MCP_SERVER = "github"
_GITHUB_MCP_PROBE_TOOL = "mcp__github__get_file_contents"
_GITHUB_MCP_README_MARKER = "ai-agents"
_GITHUB_MCP_PROBE_PROMPT = (
    f"Call {_GITHUB_MCP_PROBE_TOOL} once with owner rjmurillo, repo ai-agents, "
    "path README.md. Do not use any other tool. Then reply with the single word DONE."
)


def _github_mcp_connected(init_event: dict[str, object]) -> bool:
    """True when the init event lists a connected MCP server named ``github``."""
    servers = init_event.get("mcp_servers")
    if not isinstance(servers, list):
        return False
    return any(
        isinstance(server, dict)
        and server.get("name") == _GITHUB_MCP_SERVER
        and server.get("status") == "connected"
        for server in servers
    )


def _content_blocks(event: dict[str, object]) -> list[dict[str, object]]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _tool_result_text(result: dict[str, object]) -> str:
    """Flatten a tool_result ``content`` field (string or text blocks) to text."""
    content = result.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(str(block.get("text", "")) for block in content if isinstance(block, dict))


def _claude_tool_call_outcome(events: list[dict[str, object]], tool: str) -> tuple[bool, bool, str]:
    """Return (called, errored, result_text) for the first call to ``tool``.

    ``called`` is False when the agent never issued the call. ``errored`` is
    True when the tool_result is flagged ``is_error`` or never arrived.
    """
    call_ids = [
        block.get("id")
        for event in events
        if event.get("type") == "assistant"
        for block in _content_blocks(event)
        if block.get("type") == "tool_use" and block.get("name") == tool
    ]
    if not call_ids:
        return False, False, ""
    for event in events:
        if event.get("type") != "user":
            continue
        for block in _content_blocks(event):
            if block.get("type") == "tool_result" and block.get("tool_use_id") == call_ids[0]:
                return True, bool(block.get("is_error")), _tool_result_text(block)
    return True, True, ""


def _copilot_project_agent_tools(events: list[dict[str, object]], agent: str) -> set[str]:
    """Extract declared tools for a project agent from Copilot CLI events.

    Primary path: look for a ``session.custom_agents_updated`` event that reports
    the agent with ``source: project``.

    Fallback path (issue #4964): Copilot CLI 1.0.78 on hosted runners with
    token-based auth (COPILOT_GITHUB_TOKEN) does not emit the enumeration event,
    even though ``--agent <name>`` succeeds (rc=0) and the agent file is present.
    When the event is absent, read the tool list from the canonical agent file at
    ``.github/agents/{agent}.agent.md``.  The exact-allowlist assertion and the
    executor-control negative control still hold because:
      - The CLI loaded the agent (rc=0 asserted by caller).
      - The file is the CLI's own source of truth for declared tools.
      - Runtime enforcement is separately verified by the shell-unavailability
        and implementer-shell assertions in the calling test.
    """
    for event in events:
        if event.get("type") != "session.custom_agents_updated":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        agents_list = data.get("agents")
        if not isinstance(agents_list, list):
            continue
        for record in agents_list:
            if not isinstance(record, dict):
                continue
            if record.get("id") != agent or record.get("source") != "project":
                continue
            tools = record.get("tools")
            assert isinstance(tools, list) and all(isinstance(tool, str) for tool in tools)
            return set(tools)

    # Fallback: event not emitted (issue #4964 hosted-runner contract).
    event_types = sorted(str(e.get("type", "<no type>")) for e in events)
    warnings.warn(
        f"session.custom_agents_updated not found for {agent!r}; "
        f"falling back to agent file. Events received: {event_types}",
        stacklevel=2,
    )
    return _read_agent_tools_from_file(agent)


_GITHUB_AGENTS_DIR = REPO_ROOT / ".github" / "agents"


def _read_agent_tools_from_file(agent: str) -> set[str]:
    """Read the declared tools from the project agent's frontmatter.

    Canonical source: ``.github/agents/{agent}.agent.md`` YAML front matter,
    ``tools`` key.  Fails hard if the file is missing or malformed.
    """
    agent_file = _GITHUB_AGENTS_DIR / f"{agent}.agent.md"
    assert agent_file.is_file(), (
        f"Agent file not found: {agent_file}. Cannot verify tools for project agent {agent!r}."
    )
    content = agent_file.read_text(encoding="utf-8")
    # Parse YAML front matter between --- delimiters.
    parts = content.split("---", 2)
    assert len(parts) >= 3, f"Agent file {agent_file} has no valid YAML front matter."
    frontmatter = yaml.safe_load(parts[1])
    assert isinstance(frontmatter, dict), f"Agent frontmatter is not a mapping: {agent_file}"
    tools = frontmatter.get("tools")
    assert isinstance(tools, list) and all(isinstance(t, str) for t in tools), (
        f"Agent {agent!r} frontmatter 'tools' must be a list of strings: {tools!r}"
    )
    return set(tools)


def _run_copilot_agent(agent: str, prompt: str) -> list[dict[str, object]]:
    try:
        run = _run_cli(
            copilot_command(
                "--agent",
                agent,
                "--no-ask-user",
                "--allow-all-tools",
                "--output-format",
                "json",
                "--prompt",
                prompt,
            ),
            cwd=REPO_ROOT,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        _skip_or_fail_copilot_timeout(f"copilot agent probe for {agent}", exc)
    _skip_on_copilot_block(run)
    assert run.returncode == 0, (
        f"copilot agent probe failed for {agent} (rc={run.returncode}). "
        f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    )
    return _json_events(run)


def _copilot_tool_names(events: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    for event in events:
        if event.get("type") != "tool.execution_start":
            continue
        data = event.get("data")
        if isinstance(data, dict) and isinstance(data.get("toolName"), str):
            names.append(data["toolName"])
    return names


def _copilot_assistant_text(events: list[dict[str, object]]) -> str:
    messages: list[str] = []
    for event in events:
        if event.get("type") != "assistant.message":
            continue
        data = event.get("data")
        if isinstance(data, dict) and isinstance(data.get("content"), str):
            messages.append(data["content"])
    return "\n".join(messages)


def _copilot_tool_result_text(events: list[dict[str, object]]) -> str:
    results: list[str] = []
    for event in events:
        if event.get("type") != "tool.execution_complete":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("content"), str):
            results.append(result["content"])
    return "\n".join(results)


def _is_from_plugin_dir(record: dict[str, object], plugin_dir: Path | None) -> bool:
    """Return whether a plugin record belongs to the requested plugin tree."""
    if plugin_dir is None:
        return True
    path = record.get("path")
    if not isinstance(path, str):
        return False
    try:
        return Path(path).resolve().is_relative_to(plugin_dir.resolve())
    except OSError:
        return False


def _plugin_skill_names(
    payload: object,
    plugin_dir: Path | None = None,
) -> set[str]:
    """Extract skill names loaded from a plugin source out of `skill list --json`.

    The Copilot CLI prints a JSON array of skill records. Each record carries a
    ``name`` and a ``source``; only ``source == "plugin"`` records prove the
    skill loaded from the plugin dir under test rather than from a built-in or a
    user-level install. A record without a recognized source is ignored, not
    counted, so a built-in ``build`` cannot mask a missing plugin ``build``.
    """
    if not isinstance(payload, list):
        return set()
    names: set[str] = set()
    for record in payload:
        if not isinstance(record, dict):
            continue
        if record.get("source") != "plugin" or not _is_from_plugin_dir(record, plugin_dir):
            continue
        name = record.get("name")
        if isinstance(name, str):
            names.add(name)
    return names


def _has_plugin_source_record(
    payload: object,
    plugin_dir: Path | None = None,
) -> bool:
    """True if `payload` is a list with a `source: plugin` record for `plugin_dir`.

    Unlike `_plugin_skill_names`, this ignores the ``name`` field: a plugin
    record with a missing or non-string name still proves the enumeration
    surface carried plugin loads. The strict ``name`` filter is applied later by
    `_plugin_skill_names`, so a nameless plugin record makes the secondary check
    fail loud on the missing skill rather than skip. Scoping by ``plugin_dir``
    drops globally installed plugins (which surface with ``pluginName: null`` on
    1.0.72), so the secondary check never trips on unrelated installs.
    """
    if not isinstance(payload, list):
        return False
    return any(
        isinstance(record, dict)
        and record.get("source") == "plugin"
        and _is_from_plugin_dir(record, plugin_dir)
        for record in payload
    )


def _read_manifest_name(manifest_path: Path) -> str:
    """The plugin's declared name, used to address `plugin details`.

    The smoke used to key its load assertion on the manifest ``version``.
    ADR-092 deleted that field so Claude Code resolves freshness from the commit
    SHA, which means `plugin details` reports a SHA the manifest cannot predict.
    ``name`` replaces it as the ARGUMENT, not as the proof: `plugin details
    <name>` echoes the string it was handed, so finding it in the output cannot
    distinguish a parsed manifest from a hollow one. The load signal in this
    smoke is the ``EXPECTED_SKILLS`` assertion below, which can only pass if the
    CLI walked the shipped plugin tree.
    """
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"manifest {manifest_path} has no string name: {data!r}")
    return name


def _parse_component_inventory(text: str, label: str) -> set[str]:
    """Names from one `plugin details` component-inventory row.

    The row reads ``  Agents (31)  analyst, architect, ...`` on a single line.
    Returns an empty set when the label is absent, so a caller that expects a
    populated inventory fails on a missing row rather than passing vacuously.
    """
    # [ \t] rather than \s: \s spans newlines, so a zero-count row such as
    # "LSP servers (0)" would swallow the line break and return the NEXT row's
    # names under this label.
    pattern = re.compile(rf"^[ \t]*{re.escape(label)}[ \t]*\(\d+\)[ \t]*(.*)$", re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        return set()
    return {name.strip() for name in match.group(1).split(",") if name.strip()}


@pytest.mark.smoke
@requires_claude
@_cli_budget(_CLI_TIMEOUT_SECONDS)
def test_claude_agent_inventory_excludes_the_non_agent_documents(tmp_path: Path) -> None:
    """The loader's own agent listing carries none of the #5493 documents.

    This is the loader-level proof that the file-level gate
    (``scripts/validation/check_agent_tree_frontmatter.py``) cannot give: it asks
    the real CLI what it registered, rather than asking the repository's own
    predicate what it would have registered.

    Measured while writing this test, on the same machine and CLI build:
    ``origin/main`` reported ``Agents (33)`` including ``AGENTS`` and ``CLAUDE``;
    this branch reports ``Agents (31)`` with neither. The three documents that
    lived under ``agents/security/references/`` did not appear in either listing,
    so the loader registered two of the five, not five.

    Positive control: ``security`` must be present. Without it a CLI that stopped
    emitting the inventory row, or emitted an empty one, would satisfy the
    absence assertion for the wrong reason.
    """
    try:
        details = _run_cli(
            [
                resolve_executable("claude"),
                "--plugin-dir",
                str(_CLAUDE_PLUGIN_DIR),
                "plugin",
                "details",
                "project-toolkit",
            ],
            cwd=tmp_path,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        _fail_on_zero_token_timeout("claude plugin details", exc)

    assert details.returncode == 0, (
        f"claude plugin details failed (rc={details.returncode}). "
        f"stdout={details.stdout[-600:]!r} stderr={details.stderr[-600:]!r}"
    )

    combined = details.stdout + details.stderr
    agents = _parse_component_inventory(combined, "Agents")

    assert "security" in agents, (
        "claude reported no agent inventory containing a known agent, so the "
        f"absence check below would pass vacuously. parsed={sorted(agents)}. "
        f"stdout={details.stdout[-600:]!r}"
    )

    registered_non_agents = agents & NON_AGENT_DOCUMENT_STEMS
    assert not registered_non_agents, (
        "claude registered non-agent documents as dispatchable agents: "
        f"{sorted(registered_non_agents)} (issue #5493)."
    )


def test_parse_component_inventory_reads_a_populated_row() -> None:
    text = "Component inventory\n  Skills (2)  a, b\n  Agents (3)  analyst, critic, security\n"

    assert _parse_component_inventory(text, "Agents") == {"analyst", "critic", "security"}


def test_parse_component_inventory_returns_empty_for_a_missing_label() -> None:
    text = "Component inventory\n  Skills (2)  a, b\n"

    assert _parse_component_inventory(text, "Agents") == set()


def test_parse_component_inventory_does_not_match_a_label_prefix() -> None:
    """`Agents` must not be read off an `MCP servers` or `LSP servers` row."""
    text = "  LSP servers (0)  \n  Agents (1)  analyst\n"

    assert _parse_component_inventory(text, "LSP servers") == set()
    assert _parse_component_inventory(text, "Agents") == {"analyst"}


def test_non_agent_document_stems_are_absent_from_the_agent_tree() -> None:
    """The always-on half: no file under the agent tree carries those stems.

    Pins the same contract as the opt-in CLI test above without a CLI, so a
    machine with no `claude` on PATH still fails when a stub returns.
    """
    tree = REPO_ROOT / ".claude" / "agents"
    stems = {path.stem for path in tree.rglob("*.md")}

    assert not (stems & NON_AGENT_DOCUMENT_STEMS), (
        f"non-agent documents are back under {tree}: "
        f"{sorted(stems & NON_AGENT_DOCUMENT_STEMS)} (issue #5493)."
    )


@pytest.mark.smoke
@requires_copilot
@_cli_budget(_SKILL_LIST_TIMEOUT_SECONDS)
def test_copilot_plugin_loads_expected_skills(tmp_path: Path) -> None:
    """The shipped plugin loads every expected skill, proven with no model call.

    REQ-047 owner decision D25: this is the Copilot leg's gate, so it spends no
    quota and never skips on a quota or auth block. ``copilot --plugin-dir
    <repo>/src/copilot-cli skill list --json`` runs from a neutral cwd under an
    isolated ``COPILOT_HOME`` (so user-installed plugins and stored auth cannot
    mask a missing skill). It must exit 0, emit no ``argument-hint`` loader
    warning (issue #2736), and list every ``EXPECTED_SKILLS`` name from a
    ``source: plugin`` record whose ``path`` is under ``src/copilot-cli``.

    The prompt-based hook probe is the best-effort
    ``test_copilot_plugin_dir_fires_probe_hook``.
    """
    neutral_cwd = tmp_path / "neutral-cwd"
    neutral_cwd.mkdir()
    env = _clean_env()
    env["COPILOT_HOME"] = str(tmp_path / "copilot-home")
    try:
        run = subprocess.run(
            copilot_command("--plugin-dir", str(_COPILOT_PLUGIN_DIR), "skill", "list", "--json"),
            cwd=neutral_cwd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_SKILL_LIST_TIMEOUT_SECONDS,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"copilot skill list exceeded {exc.timeout}s; it makes no model call, so this "
            "is a hang, not a quota block."
        )

    assert run.returncode == 0, (
        f"copilot skill list failed (rc={run.returncode}). "
        f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    )
    assert _ARGUMENT_HINT_WARNING not in run.stderr.lower(), (
        "copilot reported an argument-hint loader warning (issue #2736 failure class). "
        f"stderr={run.stderr[-600:]!r}"
    )

    try:
        payload = json.loads(run.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"copilot skill list emitted non-JSON: {exc}. stdout={run.stdout[-600:]!r}")
    assert isinstance(payload, list), (
        "copilot skill list --json did not return a JSON array "
        f"(got {type(payload).__name__}); the enumeration schema changed. "
        f"stdout={run.stdout[-600:]!r}"
    )

    loaded = _plugin_skill_names(payload, _COPILOT_PLUGIN_DIR)
    missing = EXPECTED_SKILLS - loaded
    assert not missing, (
        "copilot did not list expected skills from the shipped plugin under "
        f"{_COPILOT_PLUGIN_DIR}: missing={sorted(missing)} loaded={sorted(loaded)}"
    )


@pytest.mark.smoke
@requires_copilot
@_cli_budget(_CLI_TIMEOUT_SECONDS)
def test_copilot_plugin_dir_fires_probe_hook(tmp_path: Path) -> None:
    """Best-effort: ``copilot --plugin-dir <probe> -p`` fires the probe hook.

    A fired hook proves the CLI loads and dispatches a ``--plugin-dir`` plugin
    (issue #3148). The prompt spends Copilot quota, so a spent quota skips with
    ``QUOTA_SKIP:`` (D26); auth, rate limit, and transport blocks fail in CI. The
    required load proof is ``test_copilot_plugin_loads_expected_skills``.
    """
    probe_plugin = tmp_path / "probe-plugin"
    marker = tmp_path / "probe_marker.txt"
    userland = tmp_path / "userland"
    userland.mkdir()
    write_marker_probe_plugin(probe_plugin, marker)
    try:
        fired = run_copilot_plugin_dir(probe_plugin, cwd=userland, timeout=_CLI_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        _skip_or_fail_copilot_timeout("copilot --plugin-dir probe", exc)
    _skip_on_copilot_block(fired)
    assert fired.returncode == 0, (
        f"copilot --plugin-dir probe run failed (rc={fired.returncode}). "
        f"stdout={fired.stdout[-600:]!r} stderr={fired.stderr[-600:]!r}"
    )
    assert marker.is_file(), (
        "copilot --plugin-dir did not fire the probe plugin's UserPromptSubmit hook: the CLI "
        "failed to load and dispatch the --plugin-dir plugin. This is a real plugin-load "
        f"failure, not an enumeration quirk. stdout={fired.stdout[-600:]!r} "
        f"stderr={fired.stderr[-600:]!r}"
    )


@pytest.mark.smoke
@requires_copilot
@_cli_budget(_CLI_TIMEOUT_SECONDS)
def test_copilot_empty_plugin_dir_does_not_fire_probe_hook(tmp_path: Path) -> None:
    """Negative control: the fired-hook load signal fails when nothing loads.

    A marker-writing probe hook exists on disk, but copilot is pointed at a
    DIFFERENT, empty plugin dir. The probe hook must NOT fire, so its marker
    stays absent. This proves the fired-hook assertion in
    ``test_copilot_plugin_dir_fires_probe_hook`` fails loud when the plugin does
    not load, rather than passing unconditionally (generated-artifacts.md: a push
    gate must keep a loud-fail negative control). Verified against Copilot CLI
    1.0.72-0: an empty ``--plugin-dir`` leaves the marker absent.
    """
    probe_plugin = tmp_path / "probe-plugin"
    marker = tmp_path / "probe_marker.txt"
    write_marker_probe_plugin(probe_plugin, marker)

    empty_plugin = tmp_path / "empty-plugin"
    empty_plugin.mkdir()
    (empty_plugin / "plugin.json").write_text(
        json.dumps(
            {
                "name": "load-smoke-neg-control",
                "description": "negative control",
                "version": "0.0.1",
                "author": {"name": "e2e"},
            }
        ),
        encoding="utf-8",
    )
    userland = tmp_path / "userland"
    userland.mkdir()
    try:
        run = run_copilot_plugin_dir(empty_plugin, cwd=userland, timeout=_CLI_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        _skip_or_fail_copilot_timeout("copilot --plugin-dir empty", exc)
    _skip_on_copilot_block(run)
    assert not marker.is_file(), (
        "negative control failed: copilot fired the probe hook while pointed at an EMPTY "
        "--plugin-dir, so a fired marker cannot distinguish load from no-load and the smoke's "
        f"primary assertion would pass unconditionally. stdout={run.stdout[-600:]!r} "
        f"stderr={run.stderr[-600:]!r}"
    )


@pytest.mark.smoke
@requires_claude
@_cli_budget(_VERSION_TIMEOUT_SECONDS, _CLI_TIMEOUT_SECONDS, _CLI_TIMEOUT_SECONDS)
def test_claude_plugin_loads_expected_skills(tmp_path: Path) -> None:
    """claude --plugin-dir loads project-toolkit at the manifest version.

    Asserts returncode 0 on ``plugin list`` and that the version from
    ``src/claude/.claude-plugin/plugin.json`` appears in ``plugin details``,
    proving the CLI loaded the shipped plugin rather than failing silently.
    """
    version = _run_cli(
        [resolve_executable("claude"), "--version"],
        timeout=_VERSION_TIMEOUT_SECONDS,
    )
    print(f"claude --version: {version.stdout.strip() or version.stderr.strip()}")

    manifest_name = _read_manifest_name(_CLAUDE_MANIFEST)

    try:
        listing = _run_cli(
            [
                resolve_executable("claude"),
                "--plugin-dir",
                str(_CLAUDE_PLUGIN_DIR),
                "plugin",
                "list",
            ],
            cwd=tmp_path,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        _fail_on_zero_token_timeout("claude plugin list", exc)

    assert listing.returncode == 0, (
        f"claude plugin list failed (rc={listing.returncode}). "
        f"stdout={listing.stdout[-600:]!r} stderr={listing.stderr[-600:]!r}"
    )

    try:
        details = _run_cli(
            [
                resolve_executable("claude"),
                "--plugin-dir",
                str(_CLAUDE_PLUGIN_DIR),
                "plugin",
                "details",
                "project-toolkit",
            ],
            cwd=tmp_path,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        _fail_on_zero_token_timeout("claude plugin details", exc)

    assert details.returncode == 0, (
        f"claude plugin details failed (rc={details.returncode}). "
        f"stdout={details.stdout[-600:]!r} stderr={details.stderr[-600:]!r}"
    )
    combined = details.stdout + details.stderr
    # Weak by construction: `plugin details <name>` echoes its own argument.
    # Kept as a cheap sanity check that the command addressed the right plugin.
    # The real load signal is the skills assertion below.
    assert manifest_name in combined, (
        f"claude did not report manifest name {manifest_name!r}. "
        f"stdout={details.stdout[-600:]!r} stderr={details.stderr[-600:]!r}"
    )
    missing = {name for name in EXPECTED_SKILLS if name not in combined}
    assert not missing, (
        f"claude did not report expected plugin skills: missing={sorted(missing)}. "
        f"stdout={details.stdout[-600:]!r} stderr={details.stderr[-600:]!r}"
    )


@pytest.mark.smoke
@requires_claude
@_cli_budget(_CLI_TIMEOUT_SECONDS, _CLI_TIMEOUT_SECONDS)
def test_claude_analyst_runtime_uses_exact_allowlist_with_executor_control() -> None:
    """Claude loads only reviewed analyst tools while implementer exposes writes."""
    analyst_tools = _claude_init_tools("analyst")
    implementer_tools = _claude_init_tools("implementer")

    assert {"Glob", "Grep", "Read"} <= analyst_tools
    assert not analyst_tools - _CLAUDE_ANALYST_TOOLS, (
        f"Claude exposed unreviewed analyst tools: {sorted(analyst_tools - _CLAUDE_ANALYST_TOOLS)}"
    )
    assert {"Bash", "Edit", "Write"} <= implementer_tools, (
        "negative control failed: Claude did not report execution and write tools "
        "for implementer, so the analyst allowlist cannot prove inheritance is restricted"
    )


@pytest.mark.smoke
@requires_claude
@_cli_budget(_CLI_TIMEOUT_SECONDS, _CLI_TIMEOUT_SECONDS)
def test_claude_security_runtime_grants_no_shell_with_executor_control() -> None:
    """Claude resolves the security agent to the reviewed read-and-report set.

    PR #5356's review found the contract tests only parsed frontmatter and
    searched prose, so nothing observed what the harness actually hands the
    agent. This probes the live loader. The implementer probe is the defective
    tool path control: it proves this probe CAN see `Bash` and `Edit` when an
    agent declares them, so their absence from the security set is a real
    boundary and not a probe that reports nothing.
    """
    security_tools = _claude_init_tools("security")
    implementer_tools = _claude_init_tools("implementer")

    assert {"Glob", "Grep", "Read", "Write"} <= security_tools
    assert not security_tools - _CLAUDE_SECURITY_TOOLS, (
        f"Claude exposed unreviewed security tools: "
        f"{sorted(security_tools - _CLAUDE_SECURITY_TOOLS)}"
    )
    assert not security_tools & _CLAUDE_SECURITY_FORBIDDEN_TOOLS, (
        f"Claude granted the security agent "
        f"{sorted(security_tools & _CLAUDE_SECURITY_FORBIDDEN_TOOLS)}. A shell "
        f"reopens `git commit`, `git push`, and `git -c Diff.External=<cmd>`, "
        f"which the case-sensitive deny rules do not catch (issue #4781)."
    )
    assert {"Bash", "Edit", "Write"} <= implementer_tools, (
        "negative control failed: Claude did not report execution and write tools "
        "for implementer, so the security allowlist cannot prove the grant was read"
    )


@pytest.mark.claude
@requires_claude
@_cli_budget(_CLI_TIMEOUT_SECONDS)
def test_claude_analyst_makes_a_live_github_mcp_read() -> None:
    """The analyst's `mcp__github__*` grant reaches a real connector (issue #5443).

    The tool-name probes above run with an empty MCP config, so they prove which
    names the loader permits, not that a `github` server backs them. This run
    keeps the machine's own MCP configuration, issues a real
    `mcp__github__get_file_contents` read through the analyst agent, and asserts
    a non-error result with content. It skips, naming the prerequisite, when no
    connected server called `github` exists: see "GitHub MCP prerequisite" in
    docs/installation.md. It is not a `smoke` test because the CI runners
    provision no such server.
    """
    try:
        run = _run_cli(
            [
                resolve_executable("claude"),
                "-p",
                "--agent",
                "analyst",
                "--allowedTools",
                _GITHUB_MCP_PROBE_TOOL,
                "--permission-mode",
                "dontAsk",
                "--output-format",
                "stream-json",
                "--verbose",
                _GITHUB_MCP_PROBE_PROMPT,
            ],
            cwd=REPO_ROOT,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        _skip_or_fail_claude_timeout("claude live github MCP probe", exc)
    if run.returncode != 0:
        _skip_on_claude_block(run, "live github MCP probe")
        raise AssertionError(
            f"claude live github MCP probe failed (rc={run.returncode}). "
            f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
        )
    events = _json_events(run)
    init_events = [
        event
        for event in events
        if event.get("type") == "system" and event.get("subtype") == "init"
    ]
    assert len(init_events) == 1, f"expected one Claude init event, got {init_events!r}"
    if not _github_mcp_connected(init_events[0]):
        pytest.skip(
            "no connected MCP server named 'github'; see 'GitHub MCP prerequisite' "
            "in docs/installation.md"
        )

    called, errored, text = _claude_tool_call_outcome(events, _GITHUB_MCP_PROBE_TOOL)

    assert called, f"analyst never called {_GITHUB_MCP_PROBE_TOOL} though the server is connected"
    assert not errored, f"{_GITHUB_MCP_PROBE_TOOL} returned an error: {_redacted_tail(text)}"
    assert _GITHUB_MCP_README_MARKER in text.lower(), (
        f"{_GITHUB_MCP_PROBE_TOOL} result does not look like README.md: {_redacted_tail(text)}"
    )


@pytest.mark.smoke
@requires_copilot
@_cli_budget(_CLI_TIMEOUT_SECONDS, _CLI_TIMEOUT_SECONDS)
def test_copilot_security_runtime_has_no_shell_with_executor_control() -> None:
    """Copilot's security agent cannot execute a command, and says so.

    The exact-allowlist half is covered by the manifest; this half observes the
    runtime refusing an execution request. The implementer probe is the control:
    the same prompt against an agent that does hold a shell must run.
    """
    security_events = _run_copilot_agent(
        "security",
        (
            "Use the shell tool to execute exactly: printf COPILOT_SHELL_CONTROL. "
            "Do not use a substitute. If unavailable reply exactly SHELL_UNAVAILABLE."
        ),
    )
    implementer_events = _run_copilot_agent(
        "implementer",
        (
            "Use the shell tool to execute exactly: printf COPILOT_SHELL_CONTROL. "
            "Do not use a substitute. Then reply exactly READY."
        ),
    )

    assert not {"bash", "shell", "execute"} & set(_copilot_tool_names(security_events))
    assert "SHELL_UNAVAILABLE" in _copilot_assistant_text(security_events)
    assert "bash" in _copilot_tool_names(implementer_events), (
        "negative control failed: implementer did not execute the shell command, "
        "so the security refusal proves nothing about the security agent"
    )
    assert "COPILOT_SHELL_CONTROL" in _copilot_tool_result_text(implementer_events)


@pytest.mark.smoke
@requires_copilot
@_cli_budget(_CLI_TIMEOUT_SECONDS, _CLI_TIMEOUT_SECONDS)
def test_copilot_analyst_runtime_uses_exact_allowlist_with_executor_control() -> None:
    """Copilot resolves only reviewed analyst tools, with an execution control."""
    analyst_shell_events = _run_copilot_agent(
        "analyst",
        (
            "Use the shell tool to execute exactly: printf COPILOT_SHELL_CONTROL. "
            "Do not use a substitute. If unavailable reply exactly SHELL_UNAVAILABLE."
        ),
    )
    implementer_events = _run_copilot_agent(
        "implementer",
        (
            "Use the shell tool to execute exactly: printf COPILOT_SHELL_CONTROL. "
            "Do not use a substitute. Then reply exactly READY."
        ),
    )
    analyst_tools = {
        tool.casefold() for tool in _copilot_project_agent_tools(analyst_shell_events, "analyst")
    }
    implementer_tools = {
        tool.casefold() for tool in _copilot_project_agent_tools(implementer_events, "implementer")
    }

    assert analyst_tools == _COPILOT_ANALYST_TOOLS
    assert {"edit", "shell"} <= implementer_tools, (
        "negative control failed: Copilot did not report execution and write tools "
        "for implementer, so the analyst allowlist cannot prove its manifest was loaded"
    )
    assert not {"bash", "shell", "execute"} & set(_copilot_tool_names(analyst_shell_events))
    assert "SHELL_UNAVAILABLE" in _copilot_assistant_text(analyst_shell_events)
    # GitHub read tools are declared in the manifest (verified by analyst_tools
    # exact-match above and by test_copilot_analyst_manifest_declares_github_tools).
    # No GitHub MCP server runs in this test environment, so runtime tool calls
    # are not possible.  Manifest declaration is the contract boundary; runtime
    # connectivity is validated by integration tests with a live MCP server.
    assert "bash" in _copilot_tool_names(implementer_events), (
        "negative control failed: implementer did not execute the shell command"
    )
    assert "COPILOT_SHELL_CONTROL" in _copilot_tool_result_text(implementer_events)


# Manifest-resolved `model:` runtime contract (issue #5333, ADR-080 rule 5,
# generated-artifacts.md MUST 2). The generator test proves it WROTE a model id;
# only the real CLI proves the id RESOLVES. Copilot CLI does not fail a run on an
# unresolvable agent model: it prints a warning on stderr, falls back to "auto",
# and exits 0 (Copilot CLI 1.0.96, probed with a bogus id). The reply therefore
# says nothing about the pin; the warning is the only signal.
_COPILOT_TIER_CONFIG = REPO_ROOT / "templates" / "platforms" / "copilot-cli.yaml"
_MODEL_REJECTED_RE = re.compile(
    r'specifies model "(?P<model>[^"]*)" which is not available', re.IGNORECASE
)
# Same shape as a manifest id, but no such model exists, so the CLI must reject it.
_BOGUS_MODEL_ID = "claude-bogus-99.99"
_MODEL_PROBE_AGENT = "model-probe"
_MODEL_PROBE_PROMPT = "Reply exactly READY."


def _copilot_tier_model(tier: str) -> str:
    """The id the generator emits for ``tier`` on Copilot CLI, from the platform YAML."""
    config = yaml.safe_load(_COPILOT_TIER_CONFIG.read_text(encoding="utf-8"))
    return str(config["legacy"]["model_tiers"][tier])


_NO_MINOR_CANONICAL_ID = "claude-opus-5"


def _copilot_no_minor_model() -> str:
    """The id the generator emits on Copilot CLI for a manifest pin with no minor.

    ``claude-opus-5`` is a live id (``build/model_pin_manifest.py`` and
    ``scripts/eval/panels/owner-copilot-cli.json``), and the second of the two
    shapes ``format_model_id_for_platform`` can emit: ``claude-{tier}-{major}``.
    """
    tiers = {t: _copilot_tier_model(t) for t in ("opus", "sonnet", "haiku")}
    emitted = _load_format_model_id_for_platform()(_NO_MINOR_CANONICAL_ID, tiers)
    assert emitted is not None, f"generator emits no pin for {_NO_MINOR_CANONICAL_ID!r}"
    return emitted


def _rejected_models(*streams: str) -> list[str]:
    """Model ids the CLI reported as unavailable, in the order printed."""
    return [match.group("model") for text in streams for match in _MODEL_REJECTED_RE.finditer(text)]


def _write_model_probe_plugin(plugin_dir: Path, model: str) -> str:
    """Write a one-agent ``--plugin-dir`` plugin pinned to ``model``.

    Returns the ``--agent`` reference. Copilot namespaces plugin agents as
    ``<plugin>:<agent>``. The plugin is isolated, so the real
    ``.github/agents/`` and ``src/copilot-cli/agents/`` trees are untouched.
    """
    name = probe_name()
    (plugin_dir / "agents").mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(manifest(name), encoding="utf-8")
    (plugin_dir / "agents" / f"{_MODEL_PROBE_AGENT}.agent.md").write_text(
        f"---\nname: {_MODEL_PROBE_AGENT}\ndescription: model id runtime probe\n"
        f"model: {model}\n---\n{_MODEL_PROBE_PROMPT}\n",
        encoding="utf-8",
    )
    return f"{name}:{_MODEL_PROBE_AGENT}"


def _run_copilot_model_probe(tmp_path: Path, model: str) -> subprocess.CompletedProcess[str]:
    """Run the probe agent pinned to ``model`` from a neutral cwd."""
    root = tmp_path / re.sub(r"[^a-z0-9]+", "-", model.lower())
    cwd = root / "cwd"
    cwd.mkdir(parents=True)
    agent = _write_model_probe_plugin(root / "plugin", model)
    try:
        run = _run_cli(
            copilot_command(
                "--plugin-dir",
                str(root / "plugin"),
                "--agent",
                agent,
                "--no-ask-user",
                "--allow-all-tools",
                "--output-format",
                "json",
                "--prompt",
                _MODEL_PROBE_PROMPT,
            ),
            cwd=cwd,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        _skip_or_fail_copilot_timeout(f"copilot model probe for {model}", exc)
    _skip_on_copilot_block(run)
    assert run.returncode == 0, (
        f"copilot model probe failed for {model} (rc={run.returncode}). "
        f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    )
    return run


@pytest.mark.smoke
@requires_copilot
@_cli_budget(_CLI_TIMEOUT_SECONDS, _CLI_TIMEOUT_SECONDS, _CLI_TIMEOUT_SECONDS)
def test_copilot_accepts_the_generated_model_id_with_rejection_control(tmp_path: Path) -> None:
    """Copilot resolves both id shapes the generator emits, and flags one it cannot.

    The control runs first: a bogus id in the same harness must print the
    rejection warning, or the warning checks below prove nothing. The subjects
    are the two shapes ``format_model_id_for_platform`` writes into generated
    frontmatter: the opus-tier dot form from ``templates/platforms/copilot-cli.yaml``
    (``claude-{tier}-{major}.{minor}``) and the no-minor form for a manifest pin
    such as ``claude-opus-5`` (``claude-{tier}-{major}``).
    """
    subjects = {
        "major.minor": _copilot_tier_model("opus"),
        "major only": _copilot_no_minor_model(),
    }
    control_run = _run_copilot_model_probe(tmp_path, _BOGUS_MODEL_ID)
    assert _BOGUS_MODEL_ID in _rejected_models(control_run.stderr, control_run.stdout), (
        "negative control failed: Copilot printed no rejection for "
        f"{_BOGUS_MODEL_ID!r}, so a clean run for any subject proves nothing. "
        f"stderr={control_run.stderr[-600:]!r}"
    )
    for shape, subject in subjects.items():
        subject_run = _run_copilot_model_probe(tmp_path, subject)
        assert subject not in _rejected_models(subject_run.stderr, subject_run.stdout), (
            f"Copilot CLI cannot use the {shape} model {subject!r} and fell back to auto. "
            "The id is unknown to this CLI version or not enabled for the smoke account. "
            f"stderr={subject_run.stderr[-600:]!r}"
        )
        assert "READY" in _copilot_assistant_text(_json_events(subject_run))


# Always-on unit checks. They need no real CLI, so they run in bare CI and pin
# the load contract the gated smoke depends on: every expected lifecycle skill
# ships in BOTH plugin trees, and the fired-hook detector has a working positive
# and negative control. A break here means the gated smoke is asserting a skill
# set that cannot load, or a load signal that cannot fail.


def test_security_agent_file_declares_the_probed_allowlist() -> None:
    """The gated smoke must not assert a tool set the agent file cannot produce.

    Same role as the skill-set pins below: this runs without a CLI, so a grant
    edited on disk fails here in bare CI rather than silently making the gated
    probe assert a set nothing will ever load.
    """
    frontmatter = yaml.safe_load(
        _SECURITY_AGENT_FILE.read_text(encoding="utf-8").split("---", 2)[1]
    )
    declared = set(frontmatter["tools"])

    assert declared == set(_CLAUDE_SECURITY_TOOLS), (
        f"{_SECURITY_AGENT_FILE.relative_to(REPO_ROOT)} declares {sorted(declared)}, "
        f"but the runtime probe asserts {sorted(_CLAUDE_SECURITY_TOOLS)}. Update both."
    )
    assert not declared & set(_CLAUDE_SECURITY_FORBIDDEN_TOOLS), (
        f"{_SECURITY_AGENT_FILE.relative_to(REPO_ROOT)} declares "
        f"{sorted(declared & set(_CLAUDE_SECURITY_FORBIDDEN_TOOLS))}; the security "
        f"agent gets no shell and no editor (issue #4781)"
    )


def test_expected_skills_ship_in_copilot_plugin_tree() -> None:
    """Each EXPECTED_SKILLS entry has a skill dir in the Copilot plugin tree.

    If a lifecycle skill is renamed or removed from src/copilot-cli/skills, the
    gated Copilot smoke would assert a name that can never load. Pin the set to
    the on-disk tree so that drift fails in bare CI, not only in plugin-cli-smoke.yml.
    """
    skills_dir = _COPILOT_PLUGIN_DIR / "skills"
    missing = {name for name in EXPECTED_SKILLS if not (skills_dir / name).is_dir()}
    assert not missing, f"expected skills missing from {skills_dir}: {sorted(missing)}"


def test_expected_skills_ship_in_claude_tree() -> None:
    """Each EXPECTED_SKILLS entry ships in the Claude tree as command or skill.

    The Claude plugin surfaces a lifecycle capability either as a slash command
    under commands/<name>.md or as a skill under skills/<name>/, resolved from
    the marketplace-listed plugin root (src/claude/, ADR-109 B6). Most
    lifecycle names ship as commands; `review` ships as a skill dir. Accept
    either so the contract tracks how the plugin actually exposes the capability,
    and so a rename in both places fails in bare CI before the plugin-cli-smoke.yml Claude
    smoke ever runs.
    """
    commands_dir = _CLAUDE_PLUGIN_DIR / "commands"
    skills_dir = _CLAUDE_PLUGIN_DIR / "skills"
    missing = {
        name
        for name in EXPECTED_SKILLS
        if not (commands_dir / f"{name}.md").is_file() and not (skills_dir / name).is_dir()
    }
    assert not missing, (
        f"expected skills missing from {commands_dir} and {skills_dir}: {sorted(missing)}"
    )


def test_claude_manifest_exposes_string_name_and_no_version() -> None:
    """The Claude manifest carries a non-empty string name and no version.

    The gated Claude smoke asserts this name appears in `plugin details`. If the
    manifest loses its name or makes it non-string, the smoke assertion becomes
    meaningless; pin the precondition here so it fails in bare CI.

    The version half is the ADR-092 invariant: a version field would pin Claude
    Code freshness to that string instead of the commit SHA. The dedicated gate
    is build/scripts/validate_plugin_version_bump.py; this asserts the smoke's
    own precondition so the load signal cannot silently go back to a version.
    """
    assert _read_manifest_name(_CLAUDE_MANIFEST)
    data = json.loads(_CLAUDE_MANIFEST.read_text(encoding="utf-8"))
    assert "version" not in data, (
        f"{_CLAUDE_MANIFEST} carries a version field; ADR-092 requires its absence "
        "so Claude Code resolves freshness from the commit SHA"
    )


def test_plugin_skill_names_counts_only_plugin_source() -> None:
    """Only `source: plugin` records count toward the loaded set.

    A built-in or user-level skill with the same name must not mask a missing
    plugin skill. This pins the filter the secondary Copilot assertion relies on.
    """
    payload = [
        {"name": "build", "source": "plugin"},
        {"name": "review", "source": "builtin"},
        {"name": "plan", "source": "plugin"},
        {"name": "noname-source-plugin"},
        "not-a-record",
    ]

    names = _plugin_skill_names(payload)

    assert names == {"build", "plan"}


def test_plugin_skill_names_handles_non_list_payload() -> None:
    """A non-list payload yields an empty set, not a crash.

    The Copilot CLI should print a JSON array, but a malformed run must surface
    as "no plugin skills loaded" (a failed assertion with diagnostics), not an
    unhandled exception that hides the real output.
    """
    assert _plugin_skill_names({"unexpected": "object"}) == set()
    assert _plugin_skill_names(None) == set()


def test_plugin_source_records_are_scoped_to_the_requested_plugin(tmp_path: Path) -> None:
    """Only records under the requested plugin dir count as its plugin source.

    A globally installed plugin (different path, and on 1.0.72 a null pluginName)
    must not make the secondary check treat the shipped plugin as enumerated, and
    must not contribute skill names. This is the fix for the environment-dependent
    flake where a machine with global plugins routed 1.0.72 into the strict subset
    assert (issue #3148).
    """
    requested = tmp_path / "requested-plugin"
    payload: list[object] = [
        {
            "name": "other-skill",
            "source": "plugin",
            "path": str(tmp_path / "other-plugin" / "skills" / "other-skill"),
        }
    ]

    assert _has_plugin_source_record(payload, requested) is False
    assert _plugin_skill_names(payload, requested) == set()

    payload.append(
        {
            "name": "build",
            "source": "plugin",
            "path": str(requested / "skills" / "build"),
        }
    )

    assert _has_plugin_source_record(payload, requested) is True
    assert _plugin_skill_names(payload, requested) == {"build"}


def test_has_plugin_source_record() -> None:
    """`_has_plugin_source_record` detects plugin records independent of name."""
    assert _has_plugin_source_record([{"source": "plugin"}]) is True
    assert _has_plugin_source_record([{"name": "build", "source": "plugin"}]) is True
    assert _has_plugin_source_record([{"name": "review", "source": "builtin"}]) is False
    assert _has_plugin_source_record([]) is False
    assert _has_plugin_source_record({"unexpected": "object"}) is False
    assert _has_plugin_source_record(None) is False


def test_marker_probe_plugin_hook_writes_marker_when_run(tmp_path: Path) -> None:
    """The probe plugin's hook writes its marker when executed directly.

    CLI-independent positive control for the fired-hook detector: if the probe
    script were itself broken, the gated PRIMARY assertion could never pass and
    the failure would be misattributed to the CLI. Build the plugin, run its
    hook, and confirm the marker records the run.
    """
    plugin = tmp_path / "plugin"
    marker = tmp_path / "marker.txt"
    write_marker_probe_plugin(plugin, marker)
    script = plugin / "hooks" / PROBE_EVENT / "probe.py"
    assert script.is_file()

    env = os.environ.copy()
    env["COPILOT_PLUGIN_ROOT"] = str(plugin)
    result = subprocess.run(
        [sys.executable, "-u", str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert marker.is_file()
    text = marker.read_text(encoding="utf-8")
    assert "MARKER" in text
    assert f"COPILOT_PLUGIN_ROOT={plugin}" in text


def test_absent_marker_means_hook_did_not_fire(tmp_path: Path) -> None:
    """A marker that was never written reports no-fire.

    CLI-independent negative control: the gated PRIMARY asserts `marker.is_file()`.
    This pins that the detector reports no-fire when the hook never ran, so a
    genuine plugin-load failure fails the smoke rather than passing.
    """
    marker = tmp_path / "never_written.txt"
    assert not marker.is_file()


def test_clean_env_strips_plugin_root_keys_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plugin-root env cleanup handles Windows-style case-insensitive names."""
    monkeypatch.setenv("claude_plugin_root", "/wrong/claude")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/wrong/project")
    monkeypatch.setenv("Copilot_Plugin_Root", "/wrong/copilot")
    monkeypatch.setenv("KEEP_ME", "1")

    env = _clean_env()

    assert "KEEP_ME" in env
    assert not any(key.upper() in _PLUGIN_ROOT_ENV_KEYS for key in env)


def test_copilot_commands_disable_auto_update() -> None:
    """Pinned smoke runs must not replace the tested binary at startup."""
    command = copilot_command("skill", "list", "--json")

    assert command[1:] == ["--no-auto-update", "skill", "list", "--json"]


# Copilot CLI 1.0.96 stderr for an agent whose `model:` does not resolve.
_REJECTION_STDERR = (
    'Warning: Custom agent "p:model-probe" specifies model "claude-bogus-99.99" '
    'which is not available; using "auto" instead\n'
)


def _load_format_model_id_for_platform() -> Callable[[str, dict[str, str]], str | None]:
    path = REPO_ROOT / "build" / "model_pin_manifest.py"
    spec = importlib.util.spec_from_file_location("_smoke_model_pin_manifest", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.format_model_id_for_platform


def test_rejected_models_reads_the_cli_warning() -> None:
    assert _rejected_models(_REJECTION_STDERR) == ["claude-bogus-99.99"]


def test_rejected_models_reads_every_stream_and_every_warning() -> None:
    second = _REJECTION_STDERR.replace("claude-bogus-99.99", "claude-opus-9.9")

    assert _rejected_models("", _REJECTION_STDERR + second) == [
        "claude-bogus-99.99",
        "claude-opus-9.9",
    ]
    assert _rejected_models("", second) == ["claude-opus-9.9"]


@pytest.mark.parametrize(
    "stderr",
    [
        "",
        "READY\n",
        'Warning: tool "bash" is not available for this agent\n',
        'Warning: Custom agent "p:model-probe" specifies model "" and nothing else\n',
    ],
)
def test_rejected_models_ignores_output_without_the_warning(stderr: str) -> None:
    assert _rejected_models(stderr) == []


@pytest.mark.parametrize("tier", ["opus", "sonnet", "haiku"])
def test_probe_ids_are_what_the_generator_emits_for_copilot(tier: str) -> None:
    """The smoke probes the generator's own output, not a hand-copied literal."""
    tiers = {t: _copilot_tier_model(t) for t in ("opus", "sonnet", "haiku")}
    fmt = _load_format_model_id_for_platform()
    major_minor = re.search(r"(\d+)\.(\d+)$", tiers[tier])
    assert major_minor is not None

    canonical = f"claude-{tier}-{major_minor.group(1)}-{major_minor.group(2)}"

    assert fmt(canonical, tiers) == tiers[tier]


def test_generator_emits_the_no_minor_shape_the_smoke_probes() -> None:
    """``claude-opus-5`` has no minor; the generator must emit ``claude-opus-5``."""
    tiers = {t: _copilot_tier_model(t) for t in ("opus", "sonnet", "haiku")}

    assert _load_format_model_id_for_platform()("claude-opus-5", tiers) == "claude-opus-5"
    assert _copilot_no_minor_model() == "claude-opus-5"
    assert re.fullmatch(r"claude-opus-\d+", _copilot_no_minor_model()) is not None


def test_the_bogus_control_id_is_not_a_shipped_tier_default() -> None:
    shipped = {_copilot_tier_model(t) for t in ("opus", "sonnet", "haiku")}

    assert _BOGUS_MODEL_ID not in shipped
    assert re.fullmatch(r"claude-(opus|sonnet|haiku)-\d+\.\d+", _BOGUS_MODEL_ID) is None


def test_model_probe_plugin_pins_the_model_and_names_the_agent(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"

    ref = _write_model_probe_plugin(plugin, "claude-opus-4.6")

    plugin_name, agent = ref.split(":")
    assert json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))["name"] == plugin_name
    text = (plugin / "agents" / f"{agent}.agent.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---")[1])
    assert frontmatter == {
        "name": "model-probe",
        "description": "model id runtime probe",
        "model": "claude-opus-4.6",
    }


def test_model_probe_plugin_names_are_unique_per_call(tmp_path: Path) -> None:
    first = _write_model_probe_plugin(tmp_path / "a", "claude-opus-4.6")
    second = _write_model_probe_plugin(tmp_path / "b", "claude-opus-4.6")

    assert first != second


def _stub_model_probe_run(
    monkeypatch: pytest.MonkeyPatch, *, returncode: int, stderr: str = ""
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args, returncode, stdout="", stderr=stderr)

    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", fake)
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.copilot_command", lambda *args: ["copilot", *args]
    )
    return calls


def test_model_probe_runs_the_isolated_plugin_from_a_neutral_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_model_probe_run(monkeypatch, returncode=0)

    _run_copilot_model_probe(tmp_path, "claude-opus-4.6")

    args = calls[0]["args"]
    assert isinstance(args, list)
    plugin_dir = Path(args[args.index("--plugin-dir") + 1])
    assert plugin_dir.is_relative_to(tmp_path)
    assert args[args.index("--agent") + 1].endswith(":model-probe")
    assert Path(str(calls[0]["cwd"])).is_relative_to(tmp_path)
    assert Path(str(calls[0]["cwd"])) != REPO_ROOT
    assert not (REPO_ROOT / "src" / "copilot-cli" / "agents" / "model-probe.agent.md").exists()


def test_model_probe_fails_on_a_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_model_probe_run(monkeypatch, returncode=1, stderr="boom")

    with pytest.raises(AssertionError, match=r"model probe failed for claude-opus-4\.6 \(rc=1\)"):
        _run_copilot_model_probe(tmp_path, "claude-opus-4.6")


def test_model_probe_keeps_the_stderr_the_rejection_check_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_model_probe_run(monkeypatch, returncode=0, stderr=_REJECTION_STDERR)

    run = _run_copilot_model_probe(tmp_path, _BOGUS_MODEL_ID)

    assert _rejected_models(run.stderr, run.stdout) == [_BOGUS_MODEL_ID]


def _fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    """Put an executable named ``fakecli`` first on PATH and return it."""
    exe = tmp_path / "fakecli"
    exe.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(sys.modules[__name__], "_STARTUP_PROBE_TIMEOUT_SECONDS", 1)
    return exe


_posix_only = pytest.mark.skipif(sys.platform == "win32", reason="fake CLI is a POSIX shell script")


@_posix_only
def test_startup_probe_reports_a_hung_cli_with_its_resolved_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = _fake_cli(tmp_path, monkeypatch, "exec sleep 30")

    message = _probe_cli_startup("fakecli")

    assert message is not None
    assert str(exe) in message
    assert "did not answer `--version` within 1s" in message


@_posix_only
def test_startup_probe_returns_none_for_a_cli_that_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_cli(tmp_path, monkeypatch, "echo 1.0.0")

    assert _probe_cli_startup("fakecli") is None


@_posix_only
def test_startup_probe_leaves_a_failing_version_to_the_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_cli(tmp_path, monkeypatch, "exit 3")

    assert _probe_cli_startup("fakecli") is None


def test_startup_probe_returns_none_when_the_cli_is_not_installed() -> None:
    assert _probe_cli_startup("no-such-cli-6000") is None


@_posix_only
def test_a_hung_cli_costs_one_probe_not_one_timeout_per_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #6000: the first test fails naming the path, the rest skip at once."""
    exe = _fake_cli(tmp_path, monkeypatch, "exec sleep 30")
    results: dict[str, str | None] = {}

    with pytest.raises(pytest.fail.Exception, match=re.escape(str(exe))):
        _gate_on_startup_probe("fakecli", results)
    started = time.monotonic()
    for _ in range(3):
        with pytest.raises(pytest.skip.Exception, match="hung at startup"):
            _gate_on_startup_probe("fakecli", results)

    assert time.monotonic() - started < 1
    assert results["fakecli"] is not None


def test_a_healthy_cli_is_probed_once_per_session(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(sys.modules[__name__], "_probe_cli_startup", lambda cli: calls.append(cli))
    results: dict[str, str | None] = {}

    for _ in range(3):
        _gate_on_startup_probe("claude", results)

    assert calls == ["claude"]


class _MarkedNode:
    def __init__(self, *markers: str) -> None:
        self._markers = set(markers)

    def get_closest_marker(self, name: str) -> object | None:
        return object() if name in self._markers else None


def test_probe_runs_only_for_the_clis_a_test_is_marked_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(sys.modules[__name__], "_probe_cli_startup", lambda cli: calls.append(cli))

    _probe_clis_marked_on(_MarkedNode("claude", "smoke"), {})
    _probe_clis_marked_on(_MarkedNode("smoke"), {})

    assert calls == ["claude"]


def test_a_hung_claude_does_not_block_the_codex_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys.modules[__name__],
        "_probe_cli_startup",
        lambda cli: "hung" if cli == "claude" else None,
    )
    results: dict[str, str | None] = {}

    with pytest.raises(pytest.fail.Exception):
        _probe_clis_marked_on(_MarkedNode("claude"), results)
    _probe_clis_marked_on(_MarkedNode("codex"), results)

    assert results == {"claude": "hung", "codex": None}


def test_run_cli_uses_cwd_and_decodes_utf8(tmp_path: Path) -> None:
    """The subprocess helper uses neutral cwd and UTF-8 decoding."""
    run = _run_cli(
        [
            sys.executable,
            "-c",
            "import os; print(os.getcwd()); print(chr(0x2713))",
        ],
        cwd=tmp_path,
        timeout=60,
    )

    assert run.returncode == 0
    lines = run.stdout.splitlines()
    assert lines == [str(tmp_path), chr(0x2713)]


def _stub_copilot_probe_run(monkeypatch: pytest.MonkeyPatch, stderr: str) -> None:
    blocked = subprocess.CompletedProcess(["copilot"], 1, stdout="", stderr=stderr)
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.run_copilot_plugin_dir",
        lambda *args, **kwargs: blocked,
    )


def _set_ci(monkeypatch: pytest.MonkeyPatch, *, ci: bool) -> None:
    monkeypatch.delenv("CI", raising=False)
    if ci:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
    else:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


@pytest.mark.parametrize("ci", [True, False], ids=["ci", "local"])
def test_copilot_probe_hook_skips_a_spent_quota_with_the_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ci: bool
) -> None:
    """Budget exhaustion is the only block that skips with the marker (D26)."""
    _set_ci(monkeypatch, ci=ci)
    _stub_copilot_probe_run(monkeypatch, "You have exceeded your monthly quota")

    with pytest.raises(pytest.skip.Exception) as skipped:
        test_copilot_plugin_dir_fires_probe_hook(tmp_path)

    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


@pytest.mark.parametrize(
    "stderr",
    [
        "API rate limit exceeded for user ID 12345.",
        "Failed to fetch PAT user login: connection reset by peer.",
        "No authentication information found.\nSet COPILOT_GITHUB_TOKEN",
        "GitHub returned: Bad credentials",
    ],
    ids=["rate_limit", "transport", "auth_absent", "auth_rejected"],
)
def test_copilot_probe_hook_fails_in_ci_on_a_non_quota_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stderr: str
) -> None:
    _set_ci(monkeypatch, ci=True)
    _stub_copilot_probe_run(monkeypatch, stderr)

    with pytest.raises(pytest.fail.Exception):
        test_copilot_plugin_dir_fires_probe_hook(tmp_path)


def test_copilot_probe_hook_skips_unmarked_locally_on_a_non_quota_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_ci(monkeypatch, ci=False)
    _stub_copilot_probe_run(monkeypatch, "API rate limit exceeded for user ID 12345.")

    with pytest.raises(pytest.skip.Exception) as skipped:
        test_copilot_plugin_dir_fires_probe_hook(tmp_path)

    assert QUOTA_SKIP_MARKER not in str(skipped.value)


def test_copilot_probe_hook_fails_on_an_unclassified_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Negative: rc=1 with no block marker is a real failure, not a skip."""
    broken = subprocess.CompletedProcess(["copilot"], 1, stdout="", stderr="segfault")
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.run_copilot_plugin_dir",
        lambda *args, **kwargs: broken,
    )

    with pytest.raises(AssertionError, match="probe run failed"):
        test_copilot_plugin_dir_fires_probe_hook(tmp_path)


def test_copilot_probe_hook_fails_when_the_marker_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ok = subprocess.CompletedProcess(["copilot"], 0, stdout="ok", stderr="")
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.run_copilot_plugin_dir",
        lambda *args, **kwargs: ok,
    )

    with pytest.raises(AssertionError, match="did not fire"):
        test_copilot_plugin_dir_fires_probe_hook(tmp_path)


def _skill_list_stdout(*names: str, root: Path = _COPILOT_PLUGIN_DIR) -> str:
    records = [
        {
            "name": name,
            "description": "d",
            "source": "plugin",
            "path": str(root / "skills" / name / "SKILL.md"),
            "enabled": True,
        }
        for name in names
    ]
    return json.dumps(records)


def _patch_zero_token_run(
    monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[str]
) -> list[dict[str, object]]:
    """Fake the version call and the skill-list subprocess; return the recorded kwargs."""
    calls: list[dict[str, object]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        return result

    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke.copilot_command", lambda *a: list(a))
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke.subprocess.run", fake_run)
    return calls


def test_zero_token_load_passes_and_isolates_home_and_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ok = subprocess.CompletedProcess(
        ["copilot"], 0, stdout=_skill_list_stdout(*sorted(EXPECTED_SKILLS)), stderr=""
    )
    calls = _patch_zero_token_run(monkeypatch, ok)

    test_copilot_plugin_loads_expected_skills(tmp_path)

    kwargs = calls[0]
    assert Path(str(kwargs["cwd"])).is_relative_to(tmp_path)
    assert not Path(str(kwargs["cwd"])).is_relative_to(REPO_ROOT)
    env = kwargs["env"]
    assert isinstance(env, dict)
    assert Path(env["COPILOT_HOME"]).is_relative_to(tmp_path)


@pytest.mark.parametrize(
    "stderr",
    ["You have exceeded your monthly quota", "API rate limit exceeded for user ID 12345."],
)
def test_zero_token_load_never_skips_on_a_block_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stderr: str
) -> None:
    """Negative: the gate must not hide a failure behind the quota classifier."""
    blocked = subprocess.CompletedProcess(["copilot"], 1, stdout="", stderr=stderr)
    _patch_zero_token_run(monkeypatch, blocked)

    with pytest.raises(AssertionError, match="skill list failed"):
        test_copilot_plugin_loads_expected_skills(tmp_path)


def test_zero_token_load_fails_on_a_missing_expected_skill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    partial = sorted(EXPECTED_SKILLS)[1:]
    ok = subprocess.CompletedProcess(["copilot"], 0, stdout=_skill_list_stdout(*partial), stderr="")
    _patch_zero_token_run(monkeypatch, ok)

    with pytest.raises(AssertionError, match="missing="):
        test_copilot_plugin_loads_expected_skills(tmp_path)


def test_zero_token_load_ignores_skills_from_outside_the_shipped_plugin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Edge: a same-named skill from a user-installed plugin cannot mask a missing one."""
    elsewhere = _skill_list_stdout(*sorted(EXPECTED_SKILLS), root=tmp_path / "other-plugin")
    ok = subprocess.CompletedProcess(["copilot"], 0, stdout=elsewhere, stderr="")
    _patch_zero_token_run(monkeypatch, ok)

    with pytest.raises(AssertionError, match="missing="):
        test_copilot_plugin_loads_expected_skills(tmp_path)


def test_zero_token_load_fails_on_an_argument_hint_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    warned = subprocess.CompletedProcess(
        ["copilot"],
        0,
        stdout=_skill_list_stdout(*sorted(EXPECTED_SKILLS)),
        stderr="warning: argument-hint must be a string",
    )
    _patch_zero_token_run(monkeypatch, warned)

    with pytest.raises(AssertionError, match="argument-hint"):
        test_copilot_plugin_loads_expected_skills(tmp_path)


@pytest.mark.parametrize("stdout", ["not json", '{"skills": []}'])
def test_zero_token_load_fails_on_a_malformed_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stdout: str
) -> None:
    ok = subprocess.CompletedProcess(["copilot"], 0, stdout=stdout, stderr="")
    _patch_zero_token_run(monkeypatch, ok)

    with pytest.raises((AssertionError, pytest.fail.Exception)):
        test_copilot_plugin_loads_expected_skills(tmp_path)


def test_zero_token_load_fails_instead_of_skipping_on_a_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def hang(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            argv,
            _SKILL_LIST_TIMEOUT_SECONDS,
            output=None,
            stderr=b"You have exceeded your monthly quota",
        )

    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke.copilot_command", lambda *a: list(a))
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke.subprocess.run", hang)

    with pytest.raises(pytest.fail.Exception, match="hang"):
        test_copilot_plugin_loads_expected_skills(tmp_path)


def test_empty_plugin_negative_control_skips_classified_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_ci(monkeypatch, ci=False)
    blocked = subprocess.CompletedProcess(
        ["copilot"],
        1,
        stdout="",
        stderr="API rate limit exceeded for user ID 12345.",
    )
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.run_copilot_plugin_dir",
        lambda *args, **kwargs: blocked,
    )

    with pytest.raises(pytest.skip.Exception):
        test_copilot_empty_plugin_dir_does_not_fire_probe_hook(tmp_path)


# ---------------------------------------------------------------------------
# Claude probe auth-skip tests (issue #4861, always-on, no runtime needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "auth_error_text",
    [
        '"result":"Failed to authenticate: OAuth session expired and could not be refreshed"',
        '"result":"Failed to authenticate: token invalid"',
        "oauth session expired",
    ],
    ids=["expired-oauth-json", "failed-auth-generic", "bare-marker"],
)
def test_claude_probe_skips_unmarked_locally_on_expired_oauth(
    monkeypatch: pytest.MonkeyPatch, auth_error_text: str
) -> None:
    """Locally, expired or failed auth skips loudly without the marker
    (issue #4861); markers match on stdout or stderr. CI fails instead (D26)."""
    _set_ci(monkeypatch, ci=False)
    expired = subprocess.CompletedProcess(["claude"], 1, stdout=auth_error_text, stderr="")
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: expired)
    with pytest.raises(pytest.skip.Exception, match="OAuth session expired") as skipped:
        _claude_init_tools("analyst")
    assert QUOTA_SKIP_MARKER not in str(skipped.value)


def test_claude_probe_fails_in_ci_on_expired_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_ci(monkeypatch, ci=True)
    expired = subprocess.CompletedProcess(["claude"], 1, stdout="oauth session expired", stderr="")
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: expired)
    with pytest.raises(pytest.fail.Exception):
        _claude_init_tools("analyst")


def test_claude_probe_skips_with_the_marker_on_a_spent_credit_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spent Claude credit balance is the budget-exhaustion skip (D26)."""
    _set_ci(monkeypatch, ci=True)
    spent = subprocess.CompletedProcess(
        ["claude"], 1, stdout='{"result":"Credit balance is too low"}', stderr=""
    )
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: spent)
    with pytest.raises(pytest.skip.Exception) as skipped:
        _claude_init_tools("analyst")
    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


def test_claude_probe_fails_on_non_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude probe still raises AssertionError on non-auth failures."""
    non_auth = subprocess.CompletedProcess(["claude"], 1, stdout="some unknown error", stderr="")
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: non_auth)
    with pytest.raises(AssertionError, match="claude agent probe failed"):
        _claude_init_tools("analyst")


def test_claude_probe_skips_on_quota_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude quota failures skip instead of failing the local push gate."""
    quota_blocked = subprocess.CompletedProcess(
        ["claude"],
        1,
        stdout='{"api_error_status": 429, "result": "monthly spend limit"}',
        stderr="",
    )
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: quota_blocked)
    with pytest.raises(pytest.skip.Exception, match="quota") as skipped:
        _claude_init_tools("analyst")
    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


def test_claude_probe_succeeds_when_rc_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude probe does NOT skip when the CLI succeeds, even if auth words appear."""
    init_event = json.dumps({"type": "system", "subtype": "init", "tools": ["Bash"]})
    success = subprocess.CompletedProcess(
        ["claude"], 0, stdout=init_event, stderr="oauth session expired"
    )
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: success)
    tools = _claude_init_tools("analyst")
    assert tools == {"Bash"}


# ---------------------------------------------------------------------------
# Copilot agent timeout classification (issue #6181, always-on, no runtime)
# ---------------------------------------------------------------------------


def _raise_timeout(
    stdout: bytes | str | None, stderr: bytes | str | None
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def fake_run_cli(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, _CLI_TIMEOUT_SECONDS, output=stdout, stderr=stderr)

    return fake_run_cli


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        (None, b"\nYou have exceeded your monthly quota (Request ID: X)\n"),
        (b'{"errorCode":"quota_exceeded"}\n', None),
        ("", "You have exceeded your monthly quota"),
    ],
    ids=["bytes-stderr", "bytes-json-stdout", "str-stderr"],
)
def test_copilot_agent_timeout_with_quota_marker_skips(
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes | str | None,
    stderr: bytes | str | None,
) -> None:
    """A run killed while retrying a spent quota skips with the quota reason."""
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", _raise_timeout(stdout, stderr))

    with pytest.raises(pytest.skip.Exception, match="monthly quota is exhausted"):
        _run_copilot_agent("security", "Reply exactly READY.")


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [(None, None), (b'{"type":"session.start"}\n', b"working...\n")],
    ids=["no-output", "unclassified-output"],
)
def test_copilot_agent_timeout_without_block_marker_fails(
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes | str | None,
    stderr: bytes | str | None,
) -> None:
    """A real hang with no block marker stays red instead of skipping."""
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", _raise_timeout(stdout, stderr))

    with pytest.raises(AssertionError, match="exceeded"):
        _run_copilot_agent("security", "Reply exactly READY.")


def test_timeout_failure_message_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """A credential in the partial output never reaches the failure log."""
    secret = "ghp_" + "A" * 36
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli",
        _raise_timeout(f"token={secret}\n".encode(), None),
    )

    with pytest.raises(AssertionError, match="exceeded") as failure:
        _run_copilot_agent("security", "Reply exactly READY.")

    assert secret not in str(failure.value)
    assert "redacted" in str(failure.value)


def test_timeout_redaction_covers_a_token_cut_at_the_tail_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token straddling the 600-character cut is redacted, not half-printed."""
    secret = "ghp_" + "B" * 36
    stdout = f"token={secret}" + "x" * (600 - 20)
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", _raise_timeout(stdout.encode(), None)
    )

    with pytest.raises(AssertionError, match="exceeded") as failure:
        _run_copilot_agent("security", "Reply exactly READY.")

    assert "B" * 20 not in str(failure.value)


_FAKE_CLI_QUOTA = (
    "import sys, time\n"
    "sys.stderr.write('You have exceeded your monthly quota\\n')\n"
    "sys.stderr.flush()\n"
    "time.sleep(60)\n"
)
_FAKE_CLI_SILENT_HANG = "import time\ntime.sleep(60)\n"


@pytest.mark.parametrize(
    ("script", "outcome"),
    [(_FAKE_CLI_QUOTA, pytest.skip.Exception), (_FAKE_CLI_SILENT_HANG, AssertionError)],
    ids=["quota-then-hang", "silent-hang"],
)
def test_copilot_agent_timeout_classifies_real_partial_output(
    monkeypatch: pytest.MonkeyPatch, script: str, outcome: type[BaseException]
) -> None:
    """A real child process killed at its deadline still reaches the classifier.

    Crosses the process boundary the synthetic cases skip: subprocess.run
    returns the captured partial output as bytes on POSIX.
    """
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._CLI_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.copilot_command",
        lambda *_: [sys.executable, "-c", script],
    )

    with pytest.raises(outcome):
        _run_copilot_agent("security", "Reply exactly READY.")


def _raise_timeout_after_version(
    stderr: bytes,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Fake _run_cli: `--version` succeeds; every other call times out."""

    def fake_run_cli(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="1.0.0", stderr="")
        raise subprocess.TimeoutExpired(argv, _CLI_TIMEOUT_SECONDS, output=None, stderr=stderr)

    return fake_run_cli


def _patch_copilot_plugin_timeouts(monkeypatch: pytest.MonkeyPatch, stderr: bytes) -> None:
    def fake_run_plugin(plugin_dir: Path, **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            ["copilot"], _CLI_TIMEOUT_SECONDS, output=None, stderr=stderr
        )

    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke.copilot_command", lambda *a: a)
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", _raise_timeout_after_version(stderr)
    )
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke.run_copilot_plugin_dir", fake_run_plugin)


def _patch_claude_plugin_timeouts(monkeypatch: pytest.MonkeyPatch, stderr: bytes) -> None:
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke.resolve_executable", lambda name: name)
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", _raise_timeout_after_version(stderr)
    )


_PLUGIN_SMOKES = [
    pytest.param(
        "test_copilot_plugin_dir_fires_probe_hook",
        _patch_copilot_plugin_timeouts,
        b"You have exceeded your monthly quota\n",
        id="copilot-probe-hook",
    ),
    pytest.param(
        "test_copilot_empty_plugin_dir_does_not_fire_probe_hook",
        _patch_copilot_plugin_timeouts,
        b"You have exceeded your monthly quota\n",
        id="copilot-empty-plugin",
    ),
]

# Claude zero-token checks: `plugin list` / `plugin details`, no prompt. A block
# marker never turns their timeout into a skip (D26).
_CLAUDE_ZERO_TOKEN_SMOKES = [
    pytest.param("test_claude_plugin_loads_expected_skills", id="claude-plugin-load"),
    pytest.param(
        "test_claude_agent_inventory_excludes_the_non_agent_documents",
        id="claude-agent-inventory",
    ),
]


@pytest.mark.parametrize(("smoke", "patch_timeouts", "block_marker"), _PLUGIN_SMOKES)
def test_plugin_smoke_timeout_without_block_marker_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    smoke: str,
    patch_timeouts: Callable[[pytest.MonkeyPatch, bytes], None],
    block_marker: bytes,
) -> None:
    """A hung plugin smoke fails instead of skipping as CLI latency."""
    patch_timeouts(monkeypatch, b"still working\n")

    with pytest.raises(AssertionError, match="exceeded"):
        globals()[smoke](tmp_path)


@pytest.mark.parametrize(("smoke", "patch_timeouts", "block_marker"), _PLUGIN_SMOKES)
def test_plugin_smoke_timeout_with_block_marker_skips(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    smoke: str,
    patch_timeouts: Callable[[pytest.MonkeyPatch, bytes], None],
    block_marker: bytes,
) -> None:
    """A plugin smoke killed while the CLI reports a block skips with the reason."""
    patch_timeouts(monkeypatch, block_marker)

    with pytest.raises(pytest.skip.Exception, match="quota"):
        globals()[smoke](tmp_path)


@pytest.mark.parametrize("smoke", _CLAUDE_ZERO_TOKEN_SMOKES)
@pytest.mark.parametrize(
    "marker", [b"monthly spend limit\n", b"Credit balance is too low\n", b"OAuth session expired\n"]
)
def test_claude_zero_token_timeout_never_skips_on_a_block_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, smoke: str, marker: bytes
) -> None:
    _set_ci(monkeypatch, ci=False)
    _patch_claude_plugin_timeouts(monkeypatch, marker)

    with pytest.raises(AssertionError, match="zero-token check never skips"):
        globals()[smoke](tmp_path)


def test_claude_agent_probe_timeout_with_auth_marker_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_ci(monkeypatch, ci=False)
    _patch_claude_plugin_timeouts(monkeypatch, b"OAuth session expired\n")

    with pytest.raises(pytest.skip.Exception, match="OAuth session expired"):
        _claude_init_tools("analyst")


def test_claude_agent_probe_timeout_without_block_marker_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_claude_plugin_timeouts(monkeypatch, b"still working\n")

    with pytest.raises(AssertionError, match="claude agent probe for analyst"):
        _claude_init_tools("analyst")


def test_copilot_agent_quota_exit_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run that exits on a spent quota skips before any event parsing."""
    blocked = subprocess.CompletedProcess(
        ["copilot"], 1, stdout="", stderr="You have exceeded your monthly quota"
    )
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: blocked)

    with pytest.raises(pytest.skip.Exception, match="monthly quota is exhausted"):
        _run_copilot_agent("security", "Reply exactly READY.")


_CODEX_PLUGIN_ID = "project-toolkit@ai-agents"
_CODEX_PLUGIN_NAME = "project-toolkit"
# Codex plugin commands read local files only, so they finish in well under a
# second. Kept below _CLI_TIMEOUT_SECONDS so an all-hang run still fits the
# pre-push cap (test_an_all_hang_run_fits_the_pre_push_cap).
_CODEX_COMMAND_TIMEOUT_SECONDS = 45
_CODEX_COMMAND_COUNT = 4
# Allow-list, matched case-insensitively (Windows env names are case-insensitive).
# Codex plugin commands read local files only, so the run needs a PATH to find
# the binary, locale and temp settings, and on Windows the shell variables that
# resolve the npm ``.cmd`` shim. Every other inherited variable, including any
# provider token, is dropped. HOME, USERPROFILE, and CODEX_HOME are set to
# throwaway directories by ``_codex_env``.
_CODEX_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "USERPROFILE",
        "CODEX_HOME",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "APPDATA",
        "LOCALAPPDATA",
        "COMSPEC",
        "PATHEXT",
        "WINDIR",
    }
)


def _codex_env(codex_home: Path, home: Path) -> dict[str, str]:
    """Env for a Codex subprocess: an allow-list, isolated homes, no credential.

    Keeps only ``_CODEX_ENV_ALLOWLIST`` variables from the parent environment, so
    an unlisted token (``GH_TOKEN``, ``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``)
    cannot reach the run. Then points ``CODEX_HOME``, ``HOME``, and
    ``USERPROFILE`` at throwaway directories so stored auth and user-level skills
    cannot leak in.
    """
    env = {key: value for key, value in os.environ.items() if key.upper() in _CODEX_ENV_ALLOWLIST}
    env["CODEX_HOME"] = str(codex_home)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


def _codex_installed_entry(list_stdout: str, plugin_id: str) -> dict[str, object] | None:
    """Return the ``installed`` entry for ``plugin_id`` from ``plugin list --json``.

    Returns None for malformed JSON, a payload without an ``installed`` list, or
    no matching entry, so the caller's assertion names the real gap.
    """
    try:
        payload = json.loads(list_stdout)
    except json.JSONDecodeError:
        return None
    installed = payload.get("installed") if isinstance(payload, dict) else None
    if not isinstance(installed, list):
        return None
    for entry in installed:
        if isinstance(entry, dict) and entry.get("pluginId") == plugin_id:
            return entry
    return None


def _codex_prompt_skill_names(prompt_text: str, plugin_name: str) -> set[str]:
    """Skill names the model-visible prompt lists as ``<plugin>:<skill>``."""
    pattern = rf"(?<![A-Za-z0-9_-]){re.escape(plugin_name)}:([A-Za-z0-9_-]+)"
    return set(re.findall(pattern, prompt_text))


def _run_codex(
    args: list[str], *, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [resolve_executable("codex"), *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_CODEX_COMMAND_TIMEOUT_SECONDS,
        check=False,
        env=env,
    )
    assert result.returncode == 0, (
        f"codex {' '.join(args)} failed (rc={result.returncode}). "
        f"stdout={redact(result.stdout[-600:])!r} stderr={redact(result.stderr[-600:])!r}"
    )
    return result


@pytest.mark.smoke
@requires_codex
@_cli_budget(*([_CODEX_COMMAND_TIMEOUT_SECONDS] * _CODEX_COMMAND_COUNT))
def test_codex_plugin_loads_expected_skills(tmp_path: Path) -> None:
    """codex installs the shipped plugin and its prompt lists every expected skill.

    Install ``project-toolkit@ai-agents`` from ``.claude-plugin/marketplace.json``
    into an isolated ``CODEX_HOME``, confirm ``plugin list --json`` reports it
    installed and enabled from ``src/claude``, then run ``codex debug
    prompt-input`` from a cwd outside the repository so the only source of
    ``project-toolkit:<skill>`` lines is the installed plugin. No model call, no
    credential (REQ-047 AC11).
    """
    home = tmp_path / "home"
    work = tmp_path / "cwd"
    codex_home = tmp_path / "codex-home"
    for directory in (home, work, codex_home):
        directory.mkdir()
    env = _codex_env(codex_home, home)

    try:
        _run_codex(["plugin", "marketplace", "add", str(REPO_ROOT)], env=env, cwd=work)
        _run_codex(["plugin", "add", _CODEX_PLUGIN_ID, "--json"], env=env, cwd=work)
        listing = _run_codex(["plugin", "list", "--json"], env=env, cwd=work)
        prompt = _run_codex(["debug", "prompt-input", "hi"], env=env, cwd=work)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"codex plugin command exceeded {_CODEX_COMMAND_TIMEOUT_SECONDS}s: {exc.cmd}")

    entry = _codex_installed_entry(listing.stdout, _CODEX_PLUGIN_ID)
    assert entry is not None, (
        f"{_CODEX_PLUGIN_ID} missing from plugin list: {listing.stdout[-600:]!r}"
    )
    assert entry.get("installed") is True and entry.get("enabled") is True, entry
    source = entry.get("source")
    source_path = source.get("path") if isinstance(source, dict) else None
    assert isinstance(source_path, str) and Path(source_path).resolve() == (
        _CLAUDE_PLUGIN_DIR.resolve()
    ), f"codex installed {_CODEX_PLUGIN_ID} from {source_path!r}, not {_CLAUDE_PLUGIN_DIR}"

    loaded = _codex_prompt_skill_names(prompt.stdout, _CODEX_PLUGIN_NAME)
    missing = EXPECTED_SKILLS - loaded
    assert not missing, (
        f"codex prompt-input lists no {_CODEX_PLUGIN_NAME}:<skill> for {sorted(missing)}. "
        f"Loaded {len(loaded)} plugin skills."
    )


# --- Grok Build leg (ADR-115 Decision 9) -------------------------------------
# `grok plugin install` needs no login and no model call. Every command runs
# under a scratch HOME and GROK_HOME, so nothing is read from or written to the
# developer's ~/.grok or ~/.claude (Grok also reads ~/.claude/settings.json
# `extraKnownMarketplaces`; the throwaway HOME hides it).
_GROK_PLUGIN_NAME = "project-toolkit"
_GROK_COMMAND_TIMEOUT_SECONDS = 45
_GROK_COMMAND_COUNT = 4
_GROK_SCRIPT_TIMEOUT_SECONDS = 30
_GROK_SCRIPT_COUNT = 2
_GROK_INSTALLED_SCRIPT = Path("skills") / "github" / "scripts" / "pr" / "get_pr_checks.py"
_GROK_COMPONENTS = "components: 1 skill dir(s), 0 command dir(s), 1 agent dir(s)"
# Same allow-list as Codex, with GROK_HOME in place of CODEX_HOME. CLAUDE_PLUGIN_ROOT
# and COPILOT_PLUGIN_ROOT are unlisted, so the installed script must find lib/ by
# its own path (the negative control proves lib/ is what it found).
_GROK_ENV_ALLOWLIST = (_CODEX_ENV_ALLOWLIST - {"CODEX_HOME"}) | {"GROK_HOME"}


def _grok_env(grok_home: Path, home: Path) -> dict[str, str]:
    """Env for a Grok subprocess: an allow-list, isolated homes, no credential."""
    env = {key: value for key, value in os.environ.items() if key.upper() in _GROK_ENV_ALLOWLIST}
    env["GROK_HOME"] = str(grok_home)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


def _grok_marketplace_name(add_stdout: str) -> str | None:
    """Marketplace name from ``Added marketplace source: <name> (<path>)``."""
    match = re.search(r"Added marketplace source:\s+(\S+)", add_stdout)
    return match.group(1) if match else None


def _grok_details_path(details_stdout: str) -> Path | None:
    """Install directory from the ``path:`` line of ``grok plugin details``."""
    match = re.search(r"^\s*path:\s+(.+?)\s*$", details_stdout, flags=re.MULTILINE)
    return Path(match.group(1)) if match else None


def _run_grok(
    args: list[str], *, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [resolve_executable("grok"), *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GROK_COMMAND_TIMEOUT_SECONDS,
        check=False,
        env=env,
    )
    assert result.returncode == 0, (
        f"grok {' '.join(args)} failed (rc={result.returncode}). "
        f"stdout={redact(result.stdout[-600:])!r} stderr={redact(result.stderr[-600:])!r}"
    )
    return result


def _run_installed_script(
    script: Path, *, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run an installed skill script under ``python -I`` without asserting the exit."""
    return subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_GROK_SCRIPT_TIMEOUT_SECONDS,
        check=False,
        env=env,
    )


@pytest.mark.smoke
@requires_grok
@_cli_budget(
    *([_GROK_COMMAND_TIMEOUT_SECONDS] * _GROK_COMMAND_COUNT),
    *([_GROK_SCRIPT_TIMEOUT_SECONDS] * _GROK_SCRIPT_COUNT),
)
def test_grok_plugin_installs_and_runs_a_skill_script(tmp_path: Path) -> None:
    """grok installs the shipped plugin and an installed skill script finds lib/.

    Add the repository as a marketplace source, install ``project-toolkit`` from
    it into a scratch ``GROK_HOME``, assert ``plugin details`` reports the
    expected components, then run ``get_pr_checks.py --help`` from the installed
    copy with both plugin-root variables unset. A copy of ``skills/`` without the
    sibling ``lib/`` must fail with the loader message (negative control). No
    model call, no credential (ADR-115 Decision 9).
    """
    home = tmp_path / "home"
    work = tmp_path / "cwd"
    grok_home = tmp_path / "grok-home"
    for directory in (home, work, grok_home):
        directory.mkdir()
    env = _grok_env(grok_home, home)

    try:
        added = _run_grok(["plugin", "marketplace", "add", str(REPO_ROOT)], env=env, cwd=work)
        marketplace = _grok_marketplace_name(added.stdout)
        assert marketplace, f"no marketplace name in add output: {added.stdout[-400:]!r}"
        _run_grok(
            ["plugin", "install", f"{_GROK_PLUGIN_NAME}@{marketplace}", "--trust"],
            env=env,
            cwd=work,
        )
        details = _run_grok(["plugin", "details", _GROK_PLUGIN_NAME], env=env, cwd=work)
        installed = _grok_details_path(details.stdout)
        assert installed is not None, f"no path: line in details: {details.stdout[-400:]!r}"
        validated = _run_grok(["plugin", "validate", str(installed)], env=env, cwd=work)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"grok plugin command exceeded {_GROK_COMMAND_TIMEOUT_SECONDS}s: {exc.cmd}")

    assert installed.resolve().is_relative_to(grok_home.resolve()), (
        f"grok installed into {installed}, outside the scratch GROK_HOME {grok_home}"
    )
    assert _GROK_COMPONENTS in details.stdout, details.stdout[-600:]
    assert "Plugin manifest is valid." in validated.stdout, validated.stdout[-400:]

    try:
        run = _run_installed_script(installed / _GROK_INSTALLED_SCRIPT, env=env, cwd=work)
        control_skills = tmp_path / "no-lib" / "skills"
        shutil.copytree(installed / "skills", control_skills)
        control = _run_installed_script(
            control_skills / _GROK_INSTALLED_SCRIPT.relative_to("skills"), env=env, cwd=work
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"installed script exceeded {_GROK_SCRIPT_TIMEOUT_SECONDS}s: {exc.cmd}")

    assert run.returncode == 0, f"installed script rc={run.returncode}: {redact(run.stderr[-600:])}"
    assert control.returncode != 0 and "Plugin lib directory not found" in control.stderr, (
        f"negative control (no lib/) rc={control.returncode}: {redact(control.stderr[-400:])!r}"
    )


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("Added marketplace source: repo-name (/x/repo-name)\n", "repo-name"),
        ("  Added marketplace source:   ai-agents\n", "ai-agents"),
        ("Error: nothing added\n", None),
        ("", None),
    ],
)
def test_grok_marketplace_name_parses_the_add_output(stdout: str, expected: str | None) -> None:
    assert _grok_marketplace_name(stdout) == expected


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        (
            "claude-1\n  path: /g/installed-plugins/claude-1\n  kind: local\n",
            "/g/installed-plugins/claude-1",
        ),
        ("  kind: local: /src/claude\n", None),
        ("", None),
    ],
)
def test_grok_details_path_reads_the_install_directory(stdout: str, expected: str | None) -> None:
    result = _grok_details_path(stdout)
    assert (str(result) if result else None) == expected


def test_grok_env_strips_credentials_and_isolates_homes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "x")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/p")
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", "/p")
    monkeypatch.setenv("GROK_HOME", "/real/grok")
    env = _grok_env(tmp_path / "gh", tmp_path / "h")

    assert env["GROK_HOME"] == str(tmp_path / "gh")
    assert env["HOME"] == env["USERPROFILE"] == str(tmp_path / "h")
    assert not {"XAI_API_KEY", "CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"} & set(env)
    assert {key.upper() for key in env} <= _GROK_ENV_ALLOWLIST


def test_codex_installed_entry_finds_the_plugin() -> None:
    payload = json.dumps(
        {"installed": [{"pluginId": "other@x"}, {"pluginId": _CODEX_PLUGIN_ID, "enabled": True}]}
    )

    assert _codex_installed_entry(payload, _CODEX_PLUGIN_ID) == {
        "pluginId": _CODEX_PLUGIN_ID,
        "enabled": True,
    }


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "not json",
        "[]",
        "{}",
        '{"installed": "nope"}',
        '{"installed": [{"pluginId": "other@x"}]}',
        '{"installed": ["project-toolkit@ai-agents"]}',
    ],
)
def test_codex_installed_entry_returns_none_when_the_plugin_is_absent(stdout: str) -> None:
    assert _codex_installed_entry(stdout, _CODEX_PLUGIN_ID) is None


def test_codex_prompt_skill_names_reads_prefixed_names() -> None:
    text = "- project-toolkit:build: x\n- project-toolkit:plan-it: y\nproject-toolkit:ship"

    assert _codex_prompt_skill_names(text, "project-toolkit") == {"build", "plan-it", "ship"}


def test_codex_prompt_skill_names_ignores_other_plugins_and_bare_names() -> None:
    text = "other-project-toolkit:evil build plan other:build project-toolkit build"

    assert _codex_prompt_skill_names(text, "project-toolkit") == set()


def test_codex_prompt_skill_names_flags_a_missing_expected_skill() -> None:
    text = "project-toolkit:build project-toolkit:plan"
    loaded = _codex_prompt_skill_names(text, "project-toolkit")

    assert EXPECTED_SKILLS - loaded == {"ship", "test", "review", "spec", "sync"}


def test_codex_env_strips_credentials_and_isolates_homes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("codex_api_key", "x")
    monkeypatch.setenv("CODEX_HOME", "/real/home")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/elsewhere")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = _codex_env(tmp_path / "ch", tmp_path / "h")

    assert not [key for key in env if key.upper().startswith(("OPENAI", "CLAUDE_PLUGIN"))]
    assert env["CODEX_HOME"] == str(tmp_path / "ch")
    assert env["HOME"] == env["USERPROFILE"] == str(tmp_path / "h")
    assert env["PATH"] == "/usr/bin"
    assert "codex_api_key" not in env


@pytest.mark.parametrize(
    "secret",
    ["GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "COPILOT_GITHUB_TOKEN"],
)
def test_codex_env_drops_unlisted_provider_tokens(
    secret: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(secret, "leak-me")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = _codex_env(tmp_path / "ch", tmp_path / "h")

    assert secret not in env
    assert "leak-me" not in env.values()


def test_codex_env_keeps_only_allow_listed_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("TMPDIR", "/scratch")
    monkeypatch.setenv("SOME_UNLISTED_VAR", "x")

    env = _codex_env(tmp_path / "ch", tmp_path / "h")

    assert {"PATH", "LANG", "TMPDIR"} <= set(env)
    assert "SOME_UNLISTED_VAR" not in env
    assert {key.upper() for key in env} <= _CODEX_ENV_ALLOWLIST


def _smoke_tests() -> list[Callable[..., object]]:
    return [
        obj
        for name, obj in sorted(globals().items())
        if name.startswith("test_")
        and callable(obj)
        and any(mark.name == "smoke" for mark in getattr(obj, "pytestmark", []))
    ]


def _local_smoke_tests() -> list[Callable[..., object]]:
    """Smoke tests the pre-push run executes: it selects ``-m "not copilot"``.

    ``CLI_E2E_LOCAL_MARKERS`` keeps every Copilot case in CI behind the
    agent-copilot environment, so a Copilot hang cannot cost the local push.
    """
    return [
        test
        for test in _smoke_tests()
        if not any(mark.name == "copilot" for mark in getattr(test, "pytestmark", []))
    ]


def _smoke_test_named(name: str) -> Callable[..., object]:
    return globals()[name]


def _timeout_mark_seconds(test: Callable[..., object]) -> float | None:
    for mark in getattr(test, "pytestmark", []):
        if mark.name == "timeout":
            return float(mark.args[0])
    return None


def _first_call_timeout(test: Callable[..., object]) -> int:
    """Timeout of the first CLI call a smoke test makes.

    The Codex and Copilot skill-list tests run local-only commands and stop at
    their own, shorter first timeout. Every other smoke test uses the model-call
    timeout.
    """
    local_only = {
        test_codex_plugin_loads_expected_skills.__name__: _CODEX_COMMAND_TIMEOUT_SECONDS,
        test_grok_plugin_installs_and_runs_a_skill_script.__name__: _GROK_COMMAND_TIMEOUT_SECONDS,
        test_copilot_plugin_loads_expected_skills.__name__: _SKILL_LIST_TIMEOUT_SECONDS,
    }
    return local_only.get(test.__name__, _CLI_TIMEOUT_SECONDS)


def test_every_real_cli_test_outlasts_its_subprocess_timeout() -> None:
    """The pytest kill must land after the subprocess timeout, not before.

    The global --timeout does not exceed _CLI_TIMEOUT_SECONDS, so a smoke test
    with no marker of its own is killed before the CLI output reaches the
    block classifier (issue #6181).
    """
    budgets = {test.__name__: _timeout_mark_seconds(test) for test in _smoke_tests()}

    assert budgets, "found no smoke tests; the marker scan is broken"
    short = {
        name: seconds
        for name, seconds in budgets.items()
        if (seconds or 0) <= _first_call_timeout(_smoke_test_named(name))
    }
    assert not short, f"smoke tests without a budget above the CLI timeout: {short}"


def test_the_pre_push_bound_counts_claude_and_codex_but_not_copilot_smokes() -> None:
    """Copilot smokes run only in CI, so they do not spend the pre-push cap (issue #5333)."""
    local = {test.__name__ for test in _local_smoke_tests()}

    assert test_copilot_accepts_the_generated_model_id_with_rejection_control.__name__ not in local
    assert test_copilot_plugin_loads_expected_skills.__name__ not in local
    assert test_claude_plugin_loads_expected_skills.__name__ in local
    assert test_codex_plugin_loads_expected_skills.__name__ in local
    assert test_grok_plugin_installs_and_runs_a_skill_script.__name__ in local


def test_an_all_hang_run_fits_the_pre_push_cap() -> None:
    """When every CLI hangs, the run still fits the pre-push cap.

    The sum below bounds probes that answer and real calls that then hang: each
    CLI runs one startup probe, and one test (the Claude plugin load) runs
    ``--version`` before its first real call. The sum must stay
    under the pre-push cap, or the cap kills the run and the hung test goes
    unnamed (issue #6181). Copilot smokes are not in the sum: the local run
    deselects them (``_local_smoke_tests``).
    """
    from scripts.validation.git_hook_policy import CLI_E2E_TIMEOUT_SECONDS

    worst_case = (
        len(_PROBED_CLIS) * _STARTUP_PROBE_TIMEOUT_SECONDS
        + _VERSION_TIMEOUT_SECONDS
        + sum(_first_call_timeout(test) for test in _local_smoke_tests())
    )

    assert worst_case < CLI_E2E_TIMEOUT_SECONDS, (
        f"an all-hang run needs {worst_case}s; the pre-push cap is {CLI_E2E_TIMEOUT_SECONDS}s"
    )


@pytest.mark.parametrize(
    "test",
    [
        test_copilot_security_runtime_has_no_shell_with_executor_control,
        test_copilot_analyst_runtime_uses_exact_allowlist_with_executor_control,
    ],
    ids=lambda test: test.__name__,
)
def test_two_run_copilot_agent_tests_outlast_both_runs(
    test: Callable[..., object],
) -> None:
    """Both agent runs can time out on their own before the test is killed."""
    assert (_timeout_mark_seconds(test) or 0) > 2 * _CLI_TIMEOUT_SECONDS


def test_cli_budget_adds_the_margin_to_the_subprocess_timeouts() -> None:
    mark = _cli_budget(60, 240, 240).mark

    assert mark.name == "timeout"
    assert mark.args == (60 + 240 + 240 + _PYTEST_MARGIN_SECONDS,)


# ---------------------------------------------------------------------------
# GitHub tool declaration checks (always-on, no runtime needed)
# ---------------------------------------------------------------------------

_CLAUDE_GITHUB_TOOLS = frozenset(
    {
        "mcp__github__issue_read",
        "mcp__github__pull_request_read",
        "mcp__github__get_file_contents",
        "mcp__github__list_commits",
        "mcp__github__list_workflow_runs",
        "mcp__github__get_workflow_run",
        "mcp__github__get_job_logs",
    }
)

_COPILOT_GITHUB_TOOLS = frozenset(
    {
        "github/issue_read",
        "github/pull_request_read",
        "github/get_file_contents",
        "github/list_commits",
        "github/list_workflow_runs",
        "github/get_workflow_run",
        "github/get_job_logs",
    }
)


def test_claude_analyst_frontmatter_declares_github_tools() -> None:
    """Claude analyst must declare all GitHub MCP tools in its frontmatter.

    The runtime smoke launches Claude with an empty MCP config, so GitHub tools
    never appear at runtime.  This test verifies the frontmatter declarations
    that control tool availability when a GitHub MCP server IS configured.
    """
    claude_analyst = _CLAUDE_PLUGIN_DIR / "agents" / "analyst.md"
    text = claude_analyst.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter = parts[1] if len(parts) >= 3 else ""
    missing = {tool for tool in _CLAUDE_GITHUB_TOOLS if tool not in frontmatter}
    assert not missing, f"Claude analyst frontmatter missing GitHub tools: {sorted(missing)}"


def test_copilot_analyst_manifest_declares_github_tools() -> None:
    """Copilot analyst manifest must declare all GitHub read tools.

    The runtime smoke may not have a GitHub MCP server, so this verifies the
    manifest declarations that control tool availability in production.
    """
    copilot_analyst = _COPILOT_PLUGIN_DIR / "agents" / "analyst.agent.md"
    text = copilot_analyst.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter = parts[1] if len(parts) >= 3 else ""
    missing = {tool for tool in _COPILOT_GITHUB_TOOLS if tool not in frontmatter}
    assert not missing, f"Copilot analyst frontmatter missing GitHub tools: {sorted(missing)}"


def test_read_agent_tools_from_file_returns_analyst_tools() -> None:
    """_read_agent_tools_from_file correctly parses the analyst agent frontmatter.

    Positive control for the file-based fallback (issue #4964).
    """
    tools = _read_agent_tools_from_file("analyst")
    assert tools == _COPILOT_ANALYST_TOOLS


def test_copilot_project_agent_tools_fallback_on_missing_event() -> None:
    """_copilot_project_agent_tools falls back to file when event is absent.

    Edge case: Copilot CLI on hosted runners may not emit
    session.custom_agents_updated (issue #4964). The fallback reads the agent
    file and returns the declared tools.
    """
    # Simulate events with no custom_agents_updated
    events: list[dict[str, object]] = [
        {"type": "user.message", "data": {}},
        {"type": "assistant.message", "data": {}},
        {"type": "result", "data": {}},
    ]
    with pytest.warns(UserWarning, match="session.custom_agents_updated not found"):
        tools = _copilot_project_agent_tools(events, "analyst")
    assert tools == _COPILOT_ANALYST_TOOLS


def test_copilot_project_agent_tools_primary_path() -> None:
    """_copilot_project_agent_tools uses the event when available.

    Positive control: when the event is emitted, it takes precedence.
    """
    events: list[dict[str, object]] = [
        {
            "type": "session.custom_agents_updated",
            "data": {
                "agents": [
                    {"id": "analyst", "source": "project", "tools": ["read", "search"]},
                    {"id": "implementer", "source": "project", "tools": ["shell", "edit"]},
                ]
            },
        }
    ]
    tools = _copilot_project_agent_tools(events, "analyst")
    assert tools == {"read", "search"}


def test_read_agent_tools_from_file_fails_on_missing_agent() -> None:
    """_read_agent_tools_from_file fails clearly on a nonexistent agent."""
    with pytest.raises(AssertionError, match="Agent file not found"):
        _read_agent_tools_from_file("nonexistent-agent-xyz")


# ---------------------------------------------------------------------------
# Live GitHub MCP probe helpers and prerequisite doc (issue #5443, always-on)
# ---------------------------------------------------------------------------


def _init_event(*servers: dict[str, object]) -> dict[str, object]:
    return {"type": "system", "subtype": "init", "mcp_servers": list(servers)}


def test_github_mcp_connected_accepts_a_connected_github_server() -> None:
    assert _github_mcp_connected(_init_event({"name": "github", "status": "connected"}))


@pytest.mark.parametrize(
    "servers",
    [
        [],
        [{"name": "github", "status": "needs-auth"}],
        [{"name": "github", "status": "disabled"}],
        [{"name": "claude.ai GitHub", "status": "connected"}],
        [{"name": "plugin:x:github", "status": "connected"}],
        ["github"],
    ],
    ids=["none", "needs-auth", "disabled", "connector-name", "plugin-name", "malformed"],
)
def test_github_mcp_connected_rejects_anything_but_a_connected_github(
    servers: list[object],
) -> None:
    assert not _github_mcp_connected({"mcp_servers": servers})


def test_github_mcp_connected_rejects_a_missing_server_list() -> None:
    assert not _github_mcp_connected({"type": "system"})


def _call_events(
    *,
    result_content: object,
    is_error: bool = False,
    tool: str = _GITHUB_MCP_PROBE_TOOL,
    result_id: str = "toolu_1",
) -> list[dict[str, object]]:
    return [
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": tool}]},
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": result_id,
                        "is_error": is_error,
                        "content": result_content,
                    }
                ]
            },
        },
    ]


def test_tool_call_outcome_reads_a_string_result() -> None:
    events = _call_events(result_content="# ai-agents")

    assert _claude_tool_call_outcome(events, _GITHUB_MCP_PROBE_TOOL) == (
        True,
        False,
        "# ai-agents",
    )


def test_tool_call_outcome_flattens_text_blocks() -> None:
    events = _call_events(
        result_content=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    )

    assert _claude_tool_call_outcome(events, _GITHUB_MCP_PROBE_TOOL) == (True, False, "ab")


def test_tool_call_outcome_flags_an_error_result() -> None:
    events = _call_events(result_content="No such tool available", is_error=True)

    called, errored, text = _claude_tool_call_outcome(events, _GITHUB_MCP_PROBE_TOOL)

    assert (called, errored, text) == (True, True, "No such tool available")


def test_tool_call_outcome_reports_a_call_that_never_happened() -> None:
    events = _call_events(result_content="x", tool="mcp__github__issue_read")

    assert _claude_tool_call_outcome(events, _GITHUB_MCP_PROBE_TOOL) == (False, False, "")


def test_tool_call_outcome_treats_a_missing_result_as_an_error() -> None:
    events = _call_events(result_content="x", result_id="toolu_other")

    assert _claude_tool_call_outcome(events, _GITHUB_MCP_PROBE_TOOL) == (True, True, "")


def test_tool_call_outcome_survives_malformed_events() -> None:
    events: list[dict[str, object]] = [
        {"type": "assistant", "message": "not a dict"},
        {"type": "assistant", "message": {"content": "not a list"}},
        {"type": "user"},
    ]

    assert _claude_tool_call_outcome(events, _GITHUB_MCP_PROBE_TOOL) == (False, False, "")


def test_tool_result_text_returns_empty_for_unsupported_content() -> None:
    assert _tool_result_text({"content": 7}) == ""


def test_installation_doc_documents_the_github_mcp_prerequisite() -> None:
    """Every agent that grants `mcp__github__*` relies on a server the plugin lacks."""
    text = (REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8")

    assert "## GitHub MCP prerequisite" in text
    section = text.split("## GitHub MCP prerequisite", 1)[1].split("\n## ", 1)[0]
    assert "mcp__github__" in section
    assert "claude mcp add" in section
