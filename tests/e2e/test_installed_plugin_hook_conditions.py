"""Opt-in runtime checks for installed Copilot plugin hook conditions.

These tests execute hook scripts from an installed Copilot plugin tree. They do
not run the Copilot CLI or spend model credits. The goal is to verify the
installed artifact that users actually load: hook command paths, matcher no-op
behavior, snake_case payload dispatch, and camelCase payload canonical replay.

Run locally:
    RUN_INSTALLED_PLUGIN_HOOK_E2E=1 uv run pytest \
        tests/e2e/test_installed_plugin_hook_conditions.py -v
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

COPILOT_HOME = Path.home() / ".copilot"
PLUGIN_MARKETPLACE = "ai-agents"
PLUGIN_NAME = "project-toolkit"
RUN_ENV_VAR = "RUN_INSTALLED_PLUGIN_HOOK_E2E"
HOOK_TIMEOUT_SECONDS = 10

_RUN = os.environ.get(RUN_ENV_VAR) == "1"
_MATCHER_RE = re.compile(r"# Matcher: (.+)")
_COMMAND_PATH_RE = re.compile(r'[/\\]hooks[/\\]([^"\s]+\.py)')


@dataclass(frozen=True, slots=True)
class HookScript:
    event: str
    index: int
    path: Path
    matcher: str


@dataclass(frozen=True, slots=True)
class HookCase:
    name: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class HookResult:
    event: str
    index: int
    script: str
    matcher: str
    case: str
    returncode: int
    elapsed_ms: float
    stdout_tail: str
    stderr_tail: str

    @property
    def combined_output(self) -> str:
        return f"{self.stdout_tail}\n{self.stderr_tail}"


@pytest.mark.skipif(
    not _RUN,
    reason=f"set {RUN_ENV_VAR}=1 to test installed Copilot plugin hooks",
)
def test_installed_project_toolkit_hook_conditions(tmp_path: Path) -> None:
    """Installed project-toolkit hooks resolve and honor every condition."""
    plugin_root = _installed_marketplace_plugin_root()
    _assert_no_enabled_direct_shadow(PLUGIN_NAME)

    hook_scripts = _load_hook_scripts(plugin_root)
    fixture = _create_git_fixture(tmp_path)
    results: list[HookResult] = []

    for hook_script in hook_scripts:
        for case in _cases_for_hook(hook_script, fixture):
            results.append(_run_hook_case(plugin_root, fixture, hook_script, case))

    failures = _evaluate_results(results)
    assert not failures, _format_failures(plugin_root, results, failures)


def _installed_marketplace_plugin_root() -> Path:
    plugin_root = (
        COPILOT_HOME
        / "installed-plugins"
        / PLUGIN_MARKETPLACE
        / PLUGIN_NAME
    )
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
    hooks_json = plugin_root / "hooks" / "hooks.json"
    if not manifest.is_file() or not hooks_json.is_file():
        pytest.skip(
            f"{PLUGIN_NAME}@{PLUGIN_MARKETPLACE} is not installed at {plugin_root}"
        )
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_data.get("name") == PLUGIN_NAME
    return plugin_root


def _assert_no_enabled_direct_shadow(plugin_name: str) -> None:
    config_path = COPILOT_HOME / "config.json"
    if not config_path.is_file():
        return

    config = _load_jsonc(config_path)
    installed_plugins = config.get("installedPlugins", [])
    direct_entries = [
        entry
        for entry in installed_plugins
        if entry.get("name") == plugin_name
        and not entry.get("marketplace")
        and entry.get("enabled", True)
    ]
    assert not direct_entries, (
        f"stale direct install can shadow {plugin_name}@{PLUGIN_MARKETPLACE}: "
        f"{direct_entries!r}"
    )


def _load_jsonc(path: Path) -> dict[str, Any]:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("//")
    ]
    return json.loads("\n".join(lines))


def _load_hook_scripts(plugin_root: Path) -> list[HookScript]:
    hooks_path = plugin_root / "hooks" / "hooks.json"
    hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
    scripts: list[HookScript] = []

    for event, entries in hooks_data.get("hooks", {}).items():
        for index, entry in enumerate(entries):
            paths = _script_paths(plugin_root, entry)
            assert paths, f"{event}[{index}] has no hook command path"
            for shell_name, script_path in paths.items():
                assert script_path.is_file(), (
                    f"{event}[{index}] {shell_name} points to missing script: "
                    f"{script_path}"
                )
                assert plugin_root in script_path.parents, (
                    f"{event}[{index}] {shell_name} points outside plugin root: "
                    f"{script_path}"
                )
            script_path = paths.get("powershell") or paths.get("bash") or next(
                iter(paths.values())
            )
            scripts.append(
                HookScript(
                    event=event,
                    index=index,
                    path=script_path,
                    matcher=_read_matcher(script_path),
                )
            )

    assert scripts, f"{hooks_path} contains no hook entries"
    return scripts


def _script_paths(plugin_root: Path, entry: dict[str, Any]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for key in ("bash", "powershell", "command"):
        command = entry.get(key)
        if not isinstance(command, str):
            continue
        match = _COMMAND_PATH_RE.search(command)
        assert match, f"{key} command does not contain a hooks/*.py path: {command}"
        relative_script = Path(*re.split(r"[/\\]", match.group(1)))
        paths[key] = plugin_root / "hooks" / relative_script
    return paths


def _read_matcher(script_path: Path) -> str:
    text = script_path.read_text(encoding="utf-8", errors="replace")
    match = _MATCHER_RE.search(text)
    return match.group(1).strip() if match else ""


def _create_git_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "hook-fixture"
    fixture.mkdir()
    (fixture / ".agents" / "retrospective").mkdir(parents=True)
    (fixture / ".agents" / "sessions").mkdir(parents=True)
    (fixture / ".agents" / "HANDOFF.md").write_text(
        "# Handoff\n\nHook harness fixture.\n",
        encoding="utf-8",
    )
    retro_path = (
        fixture / ".agents" / "retrospective" / "2026-06-02-hook-harness.md"
    )
    retro_path.write_text("# Retro\n", encoding="utf-8")
    (fixture / "README.md").write_text("# Hook Harness\n", encoding="utf-8")

    _run_git(fixture, "init", "-b", "feature/hook-harness")
    _run_git(fixture, "config", "user.email", "hook@example.invalid")
    _run_git(fixture, "config", "user.name", "Hook Harness")
    _run_git(fixture, "add", ".")
    _run_git(fixture, "commit", "-m", "init")
    return fixture


def _run_git(cwd: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _cases_for_hook(hook_script: HookScript, fixture: Path) -> list[HookCase]:
    base_payload: dict[str, Any] = {
        "timestamp": "2026-06-02T00:00:00Z",
        "cwd": str(fixture),
        "session_id": "hook-harness",
    }
    matcher = hook_script.matcher
    if matcher:
        tool_name, command = _matched_tool_and_command(matcher)
        tool_input = {
            "command": command,
            "file_path": str(fixture / "README.md"),
        }
        return [
            HookCase(
                "miss_wrong_tool",
                {
                    **base_payload,
                    "tool_name": "DefinitelyNotTheMatchedTool",
                    "tool_input": tool_input,
                    "tool_response": {},
                },
            ),
            HookCase(
                "match_snake",
                {
                    **base_payload,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_response": {},
                },
            ),
            HookCase(
                "match_camel",
                {
                    **base_payload,
                    "toolName": tool_name,
                    "toolArgs": json.dumps(tool_input),
                    "tool_response": {},
                },
            ),
        ]

    if hook_script.event == "UserPromptSubmit":
        return [
            HookCase(
                "event_payload",
                {
                    **base_payload,
                    "prompt": "Implement a small test change in this repository.",
                },
            )
        ]
    return [HookCase("event_payload", base_payload)]


def _matched_tool_and_command(matcher: str) -> tuple[str, str]:
    kind, params = _classify_matcher(matcher)
    if kind == "regex":
        return _sample_tool_for_regex(params["pattern"]), "hook condition test"
    if kind == "tool-glob":
        tool_name = params["toolName"]
        return tool_name, _sample_command_for_glob(params["argsGlob"], tool_name)
    if params["toolName"] == "Bash":
        return params["toolName"], "git status"
    return params["toolName"], "hook condition test"


def _classify_matcher(pattern: str) -> tuple[str, dict[str, str]]:
    if pattern.startswith("^") and pattern.endswith("$"):
        return "regex", {"pattern": pattern}
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$", pattern)
    if match:
        return "tool-glob", {"toolName": match.group(1), "argsGlob": match.group(2)}
    return "bare", {"toolName": pattern}


def _sample_tool_for_regex(pattern: str) -> str:
    candidates = [
        "LSP",
        "Write",
        "Edit",
        "Read",
        "Glob",
        "Grep",
        "Agent",
        "Task",
        "Bash",
        "mcp__serena__find_symbol",
        "mcp__serena__find_referencing_symbols",
        "mcp__serena__get_symbols_overview",
    ]
    compiled = re.compile(pattern)
    for candidate in candidates:
        if compiled.fullmatch(candidate):
            return candidate
    raise AssertionError(f"no sample tool matches regex hook matcher: {pattern}")


def _sample_command_for_glob(args_glob: str, tool_name: str) -> str:
    first_branch = (args_glob or "").split("|")[0].strip()
    if not first_branch:
        return "echo HOOK_CONDITION_TEST"
    if first_branch.endswith("*"):
        return first_branch[:-1] + " hook-condition-test"
    if "*" not in first_branch:
        return first_branch
    if tool_name == "Bash":
        return "git status"
    return "hook condition test"


def _run_hook_case(
    plugin_root: Path,
    fixture: Path,
    hook_script: HookScript,
    case: HookCase,
) -> HookResult:
    env = os.environ.copy()
    env.update(
        {
            "COPILOT_PLUGIN_ROOT": str(plugin_root),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "CLAUDE_PROJECT_DIR": str(fixture),
            "GITHUB_WORKSPACE": str(fixture),
            "COPILOT_HOOK_DEBUG": "1",
            "NO_COLOR": "1",
        }
    )

    started = time.perf_counter()
    process = subprocess.run(
        [sys.executable, "-u", str(hook_script.path)],
        input=json.dumps(case.payload),
        text=True,
        capture_output=True,
        cwd=fixture,
        env=env,
        timeout=HOOK_TIMEOUT_SECONDS,
        check=False,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return HookResult(
        event=hook_script.event,
        index=hook_script.index,
        script=hook_script.path.name,
        matcher=hook_script.matcher,
        case=case.name,
        returncode=process.returncode,
        elapsed_ms=elapsed_ms,
        stdout_tail=process.stdout[-1000:],
        stderr_tail=process.stderr[-1000:],
    )


def _evaluate_results(results: list[HookResult]) -> list[str]:
    failures: list[str] = []
    for result in results:
        output = result.combined_output.lower()
        location = (
            f"{result.event}[{result.index}] {result.script} "
            f"{result.case} rc={result.returncode}"
        )
        if result.returncode not in (0, 2):
            failures.append(f"{location}: unexpected exit code")
        if result.case.startswith("miss") and result.returncode != 0:
            failures.append(f"{location}: non-match should no-op with exit 0")
        if (
            result.matcher
            and result.case.startswith("miss")
            and "fired=false" not in output
        ):
            failures.append(f"{location}: non-match did not report fired=false")
        if (
            result.matcher
            and result.case.startswith("match")
            and "fired=true" not in output
        ):
            failures.append(f"{location}: match did not report fired=true")
        if result.case == "match_camel" and _looks_like_schema_miss(output):
            failures.append(f"{location}: camelCase payload was not canonicalized")
        if "can't open file" in output or "no such file or directory" in output:
            failures.append(f"{location}: launcher path failed")
    return failures


def _looks_like_schema_miss(output: str) -> bool:
    markers = (
        "missing string `tool_name`",
        "missing tool_input",
        "missing_tool_input",
    )
    return any(marker in output for marker in markers)


def _format_failures(
    plugin_root: Path,
    results: list[HookResult],
    failures: list[str],
) -> str:
    by_event: dict[str, int] = {}
    for result in results:
        by_event[result.event] = by_event.get(result.event, 0) + 1
    summary = ", ".join(
        f"{event}:{count}" for event, count in sorted(by_event.items())
    )
    details = "\n".join(
        f"- {failure}\n{_matching_result_tail(results, failure)}" for failure in failures
    )
    return (
        f"installed plugin hook condition failures for {plugin_root}\n"
        f"cases by event: {summary}\n"
        f"{details}"
    )


def _matching_result_tail(results: list[HookResult], failure: str) -> str:
    for result in results:
        prefix = f"{result.event}[{result.index}] {result.script} {result.case}"
        if failure.startswith(prefix):
            return (
                f"  matcher={result.matcher!r}\n"
                f"  stdout={result.stdout_tail!r}\n"
                f"  stderr={result.stderr_tail!r}"
            )
    return ""
