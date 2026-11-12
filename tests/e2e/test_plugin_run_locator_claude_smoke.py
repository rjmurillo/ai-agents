#!/usr/bin/env python3
"""Real Claude Code smoke for the ADR-121 plugin-root locator, inside a SKILL.md fence.

ADR-121 Rollout step 2 requires a real-CLI check that the committed locator
(``build/scripts/plugin_run_launcher.render_locator``) runs under Claude Code,
including when it sits in a fenced code block of a ``SKILL.md``. The host rewrites
the bare ``${CLAUDE_PLUGIN_ROOT}`` token inside such a block to the absolute plugin
directory. The locator then finds ``lib/ptk_run.py`` under that root and runs the
target script through it.

The test builds a throwaway plugin (``ptkloc``) with a byte copy of
``src/claude/lib/ptk_run.py``, a stub target that prints one JSON line, and two
skills that each hold one fenced command. It runs ``claude -p`` with a model call.

Cases:

* Positive: the ``runit`` skill holds the rendered locator. The stub's marker
  must reach a Bash tool result, with the argument ``one`` intact.
* Negative control 1: the ``runlegacy`` skill holds the legacy nested form. The
  host leaves it literal and the neutral cwd holds no ``.claude``, so the marker
  must not appear. The control also requires that a Bash call was attempted, so
  a model that refuses to run anything cannot pass it.
* Negative control 2 (foreign root): the positive skill runs with
  ``CLAUDE_PLUGIN_ROOT`` pointing at an empty directory with no resolver. The
  marker must still appear.

Gating: it needs ``RUN_CLI_E2E=1``, ``RUN_CLI_MODEL_E2E=1`` (a model call costs
quota), and ``claude`` on PATH. A missing piece skips with a reason that names it.
A blocked run (auth, quota, timeout) goes through ``smoke_skip_policy``. It is
not listed in ``plugin-cli-smoke.yml``.

Run locally:

    RUN_CLI_E2E=1 RUN_CLI_MODEL_E2E=1 env -u CLAUDE_PLUGIN_ROOT -u CLAUDE_PLUGIN_DATA \\
        uv run pytest tests/e2e/test_plugin_run_locator_claude_smoke.py \\
        -m "smoke and claude" -v

Stricter than the issue brief: the run uses ``--output-format stream-json`` so the
assertions read Bash tool results and not the model's paraphrase.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import copilot_hook_probe  # noqa: E402
import smoke_skip_policy  # noqa: E402
from plugin_run_launcher import render_locator  # noqa: E402

from scripts.cli_exec import resolve_executable  # noqa: E402

RESOLVER_SOURCE = REPO_ROOT / "src" / "claude" / "lib" / "ptk_run.py"
PLUGIN_NAME = "ptkloc"
TARGET_REL = "skills/stub/scripts/echo_marker.py"
TARGET_ARG = "one"
MARKER = "ptk-ran"
MODEL = "haiku"
TIMEOUT_SECONDS = 170
ATTEMPTS = 2
ENV_STRIP = frozenset({"CLAUDE_PLUGIN_DATA"})

POSITIVE_SKILL = "runit"
LEGACY_SKILL = "runlegacy"
LEGACY_COMMAND = (
    'python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/'
    f'{TARGET_REL}" {TARGET_ARG}'
)

STUB_SOURCE = (
    f'import json\nimport sys\nprint(json.dumps({{"marker": "{MARKER}", "argv": sys.argv[1:]}}))\n'
)

SKILL_TEMPLATE = """---
name: {name}
description: Run one fixed shell command and report its raw output.
---

# {name}

Run exactly the command in the fenced block below, once, with the Bash tool.
Do not edit it, retry it, or look for another way to run the script.

```bash
{command}
```

Reply with the raw command output only.
"""


def gate_skip_reason(environ: Mapping[str, str], claude_path: str | None) -> str | None:
    """Return why the live run cannot start, or ``None`` when it can."""
    missing = []
    if environ.get("RUN_CLI_E2E") != "1":
        missing.append("RUN_CLI_E2E=1")
    if environ.get("RUN_CLI_MODEL_E2E") != "1":
        missing.append("RUN_CLI_MODEL_E2E=1 (this smoke makes a model call)")
    if not claude_path:
        missing.append("the claude CLI on PATH")
    if not missing:
        return None
    return "ADR-121 locator smoke SKIPPED, it needs " + ", ".join(missing)


_SKIP_REASON = gate_skip_reason(os.environ, shutil.which("claude"))
requires_model_run = pytest.mark.skipif(
    _SKIP_REASON is not None, reason=_SKIP_REASON or "gate open"
)


@dataclass(frozen=True, slots=True)
class Observation:
    """What one ``claude -p`` run did, read from its stream-json output."""

    bash_commands: tuple[str, ...]
    tool_results: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int

    def marker_ran(self) -> bool:
        """True when a Bash tool result holds the stub's JSON line with our argument."""
        return any(
            payload.get("marker") == MARKER and payload.get("argv") == [TARGET_ARG]
            for text in self.tool_results
            for payload in json_lines(text)
        )

    def marker_anywhere(self) -> bool:
        return MARKER in self.stdout

    def describe(self) -> str:
        return (
            f"returncode={self.returncode}\nbash_commands={list(self.bash_commands)!r}\n"
            f"tool_results={list(self.tool_results)!r}\n"
            f"--- full stdout ---\n{self.stdout}\n--- stderr ---\n{self.stderr}"
        )


