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
  - Analyst contract (issue #3918): load the project analyst in each real CLI
    and assert its exact reviewed read-only tool set. Each probe also loads an
    execution agent that must expose shell and edit tools, so the test cannot
    pass when the CLI stops reporting tool availability.

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
    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_plugin_load_smoke.py -v
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, TypeVar

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
        f"Agent file not found: {agent_file}. "
        f"Cannot verify tools for project agent {agent!r}."
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
        f"Claude exposed unreviewed analyst tools: "
        f"{sorted(analyst_tools - _CLAUDE_ANALYST_TOOLS)}"
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
        tool.casefold()
        for tool in _copilot_project_agent_tools(analyst_shell_events, "analyst")
    }
    implementer_tools = {
        tool.casefold()
        for tool in _copilot_project_agent_tools(implementer_events, "implementer")
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
        text=True, encoding="utf-8",
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


def _stub_copilot_probe_run(
    monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
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
    expired = subprocess.CompletedProcess(
        ["claude"], 1, stdout=auth_error_text, stderr=""
    )
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: expired
    )
    with pytest.raises(pytest.skip.Exception, match="OAuth session expired") as skipped:
        _claude_init_tools("analyst")
    assert QUOTA_SKIP_MARKER not in str(skipped.value)


def test_claude_probe_fails_in_ci_on_expired_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_ci(monkeypatch, ci=True)
    expired = subprocess.CompletedProcess(
        ["claude"], 1, stdout="oauth session expired", stderr=""
    )
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: expired
    )
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
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: spent
    )
    with pytest.raises(pytest.skip.Exception) as skipped:
        _claude_init_tools("analyst")
    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


def test_claude_probe_fails_on_non_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude probe still raises AssertionError on non-auth failures."""
    non_auth = subprocess.CompletedProcess(
        ["claude"], 1, stdout="some unknown error", stderr=""
    )
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: non_auth
    )
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
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: quota_blocked
    )
    with pytest.raises(pytest.skip.Exception, match="quota") as skipped:
        _claude_init_tools("analyst")
    assert str(skipped.value).startswith(QUOTA_SKIP_MARKER)


def test_claude_probe_succeeds_when_rc_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude probe does NOT skip when the CLI succeeds, even if auth words appear."""
    init_event = json.dumps(
        {"type": "system", "subtype": "init", "tools": ["Bash"]}
    )
    success = subprocess.CompletedProcess(
        ["claude"], 0, stdout=init_event, stderr="oauth session expired"
    )
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: success
    )
    tools = _claude_init_tools("analyst")
    assert tools == {"Bash"}


# ---------------------------------------------------------------------------
# Copilot agent timeout classification (issue #6181, always-on, no runtime)
# ---------------------------------------------------------------------------


def _raise_timeout(
    stdout: bytes | str | None, stderr: bytes | str | None
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def fake_run_cli(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            argv, _CLI_TIMEOUT_SECONDS, output=stdout, stderr=stderr
        )

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
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", _raise_timeout(stdout, stderr)
    )

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
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", _raise_timeout(stdout, stderr)
    )

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
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.run_copilot_plugin_dir", fake_run_plugin
    )


def _patch_claude_plugin_timeouts(monkeypatch: pytest.MonkeyPatch, stderr: bytes) -> None:
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.resolve_executable", lambda name: name
    )
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
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke._run_cli", lambda *a, **kw: blocked
    )

    with pytest.raises(pytest.skip.Exception, match="monthly quota is exhausted"):
        _run_copilot_agent("security", "Reply exactly READY.")


_CODEX_PLUGIN_ID = "project-toolkit@ai-agents"
_CODEX_PLUGIN_NAME = "project-toolkit"
# Codex plugin commands read local files only, so they finish in well under a
# second. Kept below _CLI_TIMEOUT_SECONDS so an all-hang run still fits the
# pre-push cap (test_an_all_hang_run_fits_the_pre_push_cap).
_CODEX_COMMAND_TIMEOUT_SECONDS = 45
_CODEX_COMMAND_COUNT = 4
_CODEX_SECRET_ENV_PREFIXES = ("OPENAI", "CODEX")


def _codex_env(codex_home: Path, home: Path) -> dict[str, str]:
    """Env for a Codex subprocess: isolated home, no OpenAI or Codex credential.

    Strips inherited ``OPENAI*`` and ``CODEX*`` variables (API keys, a parent
    ``CODEX_HOME``) and the shared plugin-root variables, then points
    ``CODEX_HOME``, ``HOME``, and ``USERPROFILE`` at throwaway directories so
    stored auth and user-level skills cannot leak into the run.
    """
    env = {
        key: value
        for key, value in _clean_env().items()
        if not key.upper().startswith(_CODEX_SECRET_ENV_PREFIXES)
    }
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


def _smoke_tests() -> list[Callable[..., object]]:
    return [
        obj
        for name, obj in sorted(globals().items())
        if name.startswith("test_")
        and callable(obj)
        and any(mark.name == "smoke" for mark in getattr(obj, "pytestmark", []))
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


def test_an_all_hang_run_fits_the_pre_push_cap() -> None:
    """When every CLI hangs, each smoke test stops at its first CLI timeout.

    One test (the Claude plugin load) runs ``--version`` before its first real
    call. The sum must stay
    under the pre-push cap, or the cap kills the run and the hung test goes
    unnamed (issue #6181).
    """
    from scripts.validation.git_hook_policy import CLI_E2E_TIMEOUT_SECONDS

    worst_case = _VERSION_TIMEOUT_SECONDS + sum(
        _first_call_timeout(test) for test in _smoke_tests()
    )

    assert worst_case < CLI_E2E_TIMEOUT_SECONDS, (
        f"an all-hang run needs {worst_case}s; the pre-push cap is "
        f"{CLI_E2E_TIMEOUT_SECONDS}s"
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
    assert not missing, (
        f"Claude analyst frontmatter missing GitHub tools: {sorted(missing)}"
    )


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
    assert not missing, (
        f"Copilot analyst frontmatter missing GitHub tools: {sorted(missing)}"
    )


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
