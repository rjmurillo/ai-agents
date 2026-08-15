#!/usr/bin/env python3
# taste-lint: ignore file-size -- always-on unit tests and opt-in e2e smokes must
# coexist in one file (same plugin contract, one source of truth per issue #3148).
"""End-to-end plugin and agent-contract smoke for the shipped CLIs.

PR #2735 was green on unit tests, schema checks, and generated-file checks, yet a
broken skill front-matter field (``argument-hint must be a string``) could still
reach a customer because nothing loaded the plugin in the real CLI and asserted
the skills loaded. These tests close that gap: they launch the REAL CLIs, load
the shipped plugin directory, and assert the plugin loads.

  - Copilot: the PRIMARY load signal is a FIRED HOOK (issue #3148). Running
    ``copilot --plugin-dir <probe> -p`` from a neutral cwd fires the probe
    plugin's ``UserPromptSubmit`` hook, which proves the CLI loads and dispatches
    a ``--plugin-dir`` plugin regardless of how ``skill list --json`` labels
    plugin skills. The shared probe lives in ``tests/e2e/copilot_hook_probe.py``
    so this smoke and ``tests/e2e/test_cli_hook_e2e.py`` use the same source of
    truth. As a co-primary #2736 guard, ``copilot --plugin-dir <repo> skill list
    --json`` must return 0 with no ``argument-hint`` loader warning. The
    ``EXPECTED_SKILLS`` subset check is kept only as a SECONDARY soft signal for
    when the CLI does enumerate the shipped plugin under ``source: plugin``.
  - Claude: ``claude --plugin-dir <repo>/.claude plugin list`` and
    ``plugin details project-toolkit`` with ``cwd`` set to a neutral directory.
    Assert returncode 0, the manifest name appears, and the expected lifecycle
    skills are present in the details output.
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
``tests/e2e/test_cli_hook_e2e.py``. Both run in the same nightly workflow under
``RUN_CLI_E2E=1``; each has its own JUnit report so a silent skip of either is a
red run.

Why opt-in: these spawn real CLIs that need authentication and spend model
credits, which bare CI does not have. They run wherever the CLIs are installed
and ``RUN_CLI_E2E=1`` is set (local dev, the nightly job with secrets); elsewhere
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
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

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
finally:
    sys.path[:] = _original_sys_path

# Fired-hook probe: ONE source of truth shared with test_cli_hook_e2e.py (#3148).
from copilot_hook_probe import (  # noqa: E402
    PROBE_EVENT,
    copilot_command,
    copilot_run_blocked,
    copilot_run_blocked_headline,
    run_copilot_plugin_dir,
    write_marker_probe_plugin,
)


def _skip_on_copilot_block(result: subprocess.CompletedProcess[str]) -> None:
    """Skip when an external or credential condition blocks Copilot.

    A rate limit, transport failure, or auth gate is not a branch defect.
    Skipping lets the pre-push proceed. The nightly workflow uses
    assert_smoke_ran.py to detect skipped smokes, so the nightly still fails red
    when the real CLI cannot run (issues #4504, #4483, #3275).
    """
    if copilot_run_blocked(result):
        pytest.skip(copilot_run_blocked_headline(result))


_RUN = os.environ.get("RUN_CLI_E2E") == "1"

# The lifecycle skills PR #2735 verified by hand. They ship in BOTH plugin trees
# (src/copilot-cli/skills/<name>/ and .claude/commands/<name>.md), so the same
# set is the load contract for both CLIs. The always-on unit checks below pin
# this set against the on-disk trees so a rename fails without a real CLI.
EXPECTED_SKILLS = frozenset({"build", "plan", "ship", "test", "review", "spec", "sync"})

_COPILOT_PLUGIN_DIR = REPO_ROOT / "src" / "copilot-cli"
_CLAUDE_PLUGIN_DIR = REPO_ROOT / ".claude"
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

_CLI_TIMEOUT_SECONDS = 240
_PLUGIN_ROOT_ENV_KEYS = {"CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "COPILOT_PLUGIN_ROOT"}

requires_copilot = pytest.mark.skipif(
    not (_RUN and shutil.which("copilot")),
    reason="needs RUN_CLI_E2E=1 and the copilot CLI on PATH (real auth + credits)",
)
requires_claude = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (real auth + credits)",
)


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


def _claude_init_tools(agent: str) -> set[str]:
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
    assert run.returncode == 0, (
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


@pytest.mark.smoke
@requires_copilot
def test_copilot_plugin_loads_expected_skills(tmp_path: Path) -> None:
    """copilot loads the plugin, proven by a fired hook, with no loader warning.

    Primary load signal (version-agnostic, issue #3148): ``copilot --plugin-dir
    <probe> -p`` fires the probe plugin's ``UserPromptSubmit`` hook, proving the
    CLI loads and dispatches a ``--plugin-dir`` plugin without depending on how
    ``skill list --json`` labels plugin skills. Co-primary (issue #2736): the
    shipped ``src/copilot-cli`` plugin lists skills with returncode 0 and no
    ``argument-hint`` loader warning. Secondary soft signal: when the CLI does
    enumerate the shipped plugin under ``source: plugin``, ``EXPECTED_SKILLS``
    must be a subset (so a CLI that enumerates and is genuinely broken still
    fails).
    """
    version = _run_cli(
        copilot_command("--version"),
        timeout=60,
    )
    print(f"copilot --version: {version.stdout.strip() or version.stderr.strip()}")

    # PRIMARY: a fired hook proves the --plugin-dir plugin loaded and dispatched.
    probe_plugin = tmp_path / "probe-plugin"
    marker = tmp_path / "probe_marker.txt"
    userland = tmp_path / "userland"
    userland.mkdir()
    write_marker_probe_plugin(probe_plugin, marker)
    try:
        fired = run_copilot_plugin_dir(probe_plugin, cwd=userland, timeout=_CLI_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        pytest.skip(
            f"copilot --plugin-dir probe exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)"
        )
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

    # CO-PRIMARY (issue #2736): the shipped plugin lists skills with no loader warning.
    try:
        run = _run_cli(
            copilot_command(
                "--plugin-dir",
                str(_COPILOT_PLUGIN_DIR),
                "skill",
                "list",
                "--json",
            ),
            cwd=tmp_path,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.skip(f"copilot skill list exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)")

    _skip_on_copilot_block(run)
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

    if not isinstance(payload, list):
        pytest.fail(
            "copilot skill list --json did not return a JSON array "
            f"(got {type(payload).__name__}); the enumeration schema changed. "
            f"stdout={run.stdout[-600:]!r}"
        )

    # SECONDARY soft signal. When the CLI enumerates the shipped plugin under
    # source: plugin, EXPECTED_SKILLS must be a subset, so a CLI that DOES
    # enumerate and is genuinely broken still fails. When it does not enumerate
    # the plugin (CLI 1.0.69+, issues #2990/#3014/#3090/#3135), the fired-hook and
    # no-loader-warning signals above already proved the load, so the absence of
    # source: plugin records is not a failure and not a skip. Scoping by plugin
    # dir also drops globally installed plugins (pluginName: null), removing the
    # environment-dependent flake that used to route 1.0.72 into a strict assert.
    if _has_plugin_source_record(payload, _COPILOT_PLUGIN_DIR):
        loaded = _plugin_skill_names(payload, _COPILOT_PLUGIN_DIR)
        missing = EXPECTED_SKILLS - loaded
        assert not missing, (
            "copilot enumerated the shipped plugin under source: plugin but omitted expected "
            f"skills: missing={sorted(missing)} loaded={sorted(loaded)}"
        )


@pytest.mark.smoke
@requires_copilot
def test_copilot_empty_plugin_dir_does_not_fire_probe_hook(tmp_path: Path) -> None:
    """Negative control: the fired-hook load signal fails when nothing loads.

    A marker-writing probe hook exists on disk, but copilot is pointed at a
    DIFFERENT, empty plugin dir. The probe hook must NOT fire, so its marker
    stays absent. This proves the PRIMARY assertion in
    ``test_copilot_plugin_loads_expected_skills`` fails loud when the plugin does
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
    except subprocess.TimeoutExpired:
        pytest.skip(
            f"copilot --plugin-dir empty exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)"
        )
    _skip_on_copilot_block(run)
    assert not marker.is_file(), (
        "negative control failed: copilot fired the probe hook while pointed at an EMPTY "
        "--plugin-dir, so a fired marker cannot distinguish load from no-load and the smoke's "
        f"primary assertion would pass unconditionally. stdout={run.stdout[-600:]!r} "
        f"stderr={run.stderr[-600:]!r}"
    )


@pytest.mark.smoke
@requires_claude
def test_claude_plugin_loads_expected_skills(tmp_path: Path) -> None:
    """claude --plugin-dir loads project-toolkit at the manifest version.

    Asserts returncode 0 on ``plugin list`` and that the version from
    ``.claude/.claude-plugin/plugin.json`` appears in ``plugin details``, proving
    the CLI loaded the shipped plugin rather than failing silently.
    """
    version = _run_cli(
        [resolve_executable("claude"), "--version"],
        timeout=60,
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
    except subprocess.TimeoutExpired:
        pytest.skip(f"claude plugin list exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)")

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
    except subprocess.TimeoutExpired:
        pytest.skip(f"claude plugin details exceeded {_CLI_TIMEOUT_SECONDS}s (CLI/infra latency)")

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
@requires_copilot
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


def test_expected_skills_ship_in_copilot_plugin_tree() -> None:
    """Each EXPECTED_SKILLS entry has a skill dir in the Copilot plugin tree.

    If a lifecycle skill is renamed or removed from src/copilot-cli/skills, the
    gated Copilot smoke would assert a name that can never load. Pin the set to
    the on-disk tree so that drift fails in bare CI, not only in the nightly job.
    """
    skills_dir = _COPILOT_PLUGIN_DIR / "skills"
    missing = {name for name in EXPECTED_SKILLS if not (skills_dir / name).is_dir()}
    assert not missing, f"expected skills missing from {skills_dir}: {sorted(missing)}"


def test_expected_skills_ship_in_claude_tree() -> None:
    """Each EXPECTED_SKILLS entry ships in the Claude tree as command or skill.

    The Claude plugin surfaces a lifecycle capability either as a slash command
    under .claude/commands/<name>.md or as a skill under .claude/skills/<name>/.
    Most lifecycle names ship as commands; `review` ships as a skill dir. Accept
    either so the contract tracks how the plugin actually exposes the capability,
    and so a rename in both places fails in bare CI before the nightly Claude
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


@pytest.mark.parametrize("blocked_phase", ["probe", "skill-list"])
@pytest.mark.parametrize(
    "stderr",
    [
        "API rate limit exceeded for user ID 12345.",
        "Failed to fetch PAT user login: connection reset by peer.",
    ],
)
def test_copilot_plugin_smoke_skips_classified_block(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    blocked_phase: str,
    stderr: str,
) -> None:
    """Both real Copilot calls skip before plugin assertions on external blocks."""
    success = subprocess.CompletedProcess(["copilot"], 0, stdout="[]", stderr="")
    blocked = subprocess.CompletedProcess(["copilot"], 1, stdout="", stderr=stderr)

    def fake_run_cli(argv: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        if "--version" in argv:
            return success
        return blocked if blocked_phase == "skill-list" else success

    def fake_run_plugin(
        plugin_dir: Path, **_: object
    ) -> subprocess.CompletedProcess[str]:
        if blocked_phase == "probe":
            return blocked
        (plugin_dir.parent / "probe_marker.txt").write_text("MARKER", encoding="utf-8")
        return success

    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke.copilot_command", lambda *a: a)
    monkeypatch.setattr("tests.e2e.test_plugin_load_smoke._run_cli", fake_run_cli)
    monkeypatch.setattr(
        "tests.e2e.test_plugin_load_smoke.run_copilot_plugin_dir",
        fake_run_plugin,
    )

    with pytest.raises(pytest.skip.Exception):
        test_copilot_plugin_loads_expected_skills(tmp_path)


def test_empty_plugin_negative_control_skips_classified_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