def json_lines(text: str) -> list[dict[str, object]]:
    """Every line of ``text`` that parses as a JSON object."""
    found = []
    for line in text.splitlines():
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if isinstance(doc, dict):
            found.append(doc)
    return found


def _content_blocks(event: dict[str, object]) -> list[dict[str, object]]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def parse_stream(stdout: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(Bash commands, tool result texts)`` from a stream-json transcript."""
    commands: list[str] = []
    results: list[str] = []
    for event in json_lines(stdout):
        for block in _content_blocks(event):
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    commands.append(str(tool_input.get("command", "")))
            elif block.get("type") == "tool_result":
                results.append(_result_text(block.get("content")))
    return tuple(commands), tuple(results)


def observe(run: subprocess.CompletedProcess[str]) -> Observation:
    commands, results = parse_stream(run.stdout or "")
    return Observation(commands, results, run.stdout or "", run.stderr or "", run.returncode)


def skill_text(name: str, command: str) -> str:
    return SKILL_TEMPLATE.format(name=name, command=command)


def build_plugin(root: Path) -> Path:
    """Write the throwaway ``ptkloc`` plugin under ``root`` and return its directory."""
    plugin = root / "plugin"
    manifest = {
        "name": PLUGIN_NAME,
        "description": "ADR-121 locator smoke plugin",
        "version": "0.0.1",
        "author": {"name": "e2e"},
    }
    files = {
        ".claude-plugin/plugin.json": json.dumps(manifest),
        f"skills/{POSITIVE_SKILL}/SKILL.md": skill_text(
            POSITIVE_SKILL, render_locator(TARGET_REL, TARGET_ARG)
        ),
        f"skills/{LEGACY_SKILL}/SKILL.md": skill_text(LEGACY_SKILL, LEGACY_COMMAND),
        TARGET_REL: STUB_SOURCE,
    }
    for rel, body in files.items():
        path = plugin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    (plugin / "lib").mkdir()
    shutil.copyfile(RESOLVER_SOURCE, plugin / "lib" / "ptk_run.py")
    return plugin


def smoke_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment with inherited plugin-root and plugin-data variables removed."""
    env = copilot_hook_probe.clean_env()
    for key in list(env):
        if key.upper() in ENV_STRIP:
            env.pop(key)
    env.update(extra or {})
    return env


def claude_command(plugin: Path, skill: str) -> list[str]:
    return [
        resolve_executable("claude"),
        "-p",
        f"Run the {skill} skill (/{PLUGIN_NAME}:{skill}).",
        "--plugin-dir",
        str(plugin),
        "--model",
        MODEL,
        "--allowedTools",
        "Bash",
        "--setting-sources",
        "project",
        "--permission-mode",
        "default",
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def run_skill(plugin: Path, cwd: Path, skill: str, env: dict[str, str]) -> Observation:
    """One ``claude -p`` run. A blocked run skips or fails per ``smoke_skip_policy``."""
    try:
        run = subprocess.run(
            claude_command(plugin, skill),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        smoke_skip_policy.skip_or_fail_unmarked(f"claude run exceeded {TIMEOUT_SECONDS}s")
    smoke_skip_policy.skip_or_fail_on_claude_block(run, f"ADR-121 locator smoke ({skill})")
    return observe(run)


def run_with_retry(
    plugin: Path,
    cwd: Path,
    skill: str,
    env: dict[str, str],
    settled: Callable[[Observation], bool],
) -> Observation:
    """Run up to ``ATTEMPTS`` times; stop at the first run that ``settled`` accepts.

    A model can refuse or paraphrase. The retry covers that, and the caller asserts
    on the last run with its full output attached.
    """
    observation = run_skill(plugin, cwd, skill, env)
    for _ in range(ATTEMPTS - 1):
        if settled(observation):
            break
        observation = run_skill(plugin, cwd, skill, env)
    return observation


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    return build_plugin(tmp_path), cwd


@pytest.mark.smoke
@pytest.mark.claude
@requires_model_run
def test_locator_in_a_skill_fence_runs_the_target(tmp_path: Path) -> None:
    plugin, cwd = _workspace(tmp_path)

    seen = run_with_retry(plugin, cwd, POSITIVE_SKILL, smoke_env(), Observation.marker_ran)

    assert seen.marker_ran(), f"the locator did not run the target.\n{seen.describe()}"


@pytest.mark.smoke
@pytest.mark.claude
@requires_model_run
def test_legacy_nested_form_in_a_skill_fence_does_not_run_the_target(tmp_path: Path) -> None:
    """Negative control 1: the host leaves the nested form literal, and cwd has no .claude."""
    plugin, cwd = _workspace(tmp_path)

    def attempted_or_leaked(obs: Observation) -> bool:
        return bool(obs.bash_commands) or obs.marker_anywhere()

    seen = run_with_retry(plugin, cwd, LEGACY_SKILL, smoke_env(), attempted_or_leaked)

    assert not seen.marker_anywhere(), f"the legacy form ran the target.\n{seen.describe()}"
    assert seen.bash_commands, (
        f"no Bash call was made, so the control is vacuous.\n{seen.describe()}"
    )


@pytest.mark.smoke
@pytest.mark.claude
@requires_model_run
def test_locator_survives_a_foreign_plugin_root_in_the_environment(tmp_path: Path) -> None:
    """Negative control 2: a foreign CLAUDE_PLUGIN_ROOT with no resolver must not win."""
    plugin, cwd = _workspace(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    env = smoke_env({"CLAUDE_PLUGIN_ROOT": str(foreign)})

    seen = run_with_retry(plugin, cwd, POSITIVE_SKILL, env, Observation.marker_ran)

    assert seen.marker_ran(), f"a foreign root broke the locator.\n{seen.describe()}"


def _stream(*events: Mapping[str, object]) -> str:
    return "\n".join(json.dumps(event) for event in events)


def _bash_use(command: str) -> dict[str, object]:
    block = {"type": "tool_use", "name": "Bash", "input": {"command": command}}
    return {"type": "assistant", "message": {"content": [block]}}


def _tool_result(content: object) -> dict[str, object]:
    block = {"type": "tool_result", "content": content}
    return {"type": "user", "message": {"content": [block]}}


def _observation(stdout: str) -> Observation:
    return observe(subprocess.CompletedProcess([], 0, stdout, ""))


def test_gate_is_open_only_with_both_flags_and_the_cli() -> None:
    both = {"RUN_CLI_E2E": "1", "RUN_CLI_MODEL_E2E": "1"}
    assert gate_skip_reason(both, "/usr/bin/claude") is None


@pytest.mark.parametrize(
    ("environ", "claude_path", "named"),
    [
        ({}, "/usr/bin/claude", "RUN_CLI_E2E=1"),
        ({"RUN_CLI_E2E": "1"}, "/usr/bin/claude", "RUN_CLI_MODEL_E2E=1"),
        ({"RUN_CLI_MODEL_E2E": "1"}, "/usr/bin/claude", "RUN_CLI_E2E=1"),
        ({"RUN_CLI_E2E": "1", "RUN_CLI_MODEL_E2E": "1"}, None, "claude CLI on PATH"),
        ({"RUN_CLI_E2E": "0", "RUN_CLI_MODEL_E2E": "1"}, "/usr/bin/claude", "RUN_CLI_E2E=1"),
    ],
)
def test_gate_names_every_missing_piece(
    environ: dict[str, str], claude_path: str | None, named: str
) -> None:
    reason = gate_skip_reason(environ, claude_path)
    assert reason is not None
    assert "SKIPPED" in reason
    assert named in reason


def test_gate_lists_all_missing_pieces_together() -> None:
    reason = gate_skip_reason({}, None)
    assert reason is not None
    for named in ("RUN_CLI_E2E=1", "RUN_CLI_MODEL_E2E=1", "claude CLI on PATH"):
        assert named in reason


def test_parse_stream_reads_bash_commands_and_results() -> None:
    stdout = _stream(
        {"type": "system"},
        _bash_use("echo hi"),
        _tool_result("hi"),
        _tool_result([{"type": "text", "text": "listed"}]),
    )
    commands, results = parse_stream(stdout)
    assert commands == ("echo hi",)
    assert results == ("hi", "listed")


def test_parse_stream_skips_non_bash_tools_junk_lines_and_odd_shapes() -> None:
    other = {"type": "tool_use", "name": "Read", "input": {"file_path": "x"}}
    stdout = "\n".join(
        [
            "not json",
            "[1, 2]",
            _stream({"type": "assistant", "message": {"content": [other]}}),
            _stream({"type": "assistant", "message": {"content": "plain text"}}),
            _stream({"type": "assistant", "message": "odd"}),
            _stream(_tool_result(None)),
        ]
    )
    assert parse_stream(stdout) == ((), ("",))


def test_parse_stream_on_empty_output() -> None:
    assert parse_stream("") == ((), ())


def test_marker_ran_needs_the_marker_and_the_argument() -> None:
    good = json.dumps({"marker": MARKER, "argv": [TARGET_ARG]})
    wrong_arg = json.dumps({"marker": MARKER, "argv": []})
    assert _observation(_stream(_tool_result(f"noise\n{good}"))).marker_ran()
    assert not _observation(_stream(_tool_result(wrong_arg))).marker_ran()
    assert not _observation(_stream(_tool_result("no json here"))).marker_ran()


def test_marker_in_model_prose_alone_is_not_a_run() -> None:
    prose = {"type": "assistant", "message": {"content": [{"type": "text", "text": MARKER}]}}
    seen = _observation(_stream(prose))
    assert seen.marker_anywhere()
    assert not seen.marker_ran()


def test_build_plugin_writes_the_plugin_the_run_needs(tmp_path: Path) -> None:
    plugin = build_plugin(tmp_path)

    manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert manifest["name"] == PLUGIN_NAME
    assert (plugin / "lib" / "ptk_run.py").read_bytes() == RESOLVER_SOURCE.read_bytes()
    assert (plugin / TARGET_REL).read_text("utf-8") == STUB_SOURCE
    positive = (plugin / "skills" / POSITIVE_SKILL / "SKILL.md").read_text("utf-8")
    legacy = (plugin / "skills" / LEGACY_SKILL / "SKILL.md").read_text("utf-8")
    assert render_locator(TARGET_REL, TARGET_ARG) in positive
    assert "${CLAUDE_PLUGIN_ROOT}" in positive
    assert LEGACY_COMMAND in legacy


def test_skill_text_never_leaks_the_marker(tmp_path: Path) -> None:
    plugin = build_plugin(tmp_path)
    for skill in (POSITIVE_SKILL, LEGACY_SKILL):
        assert MARKER not in (plugin / "skills" / skill / "SKILL.md").read_text("utf-8")


def test_stub_prints_the_marker_line_for_its_arguments(tmp_path: Path) -> None:
    plugin = build_plugin(tmp_path)
    run = subprocess.run(
        [sys.executable, str(plugin / TARGET_REL), TARGET_ARG],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert run.returncode == 0
    assert json.loads(run.stdout) == {"marker": MARKER, "argv": [TARGET_ARG]}


def test_smoke_env_strips_plugin_root_and_data_and_keeps_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/x")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/y")
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", "/z")
    monkeypatch.setenv("KEEP_ME", "1")

    bare = smoke_env()
    assert not {"CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "COPILOT_PLUGIN_ROOT"} & set(bare)
    assert bare["KEEP_ME"] == "1"
    assert smoke_env({"CLAUDE_PLUGIN_ROOT": "/foreign"})["CLAUDE_PLUGIN_ROOT"] == "/foreign"


def test_claude_command_carries_the_isolation_flags(tmp_path: Path) -> None:
    command = claude_command(tmp_path, POSITIVE_SKILL)
    assert command[1] == "-p"
    assert f"/{PLUGIN_NAME}:{POSITIVE_SKILL}" in command[2]
    for flag, value in [
        ("--plugin-dir", str(tmp_path)),
        ("--model", MODEL),
        ("--allowedTools", "Bash"),
        ("--setting-sources", "project"),
        ("--permission-mode", "default"),
    ]:
        assert command[command.index(flag) + 1] == value


def test_run_with_retry_stops_after_a_settled_first_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def fake(*_args: object) -> Observation:
        calls.append(1)
        return _observation("")

    monkeypatch.setattr(sys.modules[__name__], "run_skill", fake)
    run_with_retry(tmp_path, tmp_path, POSITIVE_SKILL, {}, lambda _obs: True)
    assert len(calls) == 1


def test_run_with_retry_retries_once_then_returns_the_last_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def fake(*_args: object) -> Observation:
        calls.append(1)
        return _observation(f"run {len(calls)}")

    monkeypatch.setattr(sys.modules[__name__], "run_skill", fake)
    last = run_with_retry(tmp_path, tmp_path, POSITIVE_SKILL, {}, lambda _obs: False)
    assert len(calls) == ATTEMPTS == 2
    assert last.stdout == "run 2"
